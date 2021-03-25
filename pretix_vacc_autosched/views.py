import logging
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import FormView
from pretix.base.models import Event
from pretix.control.views.event import EventSettingsFormView, EventSettingsViewMixin
from pretix.presale.views import EventViewMixin
from pretix.presale.views.order import OrderDetailMixin

from .forms import AutoschedSettingsForm, SecondDoseCodeForm

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
    pass
