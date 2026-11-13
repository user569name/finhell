"""Авторизация по email и паролю и токен-экономика ФинХелл.

Пароли хранятся только в виде PBKDF2-HMAC-SHA256 хешей с индивидуальной
солью. Токены авторизации — компактные HMAC-SHA256 подписи (аналог JWT) без
внешних зависимостей. Пользователи, баланс токенов и сессии рекламы лежат
в SQLite.

Токены расхода:
    расчёт стоит CALCULATION_COST_TOKENS (по умолчанию 1);
    награда за рекламу — AD_REWARD_TOKENS (по умолчанию 5);
    рекламу можно смотреть не чаще AD_COOLDOWN_SECONDS (30 с)
    и не больше AD_DAILY_LIMIT раз в сутки (20).

Переменные окружения:
    FINHELL_DB_PATH        путь к SQLite (по умолчанию DefultCredit/data/finhell.db)
    FINHELL_AUTH_SECRET    секрет подписи токенов; если не задан, создаётся файл
                           auth_secret рядом с базой
    FINHELL_TOKEN_TTL_SECONDS  срок жизни токена (по умолчанию 30 дней)
    FINHELL_CALCULATION_COST_TOKENS  стоимость расчёта (1)
    FINHELL_AD_REWARD_TOKENS         награда за рекламу (5)
    FINHELL_AD_DURATION_SECONDS      длительность rewarded-рекламы (15)
    FINHELL_AD_COOLDOWN_SECONDS      пауза между рекламами (30)
    FINHELL_AD_DAILY_LIMIT           лимит реклам в сутки (20)
    FINHELL_AD_SESSION_GRACE_SECONDS запас времени на завершение (300)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
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
CALCULATION_COST_TOKENS = max(
    0, int(os.getenv("FINHELL_CALCULATION_COST_TOKENS", "1"))
)
AD_REWARD_TOKENS = max(1, int(os.getenv("FINHELL_AD_REWARD_TOKENS", "5")))
AD_DURATION_SECONDS = max(0, int(os.getenv("FINHELL_AD_DURATION_SECONDS", "15")))
AD_COOLDOWN_SECONDS = max(0, int(os.getenv("FINHELL_AD_COOLDOWN_SECONDS", "30")))
AD_DAILY_LIMIT = max(1, int(os.getenv("FINHELL_AD_DAILY_LIMIT", "20")))
AD_SESSION_GRACE_SECONDS = max(
    30, int(os.getenv("FINHELL_AD_SESSION_GRACE_SECONDS", "300"))
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


class TokenError(AuthError):
    """Базовая ошибка токен-экономики."""


class InsufficientTokensError(TokenError):
    """На балансе недостаточно токенов для расчёта."""

    def __init__(self, required: int, balance: int) -> None:
        self.required = max(0, int(required))
        self.balance = max(0, int(balance))
        super().__init__(
            f"Недостаточно токенов: нужно {self.required}, "
            f"на балансе {self.balance}. Посмотрите рекламу, чтобы получить токены."
        )


class AdCooldownError(TokenError):
    """Следующая реклама доступна позже."""

    def __init__(self, retry_after_seconds: float) -> None:
        self.retry_after_seconds = max(0, math.ceil(retry_after_seconds))
        super().__init__(
            f"Следующую рекламу можно посмотреть через "
            f"{self.retry_after_seconds} с."
        )


class AdLimitError(TokenError):
    """Дневной лимит просмотров рекламы исчерпан."""

    def __init__(self, limit: int, reset_in_seconds: float) -> None:
        self.limit = max(1, int(limit))
        self.reset_in_seconds = max(0, math.ceil(reset_in_seconds))
        super().__init__(
            f"Дневной лимит рекламы исчерпан ({self.limit} за сутки). "
            "Возвращайтесь после полуночи UTC."
        )


class AdNotFinishedError(TokenError):
    """Реклама ещё не досмотрена."""

    def __init__(self, retry_after_seconds: float) -> None:
        self.retry_after_seconds = max(1, math.ceil(retry_after_seconds))
        super().__init__(
            f"Реклама ещё не завершена: осталось "
            f"{self.retry_after_seconds} с."
        )


class AdSessionError(TokenError):
    """Сессия рекламы не найдена, истекла или уже оплачена."""


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
                    last_login_at TEXT,
                    tokens INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(users)")
            }
            if "tokens" not in columns:
                connection.execute(
                    "ALTER TABLE users ADD COLUMN tokens INTEGER NOT NULL DEFAULT 0"
                )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS token_transactions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    balance_after INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    meta TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_token_tx_user
                ON token_transactions (user_id, created_at)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ad_sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'started',
                    reward INTEGER NOT NULL,
                    started_at REAL NOT NULL,
                    completed_at REAL,
                    expires_at REAL NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_ad_sessions_user
                ON ad_sessions (user_id, status, started_at)
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
        "tokens": int(row["tokens"]),
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
        "tokens": 0,
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


# ---------------------------------------------------------------------------
# Токен-экономика
# ---------------------------------------------------------------------------

def _utc_day_start(now: float) -> float:
    moment = datetime.fromtimestamp(now, tz=timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return moment.timestamp()


def _utc_day_end(now: float) -> float:
    return _utc_day_start(now) + 24 * 60 * 60


def _log_transaction(
    connection: sqlite3.Connection,
    user_id: str,
    amount: int,
    balance_after: int,
    kind: str,
    meta: str = "",
) -> None:
    connection.execute(
        """
        INSERT INTO token_transactions
            (id, user_id, amount, balance_after, kind, meta, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"txn_{uuid.uuid4().hex}",
            user_id,
            int(amount),
            int(balance_after),
            kind,
            meta[:500],
            _now_iso(),
        ),
    )


