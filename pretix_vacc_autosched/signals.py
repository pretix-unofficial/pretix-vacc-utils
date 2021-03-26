import copy
from django.dispatch import receiver
from django.urls import resolve, reverse
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_noop, ugettext_lazy as _
from i18nfield.strings import LazyI18nString
from pretix.base.settings import settings_hierarkey
from pretix.base.signals import (
    checkin_created,
    event_copy_data,
    item_copy_data,
    logentry_display,
)
from pretix.control.signals import item_forms, nav_event_settings

from pretix_vacc_autosched.tasks import schedule_second_dose

from .forms import ItemConfigForm
from .models import ItemConfig


@receiver(nav_event_settings, dispatch_uid="vacc_autosched_nav")
def navbar_info(sender, request, **kwargs):
    url = resolve(request.path_info)
    if not request.user.has_event_permission(
        request.organizer, request.event, "can_change_event_settings", request=request
    ):
        return []
    return [
        {
            "label": _("Vaccination scheduling"),
            "url": reverse(
                "plugins:pretix_vacc_autosched:settings",
                kwargs={
                    "event": request.event.slug,
                    "organizer": request.organizer.slug,
                },
            ),
            "active": url.namespace == "plugins:pretix_vacc_autosched",
        }
    ]


@receiver(item_forms, dispatch_uid="vacc_autosched_item_forms")
def control_item_forms(sender, request, item, **kwargs):
    try:
        inst = ItemConfig.objects.get(item=item)
    except ItemConfig.DoesNotExist:
        inst = ItemConfig(item=item)
    return ItemConfigForm(
        instance=inst,
        event=sender,
        data=(request.POST if request.method == "POST" else None),
        prefix="vacc_autosched_conf",
    )


@receiver(item_copy_data, dispatch_uid="vacc_autosched_item_copy")
def copy_item(sender, source, target, **kwargs):
    try:
        inst = ItemConfig.objects.get(item=source)
        inst = copy.copy(inst)
        inst.pk = None
        inst.item = target
        inst.save()
    except ItemConfig.DoesNotExist:
        pass


@receiver(signal=event_copy_data, dispatch_uid="vacc_autosched_copy_data")
def event_copy_data_receiver(sender, other, question_map, item_map, **kwargs):
    for ip in ItemConfig.objects.filter(item__event=other):
        ip = copy.copy(ip)
        ip.pk = None
        ip.item = item_map[ip.item_id]
        ip.save()


@receiver(signal=checkin_created, dispatch_uid="vacc_autosched_checkin_created")
def checkin_created_receiver(sender, checkin, **kwargs):
    if checkin.list.name.startswith("Print"):
        return  # ignore, not a "real" check-in
    if not sender.settings.vacc_autosched_checkin:
        return  # ignore, handled manually

    try:
        ItemConfig.objects.get(item=checkin.position.item)
    except ItemConfig.DoesNotExist:
        return  # ignore, not configured

    schedule_second_dose.apply_async(
        args=(
            sender.pk,
            checkin.position.pk,
        )
    )


@receiver(signal=logentry_display, dispatch_uid="vacc_autosched_logentry_display")
def badges_logentry_display(sender, logentry, **kwargs):
    if not logentry.action_type.startswith("pretix_vacc_autosched."):
        return

    d = logentry.parsed_data
    if logentry.action_type == "pretix_vacc_autosched.failed":
        return _("Automatic scheduling of second dose failed: {reason}").format(
            reason=d.get("reason")
        )
    if logentry.action_type == "pretix_vacc_autosched.scheduled":
        url = reverse(
            "control:event.order",
            kwargs={
                "event": d.get("event_slug"),
                "organizer": logentry.organizer.slug,
                "code": d.get("order"),
            },
        )
        return mark_safe(
            _("Second dose scheduled automatically: {order}").format(
                order='<a href="{}">{}</a>'.format(url, d.get("order")),
            )
        )
    if logentry.action_type == "pretix_vacc_autosched.created":
        url = reverse(
            "control:event.order",
            kwargs={
                "event": d.get("event_slug"),
                "organizer": logentry.organizer.slug,
                "code": d.get("order"),
            },
        )
        return mark_safe(
            _(
                "This order has been scheduled as the second dose for order {order}"
            ).format(
                order='<a href="{}">{}</a>'.format(url, d.get("order")),
            )
        )


settings_hierarkey.add_default("vacc_autosched_mail", False, bool)
settings_hierarkey.add_default("vacc_autosched_self_service", False, bool)
settings_hierarkey.add_default(
    "vacc_autosched_self_service_info",
    "",
    LazyI18nString,
)
settings_hierarkey.add_default(
    "vacc_autosched_self_service_order_info",
    "",
    LazyI18nString,
)
settings_hierarkey.add_default(
    "vacc_autosched_subject",
    LazyI18nString.from_gettext(gettext_noop("Your second dose: {scheduled_datetime}")),
    LazyI18nString,
)
settings_hierarkey.add_default(
    "vacc_autosched_body",
    LazyI18nString.from_gettext(
        gettext_noop(
            "Hello,\n\n"
            "we scheduled your second dose for {scheduled_datetime}.\n\n"
            "Please find additional information in your ticket attached.\n\n"
            "Best regards,\n"
            "Your {event} team"
        )
    ),
    LazyI18nString,
)
settings_hierarkey.add_default("vacc_autosched_checkin", True, bool)
