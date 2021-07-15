from django.conf.urls import url

from . import api
from .views import SelfServiceBookingView, SelfServiceIndexView, SettingsView

urlpatterns = [
    url(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/settings/vacc_autosched/$",
        SettingsView.as_view(),
        name="settings",
    ),
    url(
        r"^api/v1/organizers/(?P<organizer>[^/]+)/events/(?P<event>[^/]+)/items/(?P<item>[^/]+)/vacc_autosched/$",
        api.ItemView.as_view(),
        name="api.item",
    ),
]

event_patterns = [
    url(
        r"^2nd/(?P<order>[^/]+)/$",
        SelfServiceBookingView.as_view(),
        name="second.booking",
    ),
    url(
        r"^2nd/?$",
        SelfServiceIndexView.as_view(),
        name="second.index",
    ),
]
