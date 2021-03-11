import logging
from django import forms
from django.urls import reverse
from django.utils.translation import ugettext_lazy as _
from i18nfield.forms import I18nFormField, I18nTextarea, I18nTextInput
from pretix.base.email import get_available_placeholders
from pretix.base.forms import PlaceholderValidator, SettingsForm
from pretix.base.models import Event
from pretix.control.views.event import EventSettingsFormView, EventSettingsViewMixin

logger = logging.getLogger(__name__)


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


class SettingsView(EventSettingsViewMixin, EventSettingsFormView):
    model = Event
    form_class = AutoschedSettingsForm
    template_name = "pretix_vacc_autosched/settings.html"
    permission = "can_change_settings"

    def get_success_url(self) -> str:
        return reverse(
            "plugins:pretix_vacc_autosched:settings",
            kwargs={
                "organizer": self.request.event.organizer.slug,
                "event": self.request.event.slug,
            },
        )
