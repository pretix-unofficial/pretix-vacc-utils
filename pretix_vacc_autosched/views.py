import logging
from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView
from pretix.base.models import Event
from pretix.control.views.event import EventSettingsFormView, EventSettingsViewMixin
from pretix.presale.views import EventViewMixin
from pretix.presale.views.order import OrderDetailMixin

from pretix_vacc_autosched.forms import (
    AutoschedSettingsForm,
    SecondDoseCodeForm,
    SecondDoseOrderForm,
)
from pretix_vacc_autosched.models import LinkedOrderPosition

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
            raise Http404()
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
            "plugins:pretix_vacc_autosched:second.booking",
            organizer=self.request.event.organizer.slug,
            event=self.request.event.slug,
            order=order.code,
            secret=order.secret,
        )


class SelfServiceBookingView(SelfServiceMixin, OrderDetailMixin, FormView):
    form_class = SecondDoseOrderForm
    template_name = "pretix_vacc_autosched/self_service_order.html"

    def dispatch(self, request, *args, **kwargs):
        if self.order.status != self.order.STATUS_PAID:
            raise Http404()

        position = (
            self.order.positions.first()
        )  # We assume that there's only one position per order
        if (
            not position.subevent
            or not position.subevent.date_from.date() <= now().date()
        ):
            raise Http404()
        config = getattr(position.item, "vacc_autosched_config", None)
        if not config or not config.days or not position.subevent:
            raise Http404()
        self.position = position
        link = LinkedOrderPosition.objects.filter(base_position=position).first()
        if link:
            order = link.child_position.order
            return redirect(
                "presale:event.order",
                organizer=order.event.organizer.slug,
                event=order.event.slug,
                order=order.code,
                secret=order.secret,
            )
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        result = super().get_form_kwargs()
        result["position"] = self.position
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
            item=form.target_item,
            variation=form.target_variation,
            subevent=subevent,
            original_event=self.request.event,
        )
        if order:
            messages.success(self.request, _("Your appointment has been booked."))
            return redirect(
                "presale:event.order",
                organizer=order.event.organizer.slug,
                event=order.event.slug,
                order=self.order.code,
                secret=self.order.secret,
            )
        else:
            messages.error(
                self.request,
                _(
                    "There was an error when booking your second dose, please try again."
                ),
            )
            return self.form_invalid(form)
