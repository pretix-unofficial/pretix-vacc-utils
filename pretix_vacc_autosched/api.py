from django.db import transaction
from pretix.base.models import Event, Item
from rest_framework import serializers, status, views
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from pretix_vacc_autosched.models import ItemConfig


class ItemConfigSerializer(serializers.ModelSerializer):
    event = serializers.SlugRelatedField(
        slug_field="slug", queryset=Event.objects.none()
    )

    class Meta:
        model = ItemConfig
        fields = ["event", "days", "second_item", "max_days"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[
            "event"
        ].queryset = self.instance.item.event.organizer.events.filter(
            has_subevents=True
        )
        self.fields["second_item"].queryset = Item.objects.filter(
            event__organizer=self.instance.item.event.organizer
        )

    def validate(self, data):
        if data.get("second_item") and data.get("event"):
            if data.get("event") != data.get("second_item").event:
                raise serializers.ValidationError("Item does not exist in event")
        return data


class ItemView(views.APIView):
    permission = "can_change_items"

    def get(self, request, *args, **kwargs):
        item = get_object_or_404(request.event.items.all(), pk=kwargs.get("item"))

        try:
            instance = item.vacc_autosched_config
        except ItemConfig.DoesNotExist:
            return Response({})
        else:
            s = ItemConfigSerializer(instance=instance)
            return Response(s.data)

    def delete(self, request, *args, **kwargs):
        item = get_object_or_404(request.event.items.all(), pk=kwargs.get("item"))

        try:
            instance = item.vacc_autosched_config
        except ItemConfig.DoesNotExist:
            return Response({})
        else:
            with transaction.atomic():
                instance.delete()
                item.log_action(
                    "pretix.event.item.changed", user=self.request.user, data={}
                )
            return Response(status=status.HTTP_204_NO_CONTENT)

    def put(self, request, *args, **kwargs):
        item = get_object_or_404(request.event.items.all(), pk=kwargs.get("item"))

        try:
            instance = item.vacc_autosched_config
        except ItemConfig.DoesNotExist:
            instance = ItemConfig(item=item)

        s = ItemConfigSerializer(instance=instance, data=request.data)
        s.is_valid(raise_exception=True)
        with transaction.atomic():
            s.save()
            item.log_action(
                "pretix.event.item.changed", user=self.request.user, data=request.data
            )
        s = ItemConfigSerializer(instance=instance)
        return Response(s.data)
