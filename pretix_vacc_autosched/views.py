import datetime as dt
import logging

from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.formats import date_format
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView
from pretix_vacc_autosched.forms import (
    AutoschedSettingsForm,
    SecondDoseCodeForm,
    SecondDoseOrderForm,
)
from pretix_vacc_autosched.models import LinkedOrderPosition
from pretix_vacc_autosched.tasks import get_for_other_event

from pretix.base.models import Event, Quota
from pretix.base.services.quotas import QuotaAvailability
from pretix.control.views.event import EventSettingsFormView, EventSettingsViewMixin
from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.views import EventViewMixin

logger = logging.getLogger(__name__)


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


class SelfServiceMixin:
    def dispatch(self, request, *args, **kwargs):
        if not request.event.settings.vacc_autosched_self_service:
            raise Http404(_("Feature not enabled"))
        return super().dispatch(request, *args, **kwargs)


class SelfServiceIndexView(SelfServiceMixin, EventViewMixin, FormView):
    form_class = SecondDoseCodeForm
    template_name = "pretix_vacc_autosched/self_service_index.html"

    def get_form_kwargs(self):
        result = super().get_form_kwargs()
        result["event"] = self.request.event
        return result

    def form_valid(self, form):
        order = form.cleaned_data.get("order")
        return redirect(
            eventreverse(
                order.event,
                "plugins:pretix_vacc_autosched:second.booking",
                kwargs={"order": order.code},
            )
        )


class SelfServiceBookingView(SelfServiceMixin, EventViewMixin, FormView):
    form_class = SecondDoseOrderForm
    template_name = "pretix_vacc_autosched/self_service_order.html"

    @cached_property
    def order(self):
        return (
            self.request.event.orders.filter(code=self.kwargs["order"])
                .select_related("event")
                .first()
        )

    def dispatch(self, request, *args, **kwargs):
        if not self.order:
            messages.error(
                request,
                _(
                    "We were unable to find a valid ticket with this code, please try again."
                ),
            )
            return redirect(
                eventreverse(
                    self.request.event,
                    "plugins:pretix_vacc_autosched:second.index",
                )
            )

        if self.order.status != self.order.STATUS_PAID or self.order.require_approval:
            messages.error(
                request,
                _(
                    "Scheduling of a second appointment is not available for this ticket since it has not yet been approved or has been canceled."
                ),
            )
            return redirect(
                eventreverse(
                    self.request.event,
                    "plugins:pretix_vacc_autosched:second.index",
                )
            )

        position = (
            self.order.positions.first()
        )  # We assume that there's only one position per order
        if (
                not position.subevent
                or not position.subevent.date_from.date() <= now().date()
        ):
            messages.error(
                request,
                _(
                    "Please do not try to schedule a second appointment before your first appointment is over."
                ),
            )
            return redirect(
                eventreverse(
                    self.request.event,
                    "plugins:pretix_vacc_autosched:second.index",
                )
            )

        config = getattr(position.item, "vacc_autosched_config", None)
        if not config or not config.days or not position.subevent:
            messages.error(
                request,
                _(
                    "Scheduling of a second appointment is not available for this ticket."
                ),
            )
            return redirect(
                eventreverse(
                    self.request.event,
                    "plugins:pretix_vacc_autosched:second.index",
                )
            )

        self.position = position
        link = LinkedOrderPosition.objects.filter(base_position=position).first()
        if link:
            messages.error(
                request,
                _(
                    "A second appointment has already been scheduled for {datetime}. The ticket has been sent to you via email to the address used for your first booking."
                ).format(
                    datetime=date_format(
                        link.child_position.subevent.date_from.astimezone(
                            self.request.event.timezone
                        ),
                        "DATETIME_FORMAT",
                    )
                ),
            )
            return redirect(
                eventreverse(
                    self.request.event,
                    "plugins:pretix_vacc_autosched:second.index",
                )
            )

        first_date = position.subevent.date_from.date()
        min_date = max(first_date + dt.timedelta(days=config.days), now().date())
        max_date = first_date + dt.timedelta(days=config.max_days if config.max_days is not None else 1)

        self.other_event = config.event or position.order.event

        self.target_item, self.target_variation = get_for_other_event(position, self.other_event)
        subevents = self.other_event.subevents.filter(
            date_from__date__gte=min_date,
            date_from__date__lte=max_date,
        )
        quotas = Quota.objects.filter(
            subevent__in=subevents, items__id=self.target_item.pk
        )
        qa = QuotaAvailability()
        qa.queue(*quotas)
        qa.compute()
        available_subevents = []
        for subevent in subevents:
            qlist = [q for q in quotas if q.subevent_id == subevent.pk]
            if qlist and all(
                    qa.results[q][0] == Quota.AVAILABILITY_OK for q in qlist
            ):
                available_subevents.append(subevent)

        self.subevents = available_subevents

        if not self.subevents:
            messages.error(
                request,
                _(
                    "Unfortunately, there is currently no available slot for a second appointment."
                ),
            )
            return redirect(
                eventreverse(
                    self.request.event,
                    "plugins:pretix_vacc_autosched:second.index",
                )
            )

        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        result = super().get_form_kwargs()
        result["position"] = self.position
        result["available_subevents"] = self.subevents
        result["event"] = self.other_event
        return result

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        result["order"] = self.order
        return result

    def form_valid(self, form):
        from .tasks import book_second_dose

        subevent = form.cleaned_data["subevent"]
        order = book_second_dose(
            op=self.position,
            item=self.target_item,
            variation=self.target_variation,
            subevent=subevent,
            original_event=self.request.event,
        )
        if order:
            messages.success(self.request, _("Your appointment has been booked. We've sent you the details via email."))
            return render(self.request, "pretix_vacc_autosched/thanks.html", context=self.get_context_data())
        else:
            messages.error(
                self.request,
                _(
                    "There was an error when booking your second dose, please try again."
                ),
            )
            return self.form_invalid(form)
