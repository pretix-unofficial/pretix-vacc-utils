from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django_scopes.forms import SafeModelChoiceField

from .models import ItemConfig


class ItemConfigForm(forms.ModelForm):
    class Meta:
        model = ItemConfig
        fields = ["days", "event"]
        exclude = []
        field_classes = {"event": SafeModelChoiceField}

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop("event")
        instance = kwargs.get("instance")
        initial = kwargs.get("initial", {})

        super().__init__(*args, **kwargs)
        self.fields["event"].queryset = self.event.organizer.events.filter(
            has_subevents=True
        ).order_by("date_from")
        self.fields["days"].required = False
        self.fields["days"].widget.is_required = False

    def clean(self):
        data = super().clean()
        if data.get("event"):
            target_event = data["event"]
            has_item = (
                len(
                    [
                        n
                        for n in target_event.items.all()
                        if (n.internal_name or str(n.name))
                        == (
                            self.instance.item.internal_name
                            or str(self.instance.item.name)
                        )
                    ]
                )
                == 1
            )
            if not has_item:
                raise ValidationError(
                    _(
                        "You selected an event series that does not have product with the same name as this "
                        "product."
                    )
                )
        return data

    def save(self, commit=True):
        if self.cleaned_data["days"] is None:
            if self.instance.pk:
                self.instance.delete()
            else:
                return
        else:
            return super().save(commit=commit)