def token_status(user_id: str) -> Dict[str, Any]:
    """Баланс, цена расчёта и доступность rewarded-рекламы."""

    _ensure_schema()
    now = time.time()
    day_start = _utc_day_start(now)
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT tokens FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            raise ValidationError("Пользователь не найден.")
        balance = int(row["tokens"])
        ads_today = int(
            connection.execute(
                """
                SELECT COUNT(*) AS total FROM ad_sessions
                WHERE user_id = ? AND status = 'completed' AND completed_at >= ?
                """,
                (user_id, day_start),
            ).fetchone()["total"]
        )
        last_ad = connection.execute(
            """
            SELECT MAX(completed_at) AS finished_at FROM ad_sessions
            WHERE user_id = ? AND status = 'completed'
            """,
            (user_id,),
        ).fetchone()["finished_at"]
        active = connection.execute(
            """
            SELECT id, started_at, expires_at FROM ad_sessions
            WHERE user_id = ? AND status = 'started' AND expires_at >= ?
            ORDER BY started_at DESC LIMIT 1
            """,
            (user_id, now),
        ).fetchone()

    cooldown_until = (
        float(last_ad) + AD_COOLDOWN_SECONDS if last_ad is not None else 0.0
    )
    cooldown_remaining = max(0, math.ceil(cooldown_until - now))
    ads_remaining = max(0, AD_DAILY_LIMIT - ads_today)
    return {
        "tokens": balance,
        "calculation_cost": CALCULATION_COST_TOKENS,
        "ad_reward": AD_REWARD_TOKENS,
        "ad_duration_seconds": AD_DURATION_SECONDS,
        "ad_cooldown_seconds": AD_COOLDOWN_SECONDS,
        "ad_daily_limit": AD_DAILY_LIMIT,
        "ads_today": ads_today,
        "ads_remaining": ads_remaining,
        "cooldown_remaining_seconds": cooldown_remaining,
        "can_watch_ad": cooldown_remaining == 0 and ads_remaining > 0,
        "active_ad_session": (
            {
                "session_id": active["id"],
                "started_at": float(active["started_at"]),
                "expires_at": float(active["expires_at"]),
                "seconds_left": max(
                    0,
                    math.ceil(
                        AD_DURATION_SECONDS
                        - (now - float(active["started_at"]))
                    ),
                ),
            }
            if active is not None
            else None
        ),
    }


