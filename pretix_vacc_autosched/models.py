from django.db import models
from django.utils.translation import gettext_lazy as _


class ItemConfig(models.Model):
    item = models.OneToOneField(
        "pretixbase.Item",
        related_name="vacc_sautosched_config",
        on_delete=models.CASCADE,
    )
    days = models.IntegerField(
        verbose_name=_("Scheduling of second dose: Number of days"),
        help_text=_("Keep empty to turn feature off"),
    )
    event = models.ForeignKey(
        "pretixbase.Event",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_("Scheduling of second dose: Event series to choose date from"),
        help_text=_("If empty, the current series will be used"),
    )
