"""Авторизация по email и паролю для ФинХелл.

Пароли хранятся только в виде PBKDF2-HMAC-SHA256 хешей с индивидуальной
солью. Токены — компактные HMAC-SHA256 подписи (аналог JWT) без внешних
зависимостей. Пользователи лежат в SQLite.

Переменные окружения:
    FINHELL_DB_PATH        путь к SQLite (по умолчанию DefultCredit/data/finhell.db)
    FINHELL_AUTH_SECRET    секрет подписи токенов; если не задан, создаётся файл
                           auth_secret рядом с базой
    FINHELL_TOKEN_TTL_SECONDS  срок жизни токена (по умолчанию 30 дней)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
PBKDF2_ITERATIONS = int(os.getenv("FINHELL_PBKDF2_ITERATIONS", "210000"))
TOKEN_TTL_SECONDS = int(
    os.getenv("FINHELL_TOKEN_TTL_SECONDS", str(60 * 60 * 24 * 30))
)
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "finhell.db"

_bearer = HTTPBearer(
    auto_error=False,
    description="Bearer-токен, полученный в /api/v2/auth/login",
)

_secret_lock = threading.Lock()
_secret_cache: Optional[bytes] = None
_schema_lock = threading.Lock()
_schema_ready: set[str] = set()
_dummy_lock = threading.Lock()
_dummy_hash: Optional[str] = None


class AuthError(Exception):
    """Базовая ошибка авторизации."""


class ValidationError(AuthError):
    """Некорректные email, пароль или имя."""


class EmailTakenError(AuthError):
    """Email уже зарегистрирован."""


class InvalidCredentialsError(AuthError):
    """Неверный email или пароль."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _db_path() -> Path:
    raw = os.getenv("FINHELL_DB_PATH", "").strip()
    return Path(raw) if raw else DEFAULT_DB_PATH


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _ensure_schema() -> None:
    key = str(_db_path())
    if key in _schema_ready:
        return
    with _schema_lock:
        if key in _schema_ready:
            return
        with closing(_connect()) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL DEFAULT '',
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_login_at TEXT
                )
                """
            )
        _schema_ready.add(key)


def _b64e(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64d(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _secret() -> bytes:
    global _secret_cache
    if _secret_cache is not None:
        return _secret_cache
    with _secret_lock:
        if _secret_cache is not None:
            return _secret_cache
        from_env = os.getenv("FINHELL_AUTH_SECRET", "").strip()
        if from_env:
            _secret_cache = from_env.encode("utf-8")
            return _secret_cache
        path = _db_path().parent / "auth_secret"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            _secret_cache = path.read_bytes()
        else:
            value = secrets.token_bytes(32)
            path.write_bytes(value)
            _secret_cache = value
        return _secret_cache


def _dummy_password_hash() -> str:
    global _dummy_hash
    if _dummy_hash is not None:
        return _dummy_hash
    with _dummy_lock:
        if _dummy_hash is None:
            _dummy_hash = _hash_password(secrets.token_urlsafe(24))
        return _dummy_hash


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return (
        f"pbkdf2_sha256${PBKDF2_ITERATIONS}"
        f"${_b64e(salt)}${_b64e(digest)}"
    )


def _verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt_b64, digest_b64 = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        salt = _b64d(salt_b64)
        expected = _b64d(digest_b64)
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            int(iterations),
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def normalize_email(email: str) -> str:
    value = (email or "").strip().lower()
    if len(value) > 254 or not EMAIL_RE.match(value):
        raise ValidationError("Введите корректный адрес электронной почты.")
    return value


def validate_password(password: str) -> None:
    if len(password) < 8:
        raise ValidationError("Пароль должен содержать минимум 8 символов.")
    if len(password) > 128:
        raise ValidationError("Пароль слишком длинный: максимум 128 символов.")


def _clean_name(name: str) -> str:
    return " ".join((name or "").split())[:120]


def _row_to_user(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "created_at": row["created_at"],
    }


def register(email: str, password: str, name: str = "") -> Tuple[Dict[str, Any], str]:
    email = normalize_email(email)
    validate_password(password)
    clean_name = _clean_name(name)
    _ensure_schema()

    user_id = f"usr_{uuid.uuid4().hex}"
    created_at = _now_iso()
    password_hash = _hash_password(password)

    try:
        with closing(_connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO users
                    (id, email, name, password_hash, created_at, last_login_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, email, clean_name, password_hash, created_at, created_at),
            )
    except sqlite3.IntegrityError as exc:
        raise EmailTakenError(
            "Пользователь с таким email уже зарегистрирован."
        ) from exc

    user = {
        "id": user_id,
        "email": email,
        "name": clean_name,
        "created_at": created_at,
    }
    return user, create_token(user_id, email)


def login(email: str, password: str) -> Tuple[Dict[str, Any], str]:
    email = normalize_email(email)
    _ensure_schema()

    with closing(_connect()) as connection, connection:
        row = connection.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,),
        ).fetchone()
        stored = row["password_hash"] if row is not None else _dummy_password_hash()
        valid = _verify_password(password, stored)
        if row is None or not valid:
            raise InvalidCredentialsError("Неверный email или пароль.")
        connection.execute(
            "UPDATE users SET last_login_at = ? WHERE id = ?",
            (_now_iso(), row["id"]),
        )

    user = _row_to_user(row)
    return user, create_token(row["id"], row["email"])


def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    _ensure_schema()
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    return _row_to_user(row) if row is not None else None


def user_count() -> int:
    _ensure_schema()
    with closing(_connect()) as connection:
        row = connection.execute("SELECT COUNT(*) AS total FROM users").fetchone()
    return int(row["total"]) if row is not None else 0


def create_token(user_id: str, email: str) -> str:
    issued_at = int(time.time())
    payload = {
        "sub": user_id,
        "email": email,
        "iat": issued_at,
        "exp": issued_at + TOKEN_TTL_SECONDS,
    }
    body = _b64e(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )
    signature = hmac.new(
        _secret(),
        body.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{body}.{_b64e(signature)}"


def decode_token(token: str) -> Dict[str, Any]:
    try:
        body, signature = token.split(".", 1)
        expected = hmac.new(
            _secret(),
            body.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(_b64d(signature), expected):
            raise AuthError("Недействительный токен.")
        payload = json.loads(_b64d(body).decode("utf-8"))
        if not isinstance(payload, dict) or not payload.get("sub"):
            raise AuthError("Недействительный токен.")
        if int(payload.get("exp", 0)) < int(time.time()):
            raise AuthError("Срок действия токена истёк. Войдите снова.")
        return payload
    except AuthError:
        raise
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise AuthError("Недействительный токен.") from exc


def current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Dict[str, Any]:
    unauthorized = HTTPException(
        status_code=401,
        detail="Требуется авторизация. Войдите по email.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized
    try:
        payload = decode_token(credentials.credentials)
    except AuthError as exc:
        raise HTTPException(
            status_code=401,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    user = get_user(str(payload["sub"]))
    if user is None:
        raise unauthorized
    return user


def reset_cache() -> None:
    """Сбрасывает кеши секрета и схемы (нужно тестам)."""

    global _secret_cache, _dummy_hash
    with _secret_lock:
        _secret_cache = None
    with _dummy_lock:
        _dummy_hash = None
    with _schema_lock:
        _schema_ready.clear()
