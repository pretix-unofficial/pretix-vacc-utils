from django.db import models
from django.utils.translation import gettext_lazy as _
from pretix.base.models import OrderPosition


class ItemConfig(models.Model):
    item = models.OneToOneField(
        "pretixbase.Item",
        related_name="vacc_autosched_config",
        on_delete=models.CASCADE,
    )
    days = models.IntegerField(
        verbose_name=_("Scheduling of second dose: Number of days"),
        help_text=_("Keep empty to turn feature off"),
    )
    max_days = models.IntegerField(
        verbose_name=_("Scheduling of second dose: Maximum number of days"),
        help_text=_("Used in the self-service functionality."),
        null=True,
        blank=True,
    )
    event = models.ForeignKey(
        "pretixbase.Event",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_("Scheduling of second dose: Event series to choose date from"),
        help_text=_("If empty, the current series will be used"),
    )


class LinkedOrderPosition(models.Model):
    base_position = models.ForeignKey(
        OrderPosition, related_name="vacc_autosched_linked", on_delete=models.PROTECT
    )
    child_position = models.OneToOneField(
        OrderPosition, related_name="vacc_autosched_link", on_delete=models.PROTECT
    )
