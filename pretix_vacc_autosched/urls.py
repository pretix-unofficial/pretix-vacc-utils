from django.conf.urls import url

from .views import SelfServiceBookingView, SelfServiceIndexView, SettingsView

urlpatterns = [
    url(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/settings/vacc_autosched/$",
        SettingsView.as_view(),
        name="settings",
    ),
]

from pretix.multidomain import event_url

event_patterns = [
    event_url(
        r"^2nd",
        SelfServiceIndexView.as_view(),
        name="second.index",
    ),
    event_url(
        r"^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/2nd$",
        SelfServiceBookingView.as_view(),
        name="second.booking",
    ),
]
