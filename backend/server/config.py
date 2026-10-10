"""Turns the environment into the values settings.py uses.

Kept out of settings.py so it can be tested by passing in a dict, without
re-importing the settings module.

There are two modes, chosen by the environment, not by a code change:

* Development (the default): exactly the setup the project had before this
  file existed. Nothing is required, the dev secret key and `ALLOWED_HOSTS = ["*"]`
  apply, there is no app key and no rate limit.
* Production: on when `DJANGO_ENV=production`, or when `K_SERVICE` is set (Cloud
  Run sets it in every container it starts, so a deploy cannot forget the switch).
  It is strict on purpose: a server that is open to the internet must not start
  with a placeholder secret, any Host header, or no app key. Each of those is an
  `ImproperlyConfigured` error that names the variable to set.
"""

from collections.abc import Mapping

from django.core.exceptions import ImproperlyConfigured

DEV_SECRET_KEY = "dev-secret-key-change-in-production"

# Per client, per minute. The hum routes render audio and can call paid APIs
# (Gemini, ElevenLabs), so they get a much tighter budget than the rest.
PRODUCTION_RATE_LIMIT_HUM = 30
PRODUCTION_RATE_LIMIT_DEFAULT = 120


def _number(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise ImproperlyConfigured(f"{name} must be a whole number, got {raw!r}") from None


def build_settings(env: Mapping[str, str]) -> dict:
    production = env.get("DJANGO_ENV") == "production" or bool(env.get("K_SERVICE"))
    app_key = env.get("APP_API_KEY", "")

    if not production:
        return {
            "IS_PRODUCTION": False,
            "DEBUG": env.get("DEBUG", "True") == "True",
            "SECRET_KEY": env.get("DJANGO_SECRET_KEY", DEV_SECRET_KEY),
            "ALLOWED_HOSTS": ["*"],
            "SECURE_PROXY_SSL_HEADER": None,
            "APP_API_KEY": app_key,
            "RATE_LIMIT_HUM_PER_MINUTE": _number(env, "RATE_LIMIT_HUM_PER_MINUTE", 0),
            "RATE_LIMIT_DEFAULT_PER_MINUTE": _number(env, "RATE_LIMIT_DEFAULT_PER_MINUTE", 0),
        }

    secret = env.get("DJANGO_SECRET_KEY", "")
    if not secret or secret == DEV_SECRET_KEY:
        raise ImproperlyConfigured("Production needs DJANGO_SECRET_KEY set to a real secret.")

    hosts = [h.strip() for h in env.get("ALLOWED_HOSTS", "").split(",") if h.strip()]
    if not hosts or "*" in hosts:
        raise ImproperlyConfigured(
            "Production needs ALLOWED_HOSTS set to the server's host names, comma separated (not '*')."
        )

    if not app_key:
        raise ImproperlyConfigured("Production needs APP_API_KEY: without it every route is open to anyone.")

    return {
        "IS_PRODUCTION": True,
        "DEBUG": False,
        "SECRET_KEY": secret,
        "ALLOWED_HOSTS": hosts,
        # Cloud Run ends TLS in front of the container and says so in this header.
        "SECURE_PROXY_SSL_HEADER": ("HTTP_X_FORWARDED_PROTO", "https"),
        "APP_API_KEY": app_key,
        "RATE_LIMIT_HUM_PER_MINUTE": _number(env, "RATE_LIMIT_HUM_PER_MINUTE", PRODUCTION_RATE_LIMIT_HUM),
        "RATE_LIMIT_DEFAULT_PER_MINUTE": _number(env, "RATE_LIMIT_DEFAULT_PER_MINUTE", PRODUCTION_RATE_LIMIT_DEFAULT),
    }
