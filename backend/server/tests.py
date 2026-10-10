"""Tests for what stands between the internet and the backend: production
settings, the health check, the app key, the rate limit, /storage/, and the
quiz route.

Run with:  python manage.py test server

None of these touch the database. Most use the small URL config at the bottom
of this file so they don't depend on the audio stack; `RealUrlConfTests` runs
the real `server.urls` and so needs the full production requirements.
"""

import tempfile
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse, JsonResponse
from django.test import Client, RequestFactory, SimpleTestCase, override_settings
from django.urls import path

from server.config import build_settings
from server.middleware import RateLimiter

PROD = {
    "DJANGO_ENV": "production",
    "DJANGO_SECRET_KEY": "a-real-secret",
    "ALLOWED_HOSTS": "api.example.com",
    "APP_API_KEY": "app-key",
}


class ConfigTests(SimpleTestCase):
    """build_settings(env) turns the environment into the values settings.py uses.
    It is separate from settings.py so it can be tested without re-importing it."""

    def test_with_nothing_set_it_is_exactly_the_old_development_setup(self):
        cfg = build_settings({})
        self.assertIs(cfg["IS_PRODUCTION"], False)
        self.assertIs(cfg["DEBUG"], True)
        self.assertEqual(cfg["SECRET_KEY"], "dev-secret-key-change-in-production")
        self.assertEqual(cfg["ALLOWED_HOSTS"], ["*"])
        self.assertIsNone(cfg["SECURE_PROXY_SSL_HEADER"])
        self.assertEqual(cfg["APP_API_KEY"], "")

    def test_development_still_honours_the_old_variables(self):
        cfg = build_settings({"DEBUG": "False", "DJANGO_SECRET_KEY": "mine"})
        self.assertIs(cfg["DEBUG"], False)
        self.assertEqual(cfg["SECRET_KEY"], "mine")

    def test_development_has_no_rate_limit_unless_asked(self):
        cfg = build_settings({})
        self.assertEqual(cfg["RATE_LIMIT_HUM_PER_MINUTE"], 0)
        self.assertEqual(cfg["RATE_LIMIT_DEFAULT_PER_MINUTE"], 0)
        cfg = build_settings({"RATE_LIMIT_HUM_PER_MINUTE": "5"})
        self.assertEqual(cfg["RATE_LIMIT_HUM_PER_MINUTE"], 5)

    def test_production_switch_by_django_env(self):
        self.assertIs(build_settings(PROD)["IS_PRODUCTION"], True)

    def test_production_switch_by_cloud_run(self):
        # Cloud Run sets K_SERVICE in every container it starts.
        env = {k: v for k, v in PROD.items() if k != "DJANGO_ENV"} | {"K_SERVICE": "hu-accompany"}
        self.assertIs(build_settings(env)["IS_PRODUCTION"], True)

    def test_production_is_never_in_debug_mode(self):
        self.assertIs(build_settings(PROD | {"DEBUG": "True"})["DEBUG"], False)

    def test_production_trusts_the_proxys_https_header(self):
        self.assertEqual(build_settings(PROD)["SECURE_PROXY_SSL_HEADER"], ("HTTP_X_FORWARDED_PROTO", "https"))

    def test_production_reads_hosts_from_a_comma_list(self):
        cfg = build_settings(PROD | {"ALLOWED_HOSTS": " api.example.com , b.example.com ,"})
        self.assertEqual(cfg["ALLOWED_HOSTS"], ["api.example.com", "b.example.com"])

    def test_production_refuses_to_start_without_a_real_secret_key(self):
        without = {k: v for k, v in PROD.items() if k != "DJANGO_SECRET_KEY"}
        with self.assertRaisesMessage(ImproperlyConfigured, "DJANGO_SECRET_KEY"):
            build_settings(without)
        with self.assertRaisesMessage(ImproperlyConfigured, "DJANGO_SECRET_KEY"):
            build_settings(PROD | {"DJANGO_SECRET_KEY": "dev-secret-key-change-in-production"})

    def test_production_refuses_to_start_without_allowed_hosts(self):
        without = {k: v for k, v in PROD.items() if k != "ALLOWED_HOSTS"}
        with self.assertRaisesMessage(ImproperlyConfigured, "ALLOWED_HOSTS"):
            build_settings(without)
        with self.assertRaisesMessage(ImproperlyConfigured, "ALLOWED_HOSTS"):
            build_settings(PROD | {"ALLOWED_HOSTS": "*"})

    def test_production_refuses_to_start_without_an_app_key(self):
        without = {k: v for k, v in PROD.items() if k != "APP_API_KEY"}
        with self.assertRaisesMessage(ImproperlyConfigured, "APP_API_KEY"):
            build_settings(without)

    def test_production_has_rate_limits_by_default_and_they_can_be_changed(self):
        cfg = build_settings(PROD)
        self.assertGreater(cfg["RATE_LIMIT_HUM_PER_MINUTE"], 0)
        self.assertGreater(cfg["RATE_LIMIT_DEFAULT_PER_MINUTE"], cfg["RATE_LIMIT_HUM_PER_MINUTE"])
        self.assertEqual(build_settings(PROD | {"RATE_LIMIT_HUM_PER_MINUTE": "7"})["RATE_LIMIT_HUM_PER_MINUTE"], 7)

    def test_a_rate_limit_that_is_not_a_number_is_reported_by_name(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "RATE_LIMIT_HUM_PER_MINUTE"):
            build_settings(PROD | {"RATE_LIMIT_HUM_PER_MINUTE": "lots"})


