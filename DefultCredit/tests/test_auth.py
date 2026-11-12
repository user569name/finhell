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

from fastapi.testclient import TestClient  # noqa: E402

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
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertIn("risk_profiles", body)
        self.assertIn("context_id", body)

    def test_async_job_belongs_to_user(self) -> None:
        owner, _email, _password = self.register()
        other, _email2, _password2 = self.register()
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
        job_id = created.json()["job_id"]

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
