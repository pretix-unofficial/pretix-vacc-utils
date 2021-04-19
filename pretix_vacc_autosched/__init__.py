from django.utils.translation import gettext_lazy

try:
    from pretix.base.plugins import PluginConfig
except ImportError:
    raise RuntimeError("Please use pretix 2.7 or above to run this plugin!")

__version__ = "2.0.2"


class PluginApp(PluginConfig):
    name = "pretix_vacc_autosched"
    verbose_name = "Vaccination: Automatic scheduling of second dose"

    class PretixPluginMeta:
        name = gettext_lazy("Vaccination: Automatic scheduling of second dose")
        author = "pretix team"
        description = gettext_lazy("Automatic scheduling of second dose")
        visible = True
        version = __version__
        category = "FEATURE"
        compatibility = "pretix>=3.15.0"

    def ready(self):
        from . import signals  # NOQA


default_app_config = "pretix_vacc_autosched.PluginApp"
