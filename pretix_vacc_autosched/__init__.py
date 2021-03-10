from django.utils.translation import gettext_lazy

try:
    from pretix.base.plugins import PluginConfig
except ImportError:
    raise RuntimeError("Please use pretix 2.7 or above to run this plugin!")

__version__ = "1.0.0"


class PluginApp(PluginConfig):
    name = "pretix_vacc_utils"
    verbose_name = "Vaccination Utilities"

    class PretixPluginMeta:
        name = gettext_lazy("Vaccination Utilities")
        author = "pretix team"
        description = gettext_lazy("Various vaccination utilities")
        visible = True
        version = __version__
        category = "FEATURE"
        compatibility = "pretix>=3.15.0"

    def ready(self):
        from . import signals  # NOQA


default_app_config = "pretix_vacc_utils.PluginApp"