def spend_tokens(
    user_id: str,
    amount: int = CALCULATION_COST_TOKENS,
    kind: str = "calculation",
    meta: str = "",
) -> Dict[str, int]:
    """Атомарно списывает токены. При нехватке — InsufficientTokensError."""

    _ensure_schema()
    amount = max(0, int(amount))
    if amount == 0:
        return {"tokens": token_status(user_id)["tokens"], "spent": 0}

    with closing(_connect()) as connection, connection:
        cursor = connection.execute(
            "UPDATE users SET tokens = tokens - ? WHERE id = ? AND tokens >= ?",
            (amount, user_id, amount),
        )
        row = connection.execute(
            "SELECT tokens FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            raise ValidationError("Пользователь не найден.")
        balance = int(row["tokens"])
        if cursor.rowcount == 0:
            raise InsufficientTokensError(required=amount, balance=balance)
        _log_transaction(connection, user_id, -amount, balance, kind, meta)
    return {"tokens": balance, "spent": amount}


def refund_tokens(
    user_id: str,
    amount: int = CALCULATION_COST_TOKENS,
    meta: str = "",
) -> Dict[str, int]:
    """Возвращает токены за неудавшийся расчёт."""

    _ensure_schema()
    amount = max(0, int(amount))
    if amount == 0:
        return {"tokens": token_status(user_id)["tokens"], "refunded": 0}

    with closing(_connect()) as connection, connection:
        cursor = connection.execute(
            "UPDATE users SET tokens = tokens + ? WHERE id = ?",
            (amount, user_id),
        )
        if cursor.rowcount == 0:
            raise ValidationError("Пользователь не найден.")
        row = connection.execute(
            "SELECT tokens FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        balance = int(row["tokens"])
        _log_transaction(connection, user_id, amount, balance, "refund", meta)
    return {"tokens": balance, "refunded": amount}


def start_ad(user_id: str) -> Dict[str, Any]:
    """Создаёт (или возобновляет) сессию rewarded-рекламы."""

    _ensure_schema()
    now = time.time()
    day_start = _utc_day_start(now)
    with closing(_connect()) as connection, connection:
        user = connection.execute(
            "SELECT tokens FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if user is None:
            raise ValidationError("Пользователь не найден.")
        balance = int(user["tokens"])

        connection.execute(
            """
            UPDATE ad_sessions SET status = 'expired'
            WHERE user_id = ? AND status = 'started' AND expires_at < ?
            """,
            (user_id, now),
        )
        active = connection.execute(
            """
            SELECT id, started_at, expires_at FROM ad_sessions
            WHERE user_id = ? AND status = 'started' AND expires_at >= ?
            ORDER BY started_at DESC LIMIT 1
            """,
            (user_id, now),
        ).fetchone()
        if active is not None:
            elapsed = max(0.0, now - float(active["started_at"]))
            return {
                "session_id": active["id"],
                "reward": AD_REWARD_TOKENS,
                "duration_seconds": AD_DURATION_SECONDS,
                "started_at": float(active["started_at"]),
                "expires_at": float(active["expires_at"]),
                "seconds_left": max(
                    0, math.ceil(AD_DURATION_SECONDS - elapsed)
                ),
                "tokens": balance,
                "resumed": True,
            }

        ads_today = int(
            connection.execute(
                """
                SELECT COUNT(*) AS total FROM ad_sessions
                WHERE user_id = ? AND status = 'completed' AND completed_at >= ?
                """,
                (user_id, day_start),
            ).fetchone()["total"]
        )
        if ads_today >= AD_DAILY_LIMIT:
            raise AdLimitError(
                limit=AD_DAILY_LIMIT,
                reset_in_seconds=_utc_day_end(now) - now,
            )

        last_ad = connection.execute(
            """
            SELECT MAX(completed_at) AS finished_at FROM ad_sessions
            WHERE user_id = ? AND status = 'completed'
            """,
            (user_id,),
        ).fetchone()["finished_at"]
        if last_ad is not None:
            wait = float(last_ad) + AD_COOLDOWN_SECONDS - now
            if wait > 0:
                raise AdCooldownError(retry_after_seconds=wait)

        session_id = f"ad_{uuid.uuid4().hex}"
        expires_at = now + AD_DURATION_SECONDS + AD_SESSION_GRACE_SECONDS
        connection.execute(
            """
            INSERT INTO ad_sessions
                (id, user_id, status, reward, started_at, completed_at,
                 expires_at, created_at)
            VALUES (?, ?, 'started', ?, ?, NULL, ?, ?)
            """,
            (
                session_id,
                user_id,
                AD_REWARD_TOKENS,
                now,
                expires_at,
                _now_iso(),
            ),
        )
    return {
        "session_id": session_id,
        "reward": AD_REWARD_TOKENS,
        "duration_seconds": AD_DURATION_SECONDS,
        "started_at": now,
        "expires_at": expires_at,
        "seconds_left": AD_DURATION_SECONDS,
        "tokens": balance,
        "resumed": False,
    }


def complete_ad(user_id: str, session_id: str) -> Dict[str, Any]:
    """Начисляет награду только после реального просмотра рекламы."""

    _ensure_schema()
    now = time.time()
    day_start = _utc_day_start(now)
    with closing(_connect()) as connection, connection:
        row = connection.execute(
            "SELECT * FROM ad_sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        ).fetchone()
        if row is None:
            raise AdSessionError("Сессия рекламы не найдена.")
        if row["status"] == "completed":
            raise AdSessionError("Награда за эту рекламу уже получена.")
        if row["status"] != "started":
            raise AdSessionError("Сессия рекламы больше не активна.")
        if now > float(row["expires_at"]):
            connection.execute(
                "UPDATE ad_sessions SET status = 'expired' WHERE id = ?",
                (session_id,),
            )
            raise AdSessionError(
                "Сессия рекламы истекла. Запустите рекламу заново."
            )

        elapsed = now - float(row["started_at"])
        if elapsed < AD_DURATION_SECONDS:
            raise AdNotFinishedError(AD_DURATION_SECONDS - elapsed)

        updated = connection.execute(
            """
            UPDATE ad_sessions SET status = 'completed', completed_at = ?
            WHERE id = ? AND status = 'started'
            """,
            (now, session_id),
        )
        if updated.rowcount == 0:
            raise AdSessionError("Награда за эту рекламу уже получена.")

        reward = int(row["reward"])
        connection.execute(
            "UPDATE users SET tokens = tokens + ? WHERE id = ?",
            (reward, user_id),
        )
        user = connection.execute(
            "SELECT tokens FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        balance = int(user["tokens"])
        _log_transaction(
            connection,
            user_id,
            reward,
            balance,
            "ad_reward",
            session_id,
        )
        ads_today = int(
            connection.execute(
                """
                SELECT COUNT(*) AS total FROM ad_sessions
                WHERE user_id = ? AND status = 'completed' AND completed_at >= ?
                """,
                (user_id, day_start),
            ).fetchone()["total"]
        )
    return {
        "session_id": session_id,
        "reward": reward,
        "tokens": balance,
        "ads_today": ads_today,
        "ads_remaining": max(0, AD_DAILY_LIMIT - ads_today),
    }


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
