from django.utils.translation import gettext_lazy
from . import __version__

try:
    from pretix.base.plugins import PluginConfig
except ImportError:
    raise RuntimeError("Please use pretix 2.7 or above to run this plugin!")


class PluginApp(PluginConfig):
    default = True
    name = "pretix_vacc_autosched"
    verbose_name = "Vaccination: Automatic scheduling of second dose"

    class PretixPluginMeta:
        name = gettext_lazy("Vaccination: Automatic scheduling of second dose")
        author = "pretix team"
        description = gettext_lazy("Automatic scheduling of second dose")
        visible = True
        version = __version__
        experimental = True
        category = "FEATURE"
        compatibility = "pretix>=4.4.0"

    def ready(self):
        from . import signals  # NOQA


