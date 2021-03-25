import logging
from django.http import Http404
from django.urls import reverse
from django.views.generic import FormView
from pretix.base.models import Event
from pretix.control.views.event import EventSettingsFormView, EventSettingsViewMixin
from pretix.presale.views import EventViewMixin
from pretix.presale.views.order import OrderDetailMixin

from .forms import AutoschedSettingsForm

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


class SecondDoseMixin:
    def dispatch(self, request, *args, **kwargs):
        if not request.settings.vacc_autosched_self_service:
            raise Http404()
        return super().dispatch(request, *args, **kwargs)


class SecondIndexView(SecondDoseMixin, EventViewMixin, FormView):
    pass


class SecondBookingView(SecondDoseMixin, OrderDetailMixin, FormView):
    pass
