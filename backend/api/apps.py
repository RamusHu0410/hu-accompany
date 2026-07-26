import os
import sys

from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "api"

    def ready(self):
        # Only advertise while actually serving requests: skip management
        # commands (migrate, shell, etc.) and, under the autoreloader,
        # skip the watcher process (RUN_MAIN is only set in the child that
        # actually serves) so we don't register the service twice.
        is_runserver = len(sys.argv) > 1 and sys.argv[1] == "runserver"
        if not is_runserver:
            return
        if os.environ.get("RUN_MAIN") != "true" and "--noreload" not in sys.argv:
            return

        from . import mdns

        port = int(os.environ.get("API_PORT", "8000"))
        mdns.start(port=port)