class RateLimiterTests(SimpleTestCase):
    def setUp(self):
        self.now = 1000.0
        self.limiter = RateLimiter(clock=lambda: self.now, window=60.0)

    def test_allows_up_to_the_limit_then_says_how_long_to_wait(self):
        self.assertEqual([self.limiter.check("a", 3) for _ in range(3)], [0.0, 0.0, 0.0])
        self.now += 10
        self.assertAlmostEqual(self.limiter.check("a", 3), 50.0)

    def test_the_window_slides(self):
        for _ in range(3):
            self.limiter.check("a", 3)
        self.now += 61
        self.assertEqual(self.limiter.check("a", 3), 0.0)

    def test_clients_do_not_share_a_budget(self):
        for _ in range(3):
            self.limiter.check("a", 3)
        self.assertGreater(self.limiter.check("a", 3), 0)
        self.assertEqual(self.limiter.check("b", 3), 0.0)

    def test_a_rejected_request_does_not_extend_the_wait(self):
        for _ in range(3):
            self.limiter.check("a", 3)
        self.now += 50
        for _ in range(10):  # refused, late in the window
            self.assertGreater(self.limiter.check("a", 3), 0)
        self.now += 11  # 61 s after the three allowed hits, 11 s after the refused ones
        self.assertEqual(self.limiter.check("a", 3), 0.0)

    def test_a_limit_of_zero_means_unlimited(self):
        self.assertTrue(all(self.limiter.check("a", 0) == 0.0 for _ in range(100)))

    def test_memory_is_bounded_when_many_clients_come_and_go(self):
        small = RateLimiter(clock=lambda: self.now, window=60.0, max_keys=50)
        for i in range(500):
            small.check(f"client-{i}", 5)
            self.now += 1
        self.assertLessEqual(len(small), 50 + 60)  # only clients seen inside the window can remain


def _ok(request, *args, **kwargs):
    return JsonResponse({"ok": True})


urlpatterns = [
    path("api/ping", _ok),
    path("api/hum/ping", _ok),
    path("api/hum/talk/speech/<str:reply_id>", _ok),
]

GATE = [
    "server.middleware.HealthCheckMiddleware",
    "server.middleware.RateLimitMiddleware",
    "server.middleware.AppKeyMiddleware",
]
# With Django's own middleware behind it, which is what refuses unknown Host headers.
CHAIN = GATE + ["django.middleware.common.CommonMiddleware"]


