import copy
from django.dispatch import receiver
from django.urls import resolve, reverse
from django.utils.translation import ugettext_lazy as _
from pretix.base.signals import event_copy_data, item_copy_data
from pretix.control.signals import item_forms, nav_event_settings

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
