"""Тесты авторизации по email и защиты API.

Запуск из корня проекта:
    .\\myvenv\\Scripts\\python.exe -m unittest discover -s DefultCredit/tests -v
"""

from __future__ import annotations

import os
import tempfile
import unittest
import uuid

_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["FINHELL_DB_PATH"] = os.path.join(_TEMP_DIR.name, "auth-test.db")
os.environ["FINHELL_AUTH_SECRET"] = "finhell-test-secret"
os.environ["FINHELL_PBKDF2_ITERATIONS"] = "1000"
os.environ["FINHELL_AD_DURATION_SECONDS"] = "0"
os.environ["FINHELL_AD_COOLDOWN_SECONDS"] = "0"
os.environ["FINHELL_AD_DAILY_LIMIT"] = "1000"

from fastapi.testclient import TestClient  # noqa: E402

from DefultCredit.optimizer import auth as auth_service  # noqa: E402
from DefultCredit.simulator import app  # noqa: E402


def unique_email() -> str:
    return f"user-{uuid.uuid4().hex[:12]}@example.com"


class AuthApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def register(
        self,
        email: str | None = None,
        password: str = "password123",
        name: str = "Тест",
    ):
        email = email or unique_email()
        response = self.client.post(
            "/api/v2/auth/register",
            json={"email": email, "password": password, "name": name},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json(), email, password

    def auth_headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def watch_ad(self, token: str) -> dict:
        started = self.client.post(
            "/api/v2/tokens/ad/start",
            headers=self.auth_headers(token),
        )
        self.assertEqual(started.status_code, 200, started.text)
        session = started.json()
        completed = self.client.post(
            "/api/v2/tokens/ad/complete",
            json={"session_id": session["session_id"]},
            headers=self.auth_headers(token),
        )
        self.assertEqual(completed.status_code, 200, completed.text)
        return completed.json()

    def test_register_login_and_me(self) -> None:
        email = unique_email().upper()
        payload, normalized_email, password = self.register(email=email)
        self.assertEqual(payload["user"]["email"], normalized_email.lower())
        self.assertEqual(payload["token_type"], "bearer")
        self.assertGreater(payload["expires_in"], 0)
        self.assertTrue(payload["token"])

        me = self.client.get(
            "/api/v2/auth/me",
            headers=self.auth_headers(payload["token"]),
        )
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["user"]["email"], normalized_email.lower())

        login = self.client.post(
            "/api/v2/auth/login",
            json={"email": normalized_email, "password": password},
        )
        self.assertEqual(login.status_code, 200, login.text)
        self.assertTrue(login.json()["token"])

    def test_me_requires_token(self) -> None:
        response = self.client.get("/api/v2/auth/me")
        self.assertEqual(response.status_code, 401)
        self.assertIn("авторизация", response.json()["detail"].lower())

        response = self.client.get(
            "/api/v2/auth/me",
            headers={"Authorization": "Bearer broken.token"},
        )
        self.assertEqual(response.status_code, 401)

    def test_duplicate_email(self) -> None:
        email = unique_email()
        self.register(email=email)
        response = self.client.post(
            "/api/v2/auth/register",
            json={"email": email, "password": "password123"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("уже зарегистрирован", response.json()["detail"])

    def test_validation(self) -> None:
        bad_email = self.client.post(
            "/api/v2/auth/register",
            json={"email": "not-an-email", "password": "password123"},
        )
        self.assertEqual(bad_email.status_code, 422)

        weak_password = self.client.post(
            "/api/v2/auth/register",
            json={"email": unique_email(), "password": "short"},
        )
        self.assertEqual(weak_password.status_code, 422)

    def test_wrong_password(self) -> None:
        payload, email, _password = self.register()
        response = self.client.post(
            "/api/v2/auth/login",
            json={"email": email, "password": "wrong-password"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn("неверный", response.json()["detail"].lower())

    def test_tampered_token(self) -> None:
        payload, _email, _password = self.register()
        token = payload["token"]
        tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
        response = self.client.get(
            "/api/v2/auth/me",
            headers=self.auth_headers(tampered),
        )
        self.assertEqual(response.status_code, 401)

    def test_optimize_requires_auth(self) -> None:
        request = {
            "profile": {"capital": 500_000, "monthly": 20_000, "horizon_months": 12},
            "options": {"monte_carlo_paths": 100, "max_scenarios": 10},
        }
        response = self.client.post("/api/v2/optimize", json=request)
        self.assertEqual(response.status_code, 401)

        payload, _email, _password = self.register()
        response = self.client.post(
            "/api/v2/optimize",
            json=request,
            headers=self.auth_headers(payload["token"]),
        )
        self.assertEqual(response.status_code, 402, response.text)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "insufficient_tokens")
        self.assertEqual(detail["tokens"], 0)

        earned = self.watch_ad(payload["token"])
        self.assertEqual(earned["tokens"], auth_service.AD_REWARD_TOKENS)

        response = self.client.post(
            "/api/v2/optimize",
            json=request,
            headers=self.auth_headers(payload["token"]),
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertIn("risk_profiles", body)
        self.assertIn("context_id", body)

        status = self.client.get(
            "/api/v2/tokens",
            headers=self.auth_headers(payload["token"]),
        )
        self.assertEqual(status.status_code, 200, status.text)
        self.assertEqual(
            status.json()["tokens"],
            auth_service.AD_REWARD_TOKENS - auth_service.CALCULATION_COST_TOKENS,
        )

    def test_async_job_belongs_to_user(self) -> None:
        owner, _email, _password = self.register()
        other, _email2, _password2 = self.register()
        self.watch_ad(owner["token"])
        self.watch_ad(other["token"])
        request = {
            "profile": {"capital": 500_000, "monthly": 20_000, "horizon_months": 12},
            "options": {"monte_carlo_paths": 100, "max_scenarios": 10},
        }
        created = self.client.post(
            "/api/v2/optimize/async",
            json=request,
            headers=self.auth_headers(owner["token"]),
        )
        self.assertEqual(created.status_code, 202, created.text)
        created_body = created.json()
        job_id = created_body["job_id"]
        self.assertEqual(
            created_body["tokens"],
            auth_service.AD_REWARD_TOKENS - auth_service.CALCULATION_COST_TOKENS,
        )

        owner_status = self.client.get(
            f"/api/v2/jobs/{job_id}",
            headers=self.auth_headers(owner["token"]),
        )
        self.assertEqual(owner_status.status_code, 200, owner_status.text)

        other_status = self.client.get(
            f"/api/v2/jobs/{job_id}",
            headers=self.auth_headers(other["token"]),
        )
        self.assertEqual(other_status.status_code, 404)

        other_jobs = self.client.get(
            "/api/v2/jobs",
            headers=self.auth_headers(other["token"]),
        )
        self.assertEqual(other_jobs.status_code, 200)
        self.assertNotIn(job_id, {job["job_id"] for job in other_jobs.json()})

        owner_jobs = self.client.get(
            "/api/v2/jobs",
            headers=self.auth_headers(owner["token"]),
        )
        self.assertEqual(owner_jobs.status_code, 200)
        self.assertIn(job_id, {job["job_id"] for job in owner_jobs.json()})

    # ------------------------------------------------------------------
    # Токен-экономика
    # ------------------------------------------------------------------

    def test_tokens_endpoints_require_auth(self) -> None:
        self.assertEqual(self.client.get("/api/v2/tokens").status_code, 401)
        self.assertEqual(
            self.client.post("/api/v2/tokens/ad/start").status_code,
            401,
        )

    def test_new_account_starts_with_zero_tokens(self) -> None:
        payload, _email, _password = self.register()
        status = self.client.get(
            "/api/v2/tokens",
            headers=self.auth_headers(payload["token"]),
        )
        self.assertEqual(status.status_code, 200, status.text)
        body = status.json()
        self.assertEqual(body["tokens"], 0)
        self.assertEqual(body["calculation_cost"], auth_service.CALCULATION_COST_TOKENS)
        self.assertEqual(body["ad_reward"], auth_service.AD_REWARD_TOKENS)
        self.assertEqual(body["ads_today"], 0)
        self.assertTrue(body["can_watch_ad"])

    def test_ad_reward_and_double_complete(self) -> None:
        payload, _email, _password = self.register()
        token = payload["token"]

        started = self.client.post(
            "/api/v2/tokens/ad/start",
            headers=self.auth_headers(token),
        )
        self.assertEqual(started.status_code, 200, started.text)
        session = started.json()
        self.assertEqual(session["reward"], auth_service.AD_REWARD_TOKENS)
        self.assertFalse(session["resumed"])

        completed = self.client.post(
            "/api/v2/tokens/ad/complete",
            json={"session_id": session["session_id"]},
            headers=self.auth_headers(token),
        )
        self.assertEqual(completed.status_code, 200, completed.text)
        self.assertEqual(completed.json()["tokens"], auth_service.AD_REWARD_TOKENS)
        self.assertEqual(completed.json()["ads_today"], 1)

        again = self.client.post(
            "/api/v2/tokens/ad/complete",
            json={"session_id": session["session_id"]},
            headers=self.auth_headers(token),
        )
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.json()["detail"]["code"], "ad_session_invalid")

        status = self.client.get(
            "/api/v2/tokens",
            headers=self.auth_headers(token),
        )
        self.assertEqual(status.json()["tokens"], auth_service.AD_REWARD_TOKENS)

    def test_ad_start_resumes_active_session(self) -> None:
        payload, _email, _password = self.register()
        token = payload["token"]
        first = self.client.post(
            "/api/v2/tokens/ad/start",
            headers=self.auth_headers(token),
        ).json()
        second = self.client.post(
            "/api/v2/tokens/ad/start",
            headers=self.auth_headers(token),
        )
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["session_id"], first["session_id"])
        self.assertTrue(second.json()["resumed"])

    def test_ad_not_finished_cannot_be_completed(self) -> None:
        previous = auth_service.AD_DURATION_SECONDS
        auth_service.AD_DURATION_SECONDS = 60
        try:
            payload, _email, _password = self.register()
            token = payload["token"]
            session = self.client.post(
                "/api/v2/tokens/ad/start",
                headers=self.auth_headers(token),
            ).json()
            response = self.client.post(
                "/api/v2/tokens/ad/complete",
                json={"session_id": session["session_id"]},
                headers=self.auth_headers(token),
            )
            self.assertEqual(response.status_code, 409, response.text)
            self.assertEqual(
                response.json()["detail"]["code"],
                "ad_not_finished",
            )
        finally:
            auth_service.AD_DURATION_SECONDS = previous

    def test_ad_cooldown(self) -> None:
        previous = auth_service.AD_COOLDOWN_SECONDS
        auth_service.AD_COOLDOWN_SECONDS = 60
        try:
            payload, _email, _password = self.register()
            token = payload["token"]
            self.watch_ad(token)
            response = self.client.post(
                "/api/v2/tokens/ad/start",
                headers=self.auth_headers(token),
            )
            self.assertEqual(response.status_code, 429, response.text)
            self.assertEqual(response.json()["detail"]["code"], "ad_cooldown")
            self.assertGreater(
                response.json()["detail"]["retry_after_seconds"],
                0,
            )
        finally:
            auth_service.AD_COOLDOWN_SECONDS = previous

    def test_ad_daily_limit(self) -> None:
        previous = auth_service.AD_DAILY_LIMIT
        auth_service.AD_DAILY_LIMIT = 1
        try:
            payload, _email, _password = self.register()
            token = payload["token"]
            self.watch_ad(token)
            response = self.client.post(
                "/api/v2/tokens/ad/start",
                headers=self.auth_headers(token),
            )
            self.assertEqual(response.status_code, 429, response.text)
            self.assertEqual(
                response.json()["detail"]["code"],
                "ad_daily_limit",
            )
        finally:
            auth_service.AD_DAILY_LIMIT = previous

    def test_optimize_402_after_balance_spent(self) -> None:
        previous = auth_service.CALCULATION_COST_TOKENS
        auth_service.CALCULATION_COST_TOKENS = auth_service.AD_REWARD_TOKENS
        try:
            payload, _email, _password = self.register()
            token = payload["token"]
            self.watch_ad(token)
            request = {
                "profile": {
                    "capital": 500_000,
                    "monthly": 20_000,
                    "horizon_months": 12,
                },
                "options": {"monte_carlo_paths": 100, "max_scenarios": 10},
            }
            first = self.client.post(
                "/api/v2/optimize",
                json=request,
                headers=self.auth_headers(token),
            )
            self.assertEqual(first.status_code, 200, first.text)
            second = self.client.post(
                "/api/v2/optimize",
                json=request,
                headers=self.auth_headers(token),
            )
            self.assertEqual(second.status_code, 402, second.text)
            self.assertEqual(
                second.json()["detail"]["code"],
                "insufficient_tokens",
            )
        finally:
            auth_service.CALCULATION_COST_TOKENS = previous

    def test_failed_calculation_refunds_tokens(self) -> None:
        from unittest.mock import patch

        from DefultCredit.optimizer import api as api_module

        payload, _email, _password = self.register()
        token = payload["token"]
        self.watch_ad(token)
        request = {
            "profile": {
                "capital": 500_000,
                "monthly": 20_000,
                "horizon_months": 12,
            },
            "options": {"monte_carlo_paths": 100, "max_scenarios": 10},
        }
        with patch.object(
            api_module,
            "run_optimization",
            side_effect=ValueError("engine failure"),
        ):
            response = self.client.post(
                "/api/v2/optimize",
                json=request,
                headers=self.auth_headers(token),
            )
        self.assertEqual(response.status_code, 400, response.text)
        status = self.client.get(
            "/api/v2/tokens",
            headers=self.auth_headers(token),
        )
        self.assertEqual(status.json()["tokens"], auth_service.AD_REWARD_TOKENS)
