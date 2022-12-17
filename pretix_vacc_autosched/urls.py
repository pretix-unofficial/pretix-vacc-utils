from django.urls import path, re_path

from . import api
from .views import SelfServiceBookingView, SelfServiceIndexView, SettingsView

urlpatterns = [
    path(
        "control/event/<str:organizer>/<str:event>/settings/vacc_autosched/",
        SettingsView.as_view(),
        name="settings",
    ),
    path(
        "api/v1/organizers/<str:organizer>/events/<str:event>/items/<str:item>/vacc_autosched/",
        api.ItemView.as_view(),
        name="api.item",
    ),
]

event_patterns = [
    path(
        "2nd/<str:order>/",
        SelfServiceBookingView.as_view(),
        name="second.booking",
    ),
    re_path(
        r"^2nd/?$",
        SelfServiceIndexView.as_view(),
        name="second.index",
    ),
]
