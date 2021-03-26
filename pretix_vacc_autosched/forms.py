import datetime as dt
from django import forms
from django.core.exceptions import ValidationError
from django.http import Http404
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_scopes.forms import SafeModelChoiceField
from i18nfield.forms import I18nFormField, I18nTextarea, I18nTextInput
from pretix.base.email import get_available_placeholders
from pretix.base.forms import PlaceholderValidator, SettingsForm
from pretix.base.models import Quota, SubEvent
from pretix.base.services.quotas import QuotaAvailability

from .models import ItemConfig
from .tasks import get_for_other_event


class ItemConfigForm(forms.ModelForm):
    class Meta:
        model = ItemConfig
        fields = ["days", "max_days", "event"]
        exclude = []
        field_classes = {"event": SafeModelChoiceField}

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop("event")
        super().__init__(*args, **kwargs)
        self.fields["event"].queryset = self.event.organizer.events.filter(
            has_subevents=True
        ).order_by("date_from")
        self.fields["days"].required = False
        self.fields["days"].widget.is_required = False

    def clean(self):
        data = super().clean()
        if data.get("days"):
            if not self.event.has_subevents:
                raise ValidationError("This may only be used on event series.")
        if data.get("event"):
            target_event = data["event"]
            has_item = (
                len(
                    [
                        n
                        for n in target_event.items.all()
                        if (n.internal_name or str(n.name))
                        == (
                            self.instance.item.internal_name
                            or str(self.instance.item.name)
                        )
                    ]
                )
                == 1
            )
            if not has_item:
                raise ValidationError(
                    _(
                        "You selected an event series that does not have product with the same name as this "
                        "product."
                    )
                )
        return data

    def save(self, commit=True):
        if self.cleaned_data["days"] is None:
            if self.instance.pk:
                self.instance.delete()
            else:
                return
        else:
            return super().save(commit=commit)


class AutoschedSettingsForm(SettingsForm):
    vacc_autosched_mail = forms.BooleanField(
        label=_("Send email if second dose has been scheduled"),
        required=False,
    )

    vacc_autosched_subject = I18nFormField(
        label=_("Email Subject"),
        required=True,
        widget=I18nTextInput,
    )

    vacc_autosched_body = I18nFormField(
        label=_("Email Body"),
        required=True,
        widget=I18nTextarea,
    )

    vacc_autosched_self_service = forms.BooleanField(
        label=_("Self-service for second doses"),
        help_text=_(
            "Allows customers to schedule their second dose via the /2nd page."
        ),
        required=False,
    )
    vacc_autosched_self_service_info = I18nFormField(
        label=_("Self service introduction"),
        help_text=_(
            "This text will be shown on the general self-service page, where customers enter their order code. You can use Markdown here."
        ),
        required=False,
        widget=I18nTextarea,
    )
    vacc_autosched_self_service_order_info = I18nFormField(
        label=_("Self service order information"),
        help_text=_(
            "This text will be shown on the page where customers order their second appointment. You can use Markdown here."
        ),
        required=False,
        widget=I18nTextarea,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.event = kwargs.pop("obj")

        self._set_field_placeholders(
            "vacc_autosched_subject", ["event"], ["{scheduled_datetime}"]
        )
        self._set_field_placeholders(
            "vacc_autosched_body", ["event"], ["{scheduled_datetime}"]
        )

    def _set_field_placeholders(self, fn, base_parameters, extras=[]):
        phs = [
            "{%s}" % p
            for p in sorted(
                get_available_placeholders(self.event, base_parameters).keys()
            )
        ] + extras
        ht = _("Available placeholders: {list}").format(list=", ".join(phs))
        if self.fields[fn].help_text:
            self.fields[fn].help_text += " " + str(ht)
        else:
            self.fields[fn].help_text = ht
        self.fields[fn].validators.append(PlaceholderValidator(phs))


class SecondDoseCodeForm(forms.Form):
    order = forms.CharField(label=_("Order code"))

    def __init__(self, event, *args, **kwargs):
        self.event = event
        return super().__init__(*args, **kwargs)

    def clean_order(self):
        code = self.cleaned_data.get("order")
        order = self.event.orders.filter(code__iexact=code).first()
        if not order:
            order = self.event.orders.filter(secret__iexact=code).first()
        if not order:
            order = self.event.orders.filter(all_positions__secret__iexact=code).first()
        if not order:
            raise forms.ValidationError(_("Unknown order code."))
        return order


class SecondDoseOrderForm(forms.Form):
    def __init__(self, *args, position=None, **kwargs):
        self.position = position
        super().__init__(*args, **kwargs)

        config = getattr(position.item, "vacc_autosched_config", None)
        if not config:  # We make sure this exists in the view
            raise Exception("No item config, cannot provide second dose.")

        event = config.event or position.order.event
        self.target_item, self.target_variation = get_for_other_event(position, event)

        first_date = position.subevent.date_from.date()
        min_date = max(first_date + dt.timedelta(days=config.days), now().date())
        max_date = first_date + dt.timedelta(days=config.max_days)

        subevents = event.subevents.filter(
            date_from__date__gte=min_date, date_from__date__lte=max_date
        )
        subevents = SubEvent.annotated(subevents)
        quotas_to_compute = []
        for subevent in subevents:
            if subevent.presale_is_running:
                quotas_to_compute += [
                    q
                    for q in subevent.active_quotas
                    if not q.cache_is_hot(now() + dt.timedelta(seconds=5))
                ]
        if quotas_to_compute:
            qa = QuotaAvailability()
            qa.queue(*quotas_to_compute)
            qa.compute()
            for subevent in subevents:
                subevent._quota_cache = qa.results
        subevents = [
            se
            for se in subevents
            if se.best_availability_state == Quota.AVAILABILITY_OK
        ]
        self.subevents = subevents
        if not subevents:
            raise Http404()
        self.fields["subevent"] = SafeModelChoiceField(
            queryset=event.subevents.filter(pk__in=[e.pk for e in subevents]),
            label=_("Date"),
            widget=forms.RadioSelect,
        )
