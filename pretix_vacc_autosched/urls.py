from django.conf.urls import url

from .views import SettingsView

urlpatterns = [
    url(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/settings/vacc_autosched/$",
        SettingsView.as_view(),
        name="settings",
    ),
]