@override_settings(ROOT_URLCONF="server.tests", MIDDLEWARE=CHAIN, APP_API_KEY="", ALLOWED_HOSTS=["testserver"],
                   RATE_LIMIT_HUM_PER_MINUTE=0, RATE_LIMIT_DEFAULT_PER_MINUTE=0)
class MiddlewareTests(SimpleTestCase):
    def fresh_client(self):
        return Client()  # a new client loads the middleware chain with the current settings

    # -- health check --------------------------------------------------------
    def test_healthz_answers_without_a_key_and_from_any_host(self):
        with override_settings(APP_API_KEY="secret"):
            response = self.fresh_client().get("/healthz", HTTP_HOST="10.1.2.3")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")

    def test_healthz_is_never_rate_limited(self):
        with override_settings(RATE_LIMIT_DEFAULT_PER_MINUTE=1):
            c = self.fresh_client()
            self.assertTrue(all(c.get("/healthz").status_code == 200 for _ in range(5)))

    def test_other_routes_do_refuse_an_unknown_host_so_the_health_pass_means_something(self):
        self.assertEqual(self.fresh_client().get("/api/ping", HTTP_HOST="10.1.2.3").status_code, 400)

    # -- app key --------------------------------------------------------------
    def test_without_a_configured_key_everything_is_open(self):
        self.assertEqual(self.fresh_client().get("/api/ping").status_code, 200)

    def test_requests_need_the_right_key(self):
        with override_settings(APP_API_KEY="secret"):
            c = self.fresh_client()
            missing = c.get("/api/ping")
            wrong = c.get("/api/ping", HTTP_X_APP_KEY="nope")
            right = c.get("/api/ping", HTTP_X_APP_KEY="secret")
        self.assertEqual((missing.status_code, wrong.status_code, right.status_code), (401, 401, 200))
        self.assertEqual(missing.json()["code"], "unauthorized")
        self.assertIn("error", missing.json())  # the app shows this text to the user

    def test_a_key_with_odd_characters_is_a_401_not_a_crash(self):
        with override_settings(APP_API_KEY="secret"):
            response = self.fresh_client().get("/api/ping", HTTP_X_APP_KEY="sécret☃")
        self.assertEqual(response.status_code, 401)

    def test_audio_playback_urls_work_without_a_header_but_only_for_get(self):
        # An audio player fetches the spoken reply itself and cannot send our header.
        # The reply id is 96 random bits and expires, so the URL is the credential.
        with override_settings(APP_API_KEY="secret"):
            c = self.fresh_client()
            self.assertEqual(c.get("/api/hum/talk/speech/abc123").status_code, 200)
            self.assertEqual(c.post("/api/hum/talk/speech/abc123").status_code, 401)

    # -- rate limit -----------------------------------------------------------
    def test_hum_routes_have_their_own_tighter_limit(self):
        with override_settings(RATE_LIMIT_HUM_PER_MINUTE=2, RATE_LIMIT_DEFAULT_PER_MINUTE=100):
            c = self.fresh_client()
            codes = [c.get("/api/hum/ping").status_code for _ in range(3)]
            other = c.get("/api/ping").status_code
        self.assertEqual(codes, [200, 200, 429])
        self.assertEqual(other, 200)

    def test_the_default_limit_covers_other_routes(self):
        with override_settings(RATE_LIMIT_DEFAULT_PER_MINUTE=2):
            c = self.fresh_client()
            self.assertEqual([c.get("/api/ping").status_code for _ in range(3)], [200, 200, 429])

    def test_a_429_says_when_to_retry(self):
        with override_settings(RATE_LIMIT_DEFAULT_PER_MINUTE=1):
            c = self.fresh_client()
            c.get("/api/ping")
            response = c.get("/api/ping")
        self.assertEqual(response.status_code, 429)
        self.assertGreaterEqual(int(response["Retry-After"]), 1)
        self.assertEqual(response.json()["code"], "rate_limited")
        self.assertIn("error", response.json())

    def test_clients_are_told_apart_by_the_address_the_proxy_appended(self):
        # Only the LAST X-Forwarded-For entry is added by the proxy; earlier ones are
        # whatever the caller wrote, so rotating them must not buy a fresh budget.
        with override_settings(RATE_LIMIT_DEFAULT_PER_MINUTE=1):
            c = self.fresh_client()
            first = c.get("/api/ping", HTTP_X_FORWARDED_FOR="1.1.1.1, 9.9.9.9")
            spoofed = c.get("/api/ping", HTTP_X_FORWARDED_FOR="2.2.2.2, 9.9.9.9")
            someone_else = c.get("/api/ping", HTTP_X_FORWARDED_FOR="3.3.3.3, 8.8.8.8")
        self.assertEqual((first.status_code, spoofed.status_code, someone_else.status_code), (200, 429, 200))

    def test_guessing_keys_is_throttled_before_the_key_is_even_checked(self):
        with override_settings(APP_API_KEY="secret", RATE_LIMIT_DEFAULT_PER_MINUTE=2):
            c = self.fresh_client()
            codes = [c.get("/api/ping", HTTP_X_APP_KEY="guess").status_code for _ in range(3)]
        self.assertEqual(codes, [401, 401, 429])


