import logging
from django.urls import reverse
from django.views.generic import FormView
from pretix.base.models import Event
from pretix.control.views.event import EventSettingsFormView, EventSettingsViewMixin

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