class StorageViewTests(SimpleTestCase):
    """/storage/ serves files by URL with no key and no listing of who may read them:
    right for local development, wrong on the internet (it holds feedback files)."""

    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        (Path(self.root.name) / "storage").mkdir()
        (Path(self.root.name) / "storage" / "hello.txt").write_text("hi")
        self.request = RequestFactory().get("/storage/hello.txt")

    def view(self, debug):
        from server.views import storage
        with override_settings(BASE_DIR=Path(self.root.name), DEBUG=debug):
            return storage(self.request, "hello.txt")

    def test_it_is_a_404_when_not_debugging(self):
        from django.http import Http404
        with self.assertRaises(Http404):
            self.view(debug=False)

    def test_it_still_serves_files_in_development(self):
        response = self.view(debug=True)
        self.assertEqual(b"".join(response.streaming_content), b"hi")


@override_settings(ROOT_URLCONF="api.urls", MIDDLEWARE=[])
class QuizRouteTests(SimpleTestCase):
    def test_the_quiz_routes_exist(self):
        c = Client()
        response = c.post("/api/quiz/generate", {"topic": "baroque", "length": 5, "seed": 1}, content_type="application/json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(response.json()["questions"]), 5)
        self.assertEqual(c.get("/api/quiz/topics").status_code, 200)

    def test_the_existing_api_routes_are_still_there(self):
        response = Client().post("/api/feedback/phrase", "not json", content_type="application/json")
        self.assertEqual(response.status_code, 400)


@override_settings(ALLOWED_HOSTS=["testserver"], APP_API_KEY="secret", DEBUG=False,
                   RATE_LIMIT_HUM_PER_MINUTE=0, RATE_LIMIT_DEFAULT_PER_MINUTE=0)
class RealUrlConfTests(SimpleTestCase):
    """The actual server.urls and the middleware list in settings.py, together."""

    def test_settings_put_the_gate_in_front_of_everything(self):
        from django.conf import settings
        self.assertEqual(list(settings.MIDDLEWARE), CHAIN)

    def test_the_health_check_works_with_no_key(self):
        self.assertEqual(Client().get("/healthz").status_code, 200)

    def test_a_real_route_is_closed_without_the_key_and_open_with_it(self):
        c = Client()
        self.assertEqual(c.get("/api/scores/search?q=bach").status_code, 401)
        self.assertEqual(c.get("/api/quiz/topics", HTTP_X_APP_KEY="secret").status_code, 200)

    def test_storage_is_not_served_in_production_even_with_the_key(self):
        self.assertEqual(Client().get("/storage/feedback/x.json", HTTP_X_APP_KEY="secret").status_code, 404)
