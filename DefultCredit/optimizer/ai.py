"""AI-слой оптимизатора капитала.

Ключевой принцип: LLM ничего не считает. Она получает детерминированный
JSON-контекст, сформированный расчётным движком, и может только объяснять
его. Любое число в ответе проверяется валидатором: если модель придумала
цифру, ответ заменяется шаблонным.

Провайдеры: OpenAI-совместимый, Anthropic, YandexGPT, GigaChat.
Без ключей работает полностью автономный шаблонный режим.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from .models import (
    AIChatMessage,
    AIChatResponse,
    AIExplanation,
)

DISCLAIMER = (
    "Это не индивидуальная инвестиционная рекомендация. Расчёты основаны "
    "на модельных допущениях и доступных макроданных; фактические доходности, "
    "ставки, налоги и цены могут отличаться. Проверяйте условия у банка, "
    "брокера и налогового консультанта."
)

CONTEXT_TTL_SECONDS = 30 * 60
RESPONSE_TTL_SECONDS = 10 * 60
MAX_CONTEXTS = 500
MAX_CACHED_RESPONSES = 300

SYSTEM_PROMPT = """Ты — AI-аналитик сервиса «Оптимизатор капитала» для России.
Ты объясняешь готовый детерминированный расчёт, а не считаешь сам.

Жёсткие правила:
1. Используй только числа, которые есть в JSON-контексте. Не выполняй
   арифметику, не экстраполируй и не придумывай новые цифры.
2. Если нужного числа нет в контексте — прямо скажи, что в расчёте его нет.
3. Не гарантируй доходность. Не пиши «без риска», «точно», «100%».
4. Не предлагай акции, криптовалюту, форекс и иные инструменты вне модели.
5. Учитывай три уровня риска: низкий, средний, высокий. Не смешивай их.
6. Пиши по-русски, кратко и структурированно, без канцелярита.
7. Всегда напоминай, что это не индивидуальная инвестиционная рекомендация.
8. Для режима объяснения верни строго JSON без markdown:
   {
     "summary": "2–4 предложения",
     "risk_profiles": {"low": "...", "medium": "...", "high": "..."},
     "steps": ["шаг 1", "шаг 2", "шаг 3"],
     "why": "почему выбран сценарий, 2–3 предложения",
     "risks": "главные риски, 2–3 предложения",
     "disclaimer": "дисклеймер"
   }
Для режима чата верни обычный текст: 2–5 коротких абзацев или пунктов."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# TTL-кэш
# ---------------------------------------------------------------------------

@dataclass
class _CacheEntry:
    value: object
    expires_at: float


class _TTLCache:
    def __init__(self, max_items: int) -> None:
        self._items: Dict[str, _CacheEntry] = {}
        self._lock = threading.Lock()
        self._max_items = max_items

    def get(self, key: str) -> Optional[object]:
        with self._lock:
            entry = self._items.get(key)
            if entry is None:
                return None
            if entry.expires_at < time.time():
                self._items.pop(key, None)
                return None
            return entry.value

    def set(self, key: str, value: object, ttl: float) -> None:
        with self._lock:
            if len(self._items) >= self._max_items:
                now = time.time()
                expired = [key for key, entry in self._items.items() if entry.expires_at < now]
                for key in expired:
                    self._items.pop(key, None)
                while len(self._items) >= self._max_items:
                    oldest = min(self._items, key=lambda key: self._items[key].expires_at)
                    self._items.pop(oldest, None)
            self._items[key] = _CacheEntry(value=value, expires_at=time.time() + ttl)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._items)


CONTEXT_CACHE = _TTLCache(MAX_CONTEXTS)
RESPONSE_CACHE = _TTLCache(MAX_CACHED_RESPONSES)


# ---------------------------------------------------------------------------
# Контекст
# ---------------------------------------------------------------------------

def _dump(value: object) -> object:
    if hasattr(value, "model_dump"):
        return value.model_dump()  # type: ignore[no-any-return]
    return value


def _round(value: float, digits: int = 4) -> float:
    return round(float(value), digits)


def _enum_value(value: object) -> object:
    return getattr(value, "value", value)


def _compact_option(option: object) -> Dict[str, object]:
    data = _dump(option)
    if not isinstance(data, dict):
        return {}
    mc = data.get("monte_carlo") or {}
    if not isinstance(mc, dict):
        mc = {}
    taxes = data.get("taxes") or {}
    fees = data.get("fees") or {}
    allocation = data.get("allocation") or []
    return {
        "id": data.get("id"),
        "name": data.get("name"),
        "risk_level": _enum_value(data.get("risk_level")),
        "description": data.get("description"),
        "expected_return_nominal": _round(data.get("expected_return_nominal", 0)),
        "expected_return_real": _round(data.get("expected_return_real", 0)),
        "after_tax_return": _round(data.get("after_tax_return", 0)),
        "volatility": _round(data.get("volatility", 0)),
        "sharpe": _round(data.get("sharpe", 0)),
        "sortino": _round(data.get("sortino", 0)),
        "var_95": _round(data.get("var_95", 0)),
        "cvar_95": _round(data.get("cvar_95", 0)),
        "max_drawdown": _round(data.get("max_drawdown", 0)),
        "probability_goal": data.get("probability_goal"),
        "probability_loss": data.get("probability_loss"),
        "liquidity": _round(data.get("liquidity", 0)),
        "liquidity_label": data.get("liquidity_label"),
        "duration_years": _round(data.get("duration_years", 0), 2),
        "npv": _round(data.get("npv", 0), 2),
        "irr": data.get("irr"),
        "score": _round(data.get("score", 0)),
        "rank": data.get("rank"),
        "tags": data.get("tags") or [],
        "allocation": [
            {
                "key": item.get("key"),
                "name": item.get("name"),
                "weight": _round(item.get("weight", 0)),
                "amount": _round(item.get("amount", 0), 2),
                "expected_return": _round(item.get("expected_return", 0)),
                "volatility": _round(item.get("volatility", 0)),
                "liquidity": _round(item.get("liquidity", 0)),
                "tax_note": item.get("tax_note"),
            }
            for item in allocation
            if isinstance(item, dict)
        ],
        "taxes": {
            "annual_tax": _round(taxes.get("annual_tax", 0), 2),
            "total_tax_estimate": _round(taxes.get("total_tax_estimate", 0), 2),
            "effective_rate": _round(taxes.get("effective_rate", 0)),
            "deductions": _round(taxes.get("deductions", 0), 2),
            "note": taxes.get("note"),
        },
        "fees": {
            "annual_fee": _round(fees.get("annual_fee", 0), 2),
            "total_fee_estimate": _round(fees.get("total_fee_estimate", 0), 2),
            "effective_rate": _round(fees.get("effective_rate", 0)),
            "note": fees.get("note"),
        },
        "monte_carlo": {
            "paths": mc.get("paths"),
            "distribution": mc.get("distribution"),
            "terminal_p5": _round(mc.get("terminal_p5", 0), 2),
            "terminal_p25": _round(mc.get("terminal_p25", 0), 2),
            "terminal_p50": _round(mc.get("terminal_p50", 0), 2),
            "terminal_p75": _round(mc.get("terminal_p75", 0), 2),
            "terminal_p95": _round(mc.get("terminal_p95", 0), 2),
            "real_terminal_p50": _round(mc.get("real_terminal_p50", 0), 2),
            "total_contributions": _round(mc.get("total_contributions", 0), 2),
            "probability_goal": mc.get("probability_goal"),
            "probability_loss": mc.get("probability_loss"),
            "var_95": _round(mc.get("var_95", 0)),
            "cvar_95": _round(mc.get("cvar_95", 0)),
            "max_drawdown_median": _round(mc.get("max_drawdown_median", 0)),
            "max_drawdown_p90": _round(mc.get("max_drawdown_p90", 0)),
        },
        "stress_tests": [
            {
                "scenario": item.get("scenario"),
                "impact_p50": _round(item.get("impact_p50", 0)),
                "impact_p5": _round(item.get("impact_p5", 0)),
                "terminal_p50": _round(item.get("terminal_p50", 0), 2),
                "note": item.get("note"),
            }
            for item in (data.get("stress_tests") or [])
            if isinstance(item, dict)
        ],
    }


def build_context(data: Dict[str, object]) -> Dict[str, object]:
    """Сжать результат оптимизации до детерминированного JSON для LLM."""
    profile = _dump(data.get("profile")) or {}
    macro = _dump(data.get("macro")) or {}
    risk_profiles_raw = data.get("risk_profiles") or {}
    comparisons_raw = _dump(data.get("comparisons")) or {}
    top_raw = data.get("top_options") or []

    if not isinstance(profile, dict):
        profile = {}
    if not isinstance(macro, dict):
        macro = {}

    def point(name: str) -> Dict[str, object]:
        item = macro.get(name) or {}
        if not isinstance(item, dict):
            return {"value": 0.0, "source": "", "updated_at": "", "is_fallback": True}
        return {
            "value": _round(item.get("value", 0)),
            "source": item.get("source"),
            "updated_at": item.get("updated_at"),
            "is_fallback": item.get("is_fallback", True),
            "note": item.get("note"),
        }

    macro_keys = [
        "key_rate", "inflation_yoy", "inflation_expected", "deposit_rate",
        "savings_rate", "credit_rate", "mortgage_rate", "ofz_yield_10y",
        "corporate_yield", "municipal_yield", "real_estate_growth",
        "rent_yield", "usd_rub", "eur_rub",
    ]
    macro_compact = {key: point(key) for key in macro_keys}
    macro_compact["ofz_curve"] = [
        {
            "tenor_months": item.get("tenor_months"),
            "yield_rate": _round(item.get("yield_rate", 0)),
        }
        for item in (macro.get("ofz_curve") or [])
        if isinstance(item, dict)
    ]
    macro_compact["fetched_at"] = macro.get("fetched_at")
    macro_compact["data_sources"] = [
        {
            "key": item.get("key"),
            "name": item.get("name"),
            "status": item.get("status"),
            "updated_at": item.get("updated_at"),
            "note": item.get("note"),
        }
        for item in (macro.get("data_sources") or [])
        if isinstance(item, dict)
    ]

    horizon_months = int(profile.get("horizon_months") or 0)
    horizon_years = round(horizon_months / 12.0, 2)
    capital = float(profile.get("capital") or 0)
    monthly = float(profile.get("monthly") or 0)
    emergency_months = int(profile.get("emergency_fund_months") or 0)
    monthly_expenses = float(profile.get("monthly_expenses") or 0)
    emergency_target = round(monthly_expenses * emergency_months, 2)

    iis = profile.get("iis") or {}
    mortgage = profile.get("existing_mortgage") or {}
    deposits = profile.get("deposits") or []
    if not isinstance(iis, dict):
        iis = {}
    if not isinstance(mortgage, dict):
        mortgage = {}
    if not isinstance(deposits, list):
        deposits = []

    profile_compact = {
        "capital": round(capital, 2),
        "monthly": round(monthly, 2),
        "horizon_months": horizon_months,
        "horizon_years": horizon_years,
        "risk_tolerance": _enum_value(profile.get("risk_tolerance")),
        "liquidity_need": _enum_value(profile.get("liquidity_need")),
        "credit_willingness": profile.get("credit_willingness"),
        "credit_type": _enum_value(profile.get("credit_type")),
        "goal_amount": profile.get("goal_amount"),
        "monthly_expenses": round(monthly_expenses, 2),
        "emergency_fund_months": emergency_months,
        "emergency_fund_target": emergency_target,
        "region": profile.get("region"),
        "iis_type": iis.get("type", "none"),
        "iis_annual_contribution": iis.get("annual_contribution", 0),
        "iis_years": iis.get("years", 0),
        "existing_mortgage_balance": mortgage.get("balance", 0),
        "existing_mortgage_rate": mortgage.get("annual_rate", 0),
        "existing_mortgage_payment": mortgage.get("monthly_payment", 0),
        "existing_mortgage_remaining_months": mortgage.get("remaining_months", 0),
        "existing_mortgage_property_value": mortgage.get("property_value", 0),
        "deposits": [
            {
                "amount": _round(item.get("amount", 0), 2),
                "annual_rate": _round(item.get("annual_rate", 0)),
                "term_months": item.get("term_months"),
            }
            for item in deposits
            if isinstance(item, dict)
        ],
        "deposits_total": round(
            sum(float(item.get("amount") or 0) for item in deposits if isinstance(item, dict)),
            2,
        ),
        "total_contributions": round(capital + monthly * horizon_months, 2),
    }

    profiles_compact: Dict[str, object] = {}
    if isinstance(risk_profiles_raw, dict):
        for level in ("low", "medium", "high"):
            profile_result = _dump(risk_profiles_raw.get(level))
            if not isinstance(profile_result, dict):
                continue
            options = profile_result.get("options") or []
            profiles_compact[level] = {
                "label": profile_result.get("label"),
                "description": profile_result.get("description"),
                "best_option_id": profile_result.get("best_option_id"),
                "summary": {
                    key: _round(value) if isinstance(value, (int, float)) else value
                    for key, value in (profile_result.get("summary") or {}).items()
                },
                "options": [
                    _compact_option(option) for option in options[:3]
                ],
            }

    top_options = [
        _compact_option(option) for option in top_raw[:10]
    ]
    comparisons = comparisons_raw if isinstance(comparisons_raw, dict) else {}

    context: Dict[str, object] = {
        "meta": {
            "generated_at": data.get("generated_at"),
            "request_id": data.get("request_id"),
            "currency": "RUB",
            "disclaimer": data.get("disclaimer") or DISCLAIMER,
        },
        "profile": profile_compact,
        "macro": macro_compact,
        "risk_profiles": profiles_compact,
        "top_options": top_options,
        "comparisons": comparisons,
        "warnings": list(data.get("warnings") or []),
    }
    return context


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def store_context(context: Dict[str, object]) -> str:
    digest = hashlib.sha256(canonical_json(context).encode("utf-8")).hexdigest()
    context_id = f"ctx_{digest[:24]}"
    CONTEXT_CACHE.set(context_id, context, CONTEXT_TTL_SECONDS)
    return context_id


def load_context(context_id: str) -> Optional[Dict[str, object]]:
    value = CONTEXT_CACHE.get(context_id)
    if isinstance(value, dict):
        return value
    return None


def resolve_context(
    context_id: Optional[str] = None,
    context: Optional[Dict[str, object]] = None,
) -> Tuple[Optional[Dict[str, object]], Optional[str]]:
    if context_id:
        stored = load_context(context_id)
        if stored is not None:
            return stored, context_id
    if context:
        new_id = store_context(context)
        return context, new_id
    return None, context_id


# ---------------------------------------------------------------------------
# Валидатор чисел
# ---------------------------------------------------------------------------

_NUMBER_RE = re.compile(
    r"(?<![\w])([-+]?\d[\d\s\u00a0]*(?:[.,]\d+)?)\s*"
    r"(%|₽|руб\.?|рублей|тыс\.?|тысяч|млн\.?|миллион(?:а|ов)?|млрд\.?|миллиард(?:а|ов)?)?",
    re.IGNORECASE,
)
_STRING_NUMBER_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")


def _collect_numbers(value: object, target: set[float]) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        number = float(value)
        if abs(number) < 1e12:
            target.add(round(number, 6))
            if 0 < abs(number) <= 2:
                target.add(round(number * 100.0, 6))
        return
    if isinstance(value, str):
        for match in _STRING_NUMBER_RE.findall(value):
            try:
                number = float(match.replace(",", "."))
            except ValueError:
                continue
            target.add(round(number, 6))
            if 0 < abs(number) <= 2:
                target.add(round(number * 100.0, 6))
        return
    if isinstance(value, dict):
        for item in value.values():
            _collect_numbers(item, target)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _collect_numbers(item, target)


def allowed_numbers(context: Dict[str, object]) -> set[float]:
    values: set[float] = set()
    _collect_numbers(context, values)
    # Часто встречающиеся структурные числа: годы, месяцы, проценты шкалы.
    values.update({0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 10.0, 12.0, 13.0, 15.0, 18.0, 20.0, 22.0, 100.0})
    return values


def _material(token: str, unit: str, raw: str) -> bool:
    if unit:
        return True
    if "." in raw or "," in raw:
        return True
    try:
        number = float(raw.replace(" ", "").replace("\u00a0", "").replace(",", "."))
    except ValueError:
        return False
    if 1900 <= number <= 2100:
        return False
    return abs(number) >= 1000


def validate_numbers(text: str, context: Dict[str, object]) -> List[str]:
    """Вернуть список материальных чисел, которых нет в контексте."""
    allowed = allowed_numbers(context)
    violations: List[str] = []
    for match in _NUMBER_RE.finditer(text):
        raw = match.group(1)
        unit = (match.group(2) or "").strip().lower()
        if not _material(raw, unit, raw):
            continue
        try:
            number = float(
                raw.replace(" ", "").replace("\u00a0", "").replace(",", ".")
            )
        except ValueError:
            continue
        multiplier = 1.0
        if unit.startswith("тыс") or unit.startswith("тысяч"):
            multiplier = 1_000.0
        elif unit.startswith("млн") or unit.startswith("миллион"):
            multiplier = 1_000_000.0
        elif unit.startswith("млрд") or unit.startswith("миллиард"):
            multiplier = 1_000_000_000.0
        value = number * multiplier
        candidates = [value]
        if unit == "%":
            candidates = [number, number / 100.0]
        elif not unit:
            candidates = [value, value * 100.0] if 0 < abs(value) <= 2 else [value]
        found = False
        for candidate in candidates:
            for known in allowed:
                tolerance = max(0.51, abs(known) * 0.01)
                if abs(candidate - known) <= tolerance:
                    found = True
                    break
            if found:
                break
        if not found:
            violations.append(match.group(0).strip())
    # Убираем дубли, сохраняя порядок.
    unique: List[str] = []
    for item in violations:
        if item not in unique:
            unique.append(item)
    return unique[:20]


def _validate_explanation(explanation: AIExplanation, context: Dict[str, object]) -> List[str]:
    parts = [explanation.summary, explanation.why, explanation.risks, explanation.disclaimer]
    parts.extend(explanation.risk_profiles.values())
    parts.extend(explanation.steps)
    violations: List[str] = []
    for part in parts:
        violations.extend(validate_numbers(part, context))
    unique: List[str] = []
    for item in violations:
        if item not in unique:
            unique.append(item)
    return unique[:20]


# ---------------------------------------------------------------------------
# Шаблонные объяснения
# ---------------------------------------------------------------------------

def _money(value: float) -> str:
    return f"{float(value):,.0f}".replace(",", " ")


def _pct(value: float, digits: int = 1) -> str:
    return f"{float(value) * 100:.{digits}f}%".replace(".", ",")


def _best_option(context: Dict[str, object]) -> Optional[Dict[str, object]]:
    options = context.get("top_options") or []
    if isinstance(options, list) and options:
        first = options[0]
        if isinstance(first, dict):
            return first
    profiles = context.get("risk_profiles") or {}
    if isinstance(profiles, dict):
        for level in ("medium", "low", "high"):
            group = profiles.get(level) or {}
            if isinstance(group, dict):
                group_options = group.get("options") or []
                if group_options and isinstance(group_options[0], dict):
                    return group_options[0]
    return None


def _profile_group(context: Dict[str, object], level: str) -> Optional[Dict[str, object]]:
    profiles = context.get("risk_profiles") or {}
    if not isinstance(profiles, dict):
        return None
    group = profiles.get(level)
    return group if isinstance(group, dict) else None


def template_explanation(context: Dict[str, object]) -> AIExplanation:
    profile = context.get("profile") or {}
    macro = context.get("macro") or {}
    if not isinstance(profile, dict):
        profile = {}
    if not isinstance(macro, dict):
        macro = {}

    capital = float(profile.get("capital") or 0)
    monthly = float(profile.get("monthly") or 0)
    years = float(profile.get("horizon_years") or 0)
    goal = profile.get("goal_amount")
    best = _best_option(context)

    def point(name: str) -> float:
        item = macro.get(name) or {}
        if isinstance(item, dict):
            return float(item.get("value") or 0)
        return 0.0

    if best:
        mc = best.get("monte_carlo") or {}
        if not isinstance(mc, dict):
            mc = {}
        goal_text = ""
        if goal:
            probability = mc.get("probability_goal")
            if isinstance(probability, (int, float)):
                goal_text = f" Вероятность достичь цели — {_pct(float(probability))}."
        summary = (
            f"При капитале {_money(capital)} ₽ и взносе {_money(monthly)} ₽/мес "
            f"на {years:g} лет лучший баланс риска и доходности — сценарий "
            f"«{best.get('name')}». Ожидаемая доходность {_pct(float(best.get('expected_return_nominal') or 0))}, "
            f"медианный капитал {_money(float(mc.get('terminal_p50') or 0))} ₽, "
            f"диапазон P5–P95: {_money(float(mc.get('terminal_p5') or 0))}–"
            f"{_money(float(mc.get('terminal_p95') or 0))} ₽.{goal_text}"
        )
    else:
        summary = (
            "Расчёт не смог построить сценарии под заданные параметры. "
            "Проверьте капитал, срок и допустимый риск."
        )

    risk_texts: Dict[str, str] = {}
    labels = {"low": "Низкий риск", "medium": "Средний риск", "high": "Высокий риск"}
    for level in ("low", "medium", "high"):
        group = _profile_group(context, level)
        if not group:
            continue
        options = group.get("options") or []
        if not options or not isinstance(options[0], dict):
            continue
        option = options[0]
        mc = option.get("monte_carlo") or {}
        if not isinstance(mc, dict):
            mc = {}
        risk_texts[level] = (
            f"{labels[level]}: «{option.get('name')}». Доходность "
            f"{_pct(float(option.get('expected_return_nominal') or 0))}, "
            f"P50 {_money(float(mc.get('terminal_p50') or 0))} ₽, "
            f"P5 {_money(float(mc.get('terminal_p5') or 0))} ₽, "
            f"P95 {_money(float(mc.get('terminal_p95') or 0))} ₽, "
            f"просадка {_pct(float(option.get('max_drawdown') or 0))}, "
            f"ликвидность {_pct(float(option.get('liquidity') or 0), 0)}."
        )

    emergency_target = float(profile.get("emergency_fund_target") or 0)
    steps = [
        (
            f"Сначала проверьте резерв: ориентир — {_money(emergency_target)} ₽ "
            f"({profile.get('emergency_fund_months')} мес. расходов). "
            "Держите его в накопительном счёте или коротком вкладе."
        ),
        (
            "Сравните три карточки риска: низкую — для сохранности, среднюю — "
            "для купона и защиты от инфляции, высокую — для премии за риск."
        ),
        (
            f"Учтите налоги и комиссии: в расчёте эффективная ставка налогов "
            f"{_pct(float((best or {}).get('taxes', {}).get('effective_rate', 0)))} "
            "от капитала в год. ИИС типа A или B может улучшить результат."
        ),
        (
            "Проверьте стресс-тесты: рост ключевой ставки, инфляция, падение "
            "недвижимости и рост ипотечной ставки. Если просадка неприемлема — "
            "сдвиньтесь к низкому риску."
        ),
        (
            "Пересчитывайте план раз в квартал или при изменении ключевой "
            "ставки, инфляции и условий по вкладам."
        ),
    ]

    key_rate = point("key_rate")
    inflation = point("inflation_expected")
    deposit = point("deposit_rate")
    mortgage = point("mortgage_rate")
    why = (
        f"Ключевая ставка {_pct(key_rate)}, ожидаемая инфляция {_pct(inflation)}, "
        f"средняя ставка по вкладам {_pct(deposit)}, ипотека {_pct(mortgage)}. "
        "При высокой ставке короткие вклады и ОФЗ дают хорошую базовую доходность "
        "с низким риском, а длинные облигации и недвижимость — премию за риск "
        "и защиту от снижения ставок в будущем."
    )
    risks = (
        "Главные риски: изменение ключевой ставки и инфляции, кредитный риск "
        "корпоративных и муниципальных облигаций, низкая ликвидность "
        "недвижимости, рост ипотечной ставки и платежа. Стресс-тесты показывают, "
        "насколько результат чувствителен к этим факторам; ориентируйтесь на P5, "
        "а не только на медиану."
    )
    return AIExplanation(
        summary=summary,
        risk_profiles=risk_texts,
        steps=steps,
        why=why,
        risks=risks,
        disclaimer=DISCLAIMER,
        generated_by="template",
    )


def _top_option_line(option: Dict[str, object]) -> str:
    mc = option.get("monte_carlo") or {}
    if not isinstance(mc, dict):
        mc = {}
    return (
        f"«{option.get('name')}»: доходность "
        f"{_pct(float(option.get('expected_return_nominal') or 0))}, "
        f"P50 {_money(float(mc.get('terminal_p50') or 0))} ₽, "
        f"P5 {_money(float(mc.get('terminal_p5') or 0))} ₽, "
        f"риск-профиль {option.get('risk_level')}."
    )


def template_chat(
    context: Dict[str, object],
    question: str,
    history: Optional[Sequence[AIChatMessage]] = None,
) -> str:
    del history  # шаблонный режим отвечает по текущему контексту
    profile = context.get("profile") or {}
    macro = context.get("macro") or {}
    if not isinstance(profile, dict):
        profile = {}
    if not isinstance(macro, dict):
        macro = {}
    q = question.lower().replace("ё", "е")

    def point(name: str) -> float:
        item = macro.get(name) or {}
        if isinstance(item, dict):
            return float(item.get("value") or 0)
        return 0.0

    best = _best_option(context)
    if any(word in q for word in ("обнал", "уйти от налог", "скрыть доход", "серую схему")):
        return (
            "Я не помогаю с незаконными схемами. Легальные способы снизить налог: "
            "ИИС типа A или B, имущественный вычет, налоговый вычет по ипотечным "
            "процентам и корректная декларация доходов."
        )
    if any(word in q for word in ("гарантир", "без риска", "точно заработа", "100%")):
        return (
            "Гарантированной доходности не существует. Любой сценарий — это "
            "распределение исходов: смотрите на P5, P50 и P95, а также на "
            "максимальную просадку. " + DISCLAIMER
        )
    if any(word in q for word in ("ключев", "ставк", "цб")):
        return (
            f"Ключевая ставка в расчёте — {_pct(point('key_rate'))}. Она задаёт "
            f"ориентир для вкладов ({_pct(point('deposit_rate'))}) и коротких ОФЗ. "
            "Если ставка растёт, длинные облигации дешевеют, а вклады становятся "
            "интереснее; если снижается — длинные ОФЗ и недвижимость получают "
            "премию. В стресс-тестах есть сценарии ±100, ±300 и ±500 б.п."
        )
    if "инфляц" in q:
        return (
            f"Ожидаемая инфляция — {_pct(point('inflation_expected'))}, "
            f"инфляция год к году — {_pct(point('inflation_yoy'))}. Реальная "
            "доходность считается как номинальная минус инфляция; в карточках "
            "показан реальный P50. Если инфляция выше доходности вклада, капитал "
            "в реальном выражении сокращается."
        )
    if any(word in q for word in ("риск", "просад", "волатил")):
        lines = []
        for level, label in (("low", "Низкий"), ("medium", "Средний"), ("high", "Высокий")):
            group = _profile_group(context, level)
            if group and group.get("options"):
                option = group["options"][0]
                mc = option.get("monte_carlo") or {}
                if isinstance(mc, dict):
                    lines.append(
                        f"{label}: «{option.get('name')}», просадка "
                        f"{_pct(float(option.get('max_drawdown') or 0))}, "
                        f"P5 {_money(float(mc.get('terminal_p5') or 0))} ₽."
                    )
        return (
            "Три профиля риска показывают разные компромиссы:\n\n"
            + "\n".join(lines)
            + "\n\nЧем выше доходность, тем шире разброс исходов. Для коротких "
            "целей ориентируйтесь на низкий риск, для длинных — на средний."
        )
    if any(word in q for word in ("ипотек", "недвиж", "квартир", "аренд")):
        comparison = context.get("comparisons") or {}
        rent = comparison.get("rent_vs_buy") if isinstance(comparison, dict) else None
        extra = ""
        if isinstance(rent, dict):
            extra = (
                f" По сравнению «аренда vs покупка» лучше: {rent.get('better_option')}, "
                f"разница NPV {_money(float(rent.get('npv_difference') or 0))} ₽."
            )
        return (
            f"Ипотечная ставка в расчёте — {_pct(point('mortgage_rate'))}, "
            f"рост цен на недвижимость — {_pct(point('real_estate_growth'))}, "
            f"доходность аренды — {_pct(point('rent_yield'))}. Недвижимость "
            "менее ликвидна, требует резерва на ремонт и простой, а плечо "
            "усиливает просадку." + extra
        )
    if any(word in q for word in ("вклад", "счет", "накопит", "депозит")):
        return (
            f"Средняя ставка по вкладам — {_pct(point('deposit_rate'))}, "
            f"по накопительному счёту — {_pct(point('savings_rate'))}. Вклад "
            "фиксирует ставку и застрахован АСВ в пределах лимита, но деньги "
            "недоступны без потери процентов. Накопительный счёт ликвиднее, "
            "но ставка обычно ниже."
        )
    if any(word in q for word in ("офз", "облигац", "купон", "дюрац")):
        return (
            f"Доходность ОФЗ в расчёте — {_pct(point('ofz_yield_10y'))}, "
            f"корпоративных облигаций — {_pct(point('corporate_yield'))}, "
            f"муниципальных — {_pct(point('municipal_yield'))}. Длинные ОФЗ "
            "чувствительны к ставке: при её снижении цена растёт, при росте — "
            "падает. Корпоративные облигации дают премию за кредитный риск."
        )
    if any(word in q for word in ("налог", "ндфл", "иис", "вычет")):
        return (
            "В модели учтены НДФЛ с процентов по вкладам сверх порога "
            "«ключевая ставка × 1 млн ₽», налог с купонов и аренды, а также "
            "вычеты по ИИС и ипотеке. ИИС типа A возвращает 13% от взносов "
            "до 400 000 ₽/год (в пределах уплаченного НДФЛ), тип B освобождает "
            "доход от налога. Точную сумму лучше проверить в личном кабинете "
            "налогоплательщика."
        )
    if any(word in q for word in ("аренда", "покупка", "купить", "снимать")):
        comparison = context.get("comparisons") or {}
        rent = comparison.get("rent_vs_buy") if isinstance(comparison, dict) else None
        if isinstance(rent, dict):
            details = rent.get("details") or {}
            return (
                f"По модели лучше {rent.get('better_option')}. Стоимость объекта "
                f"{_money(float(details.get('property_value') or 0))} ₽, "
                f"первый взнос {_money(float(details.get('down_payment') or 0))} ₽, "
                f"платёж {_money(float(details.get('monthly_payment') or 0))} ₽/мес, "
                f"аренда {_money(float(details.get('monthly_rent') or 0))} ₽/мес. "
                "Разница NPV уже учитывает рост цены, остаток долга и вычеты."
            )
        return "Сравнение «аренда vs покупка» появится после расчёта с достаточным капиталом."
    if any(word in q for word in ("досроч", "погас", "кредит")):
        comparison = context.get("comparisons") or {}
        prepay = comparison.get("prepay_vs_invest") if isinstance(comparison, dict) else None
        if isinstance(prepay, dict):
            return (
                f"По модели лучше {prepay.get('better_option')}. Ставка по долгу "
                f"{_pct(float((prepay.get('details') or {}).get('debt_rate') or 0))}, "
                f"ожидаемая доходность портфеля "
                f"{_pct(float((prepay.get('details') or {}).get('portfolio_return') or 0))}. "
                "Досрочное погашение — это гарантированная экономия на процентах; "
                "инвестирование — рискованная, но потенциально более высокая доходность."
            )
        return "Добавьте существующий кредит или ипотеку в форму, чтобы сравнить погашение и инвестирование."
    if any(word in q for word in ("стресс", "падени", "шок")):
        if best:
            stress = best.get("stress_tests") or []
            if stress:
                lines = [
                    f"{item.get('scenario')}: {_pct(float(item.get('impact_p50') or 0))}"
                    for item in stress[:6]
                    if isinstance(item, dict)
                ]
                return (
                    "Стресс-тесты для лучшего сценария показывают изменение "
                    "медианного результата:\n\n" + "\n".join(lines) +
                    "\n\nХудший сценарий — не приговор, но он помогает понять, "
                    "выдержите ли вы просадку психологически и по денежному потоку."
                )
        return "Стресс-тесты появятся после расчёта."
    if any(word in q for word in ("что выбрать", "лучше", "рекоменд", "почему", "какой")):
        if best:
            return (
                f"Лучший сценарий по совокупности Sharpe, NPV, устойчивости к "
                f"стрессам и ликвидности — {_top_option_line(best)} "
                "Но «лучший» здесь — не универсальная рекомендация: если цель "
                "близко или нужен резерв, выбирайте низкий риск; если горизонт "
                "длинный и просадка приемлема — средний или высокий."
            )
        return "Расчёт ещё не готов. Запустите оптимизацию."
    if best:
        return (
            "Коротко по расчёту: " + _top_option_line(best) +
            "\n\nМожно спросить про ключевую ставку, инфляцию, риски, вклады, "
            "ОФЗ, налоги, ИИС, ипотеку, аренду или стресс-тесты."
        )
    return (
        "Я объясняю готовый расчёт оптимизатора. Запустите оптимизацию, и я "
        "разберу сценарии, риски, налоги и стресс-тесты."
    )


# ---------------------------------------------------------------------------
# Провайдеры LLM
# ---------------------------------------------------------------------------

class LLMError(RuntimeError):
    pass


def _post_json(
    url: str,
    payload: Dict[str, object],
    headers: Dict[str, str],
    timeout: float,
) -> Dict[str, object]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise LLMError(f"LLM HTTP {exc.code}: {detail}") from exc
    except Exception as exc:  # noqa: BLE001
        raise LLMError(f"LLM request failed: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMError("LLM вернул не-JSON") from exc
    if not isinstance(data, dict):
        raise LLMError("LLM вернул неожиданный формат")
    return data


class BaseProvider:
    name = "base"

    def __init__(self) -> None:
        self.timeout = float(os.getenv("LLM_TIMEOUT", "25"))
        self.max_tokens = int(os.getenv("LLM_MAX_TOKENS", "1200"))
        self.model = os.getenv("LLM_MODEL", "")

    def available(self) -> bool:
        return False

    def complete(
        self,
        system: str,
        messages: Sequence[Dict[str, str]],
        max_tokens: Optional[int] = None,
    ) -> str:
        raise NotImplementedError


class OpenAIProvider(BaseProvider):
    name = "openai"

    def __init__(self) -> None:
        super().__init__()
        self.api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY", "")
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.model = self.model or "gpt-4o-mini"

    def available(self) -> bool:
        return bool(self.api_key)

    def complete(
        self,
        system: str,
        messages: Sequence[Dict[str, str]],
        max_tokens: Optional[int] = None,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "temperature": 0.2,
            "max_tokens": max_tokens or self.max_tokens,
        }
        data = _post_json(
            f"{self.base_url}/chat/completions",
            payload,
            {"Authorization": f"Bearer {self.api_key}"},
            self.timeout,
        )
        try:
            return str(data["choices"][0]["message"]["content"])  # type: ignore[index]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("OpenAI: нет choices[0].message.content") from exc


class AnthropicProvider(BaseProvider):
    name = "anthropic"

    def __init__(self) -> None:
        super().__init__()
        self.api_key = os.getenv("LLM_API_KEY") or os.getenv("ANTHROPIC_API_KEY", "")
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.anthropic.com").rstrip("/")
        self.model = self.model or "claude-3-5-sonnet-latest"

    def available(self) -> bool:
        return bool(self.api_key)

    def complete(
        self,
        system: str,
        messages: Sequence[Dict[str, str]],
        max_tokens: Optional[int] = None,
    ) -> str:
        payload = {
            "model": self.model,
            "system": system,
            "messages": list(messages),
            "temperature": 0.2,
            "max_tokens": max_tokens or self.max_tokens,
        }
        data = _post_json(
            f"{self.base_url}/v1/messages",
            payload,
            {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            self.timeout,
        )
        try:
            blocks = data["content"]  # type: ignore[index]
            return "".join(
                str(block.get("text", ""))
                for block in blocks
                if isinstance(block, dict)
            )
        except (KeyError, TypeError) as exc:
            raise LLMError("Anthropic: нет content") from exc


class YandexGPTProvider(BaseProvider):
    name = "yandex"

    def __init__(self) -> None:
        super().__init__()
        self.api_key = os.getenv("LLM_API_KEY") or os.getenv("YANDEX_API_KEY", "")
        self.folder = os.getenv("YANDEX_FOLDER_ID", "")
        self.base_url = os.getenv(
            "LLM_BASE_URL", "https://llm.api.cloud.yandex.net"
        ).rstrip("/")
        self.model = self.model or "yandexgpt-lite"

    def available(self) -> bool:
        return bool(self.api_key and self.folder)

    def complete(
        self,
        system: str,
        messages: Sequence[Dict[str, str]],
        max_tokens: Optional[int] = None,
    ) -> str:
        payload = {
            "modelUri": f"gpt://{self.folder}/{self.model}",
            "completionOptions": {
                "stream": False,
                "temperature": 0.2,
                "maxTokens": max_tokens or self.max_tokens,
            },
            "messages": [
                {"role": "system", "text": system},
                *[
                    {"role": item["role"], "text": item["content"]}
                    for item in messages
                ],
            ],
        }
        data = _post_json(
            f"{self.base_url}/foundationModels/v1/completion",
            payload,
            {"Authorization": f"Api-Key {self.api_key}"},
            self.timeout,
        )
        try:
            return str(data["result"]["alternatives"][0]["message"]["text"])  # type: ignore[index]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("YandexGPT: нет result.alternatives") from exc


class GigaChatProvider(BaseProvider):
    name = "gigachat"

    def __init__(self) -> None:
        super().__init__()
        self.api_key = os.getenv("LLM_API_KEY") or os.getenv("GIGACHAT_API_KEY", "")
        self.base_url = os.getenv(
            "LLM_BASE_URL", "https://gigachat.devices.sberbank.ru/api/v1"
        ).rstrip("/")
        self.oauth_url = os.getenv(
            "GIGACHAT_OAUTH_URL",
            "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
        )
        self.model = self.model or "GigaChat"
        self._token: Optional[str] = None
        self._token_expires_at = 0.0
        self._lock = threading.Lock()

    def available(self) -> bool:
        return bool(self.api_key)

    def _get_token(self) -> str:
        with self._lock:
            if self._token and time.time() < self._token_expires_at - 60:
                return self._token
            body = urllib.parse.urlencode({"scope": "GIGACHAT_API_PERS"}).encode("utf-8")
            request = urllib.request.Request(
                self.oauth_url,
                data=body,
                headers={
                    "Authorization": f"Basic {self.api_key}",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "RqUID": str(uuid.uuid4()),
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    data = json.loads(response.read().decode("utf-8", errors="replace"))
            except Exception as exc:  # noqa: BLE001
                raise LLMError(f"GigaChat OAuth failed: {exc}") from exc
            token = data.get("access_token")
            if not token:
                raise LLMError("GigaChat: нет access_token")
            self._token = str(token)
            self._token_expires_at = time.time() + float(data.get("expires_at", 1800))
            return self._token

    def complete(
        self,
        system: str,
        messages: Sequence[Dict[str, str]],
        max_tokens: Optional[int] = None,
    ) -> str:
        token = self._get_token()
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "temperature": 0.2,
            "max_tokens": max_tokens or self.max_tokens,
        }
        data = _post_json(
            f"{self.base_url}/chat/completions",
            payload,
            {"Authorization": f"Bearer {token}"},
            self.timeout,
        )
        try:
            return str(data["choices"][0]["message"]["content"])  # type: ignore[index]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("GigaChat: нет choices[0].message.content") from exc


_PROVIDER_LOCK = threading.Lock()
_PROVIDER: Optional[BaseProvider] = None
_PROVIDER_NAME: Optional[str] = None


def get_provider() -> Optional[BaseProvider]:
    global _PROVIDER, _PROVIDER_NAME
    name = os.getenv("LLM_PROVIDER", "").strip().lower()
    with _PROVIDER_LOCK:
        if _PROVIDER is not None and _PROVIDER_NAME == name:
            return _PROVIDER if _PROVIDER.available() else None
        provider: Optional[BaseProvider]
        if name in ("openai", "openai-compatible", "compatible"):
            provider = OpenAIProvider()
        elif name == "anthropic":
            provider = AnthropicProvider()
        elif name in ("yandex", "yandexgpt"):
            provider = YandexGPTProvider()
        elif name in ("gigachat", "sber"):
            provider = GigaChatProvider()
        else:
            provider = None
        _PROVIDER = provider
        _PROVIDER_NAME = name
        if provider is None or not provider.available():
            return None
        return provider


def provider_status() -> Dict[str, object]:
    provider = get_provider()
    return {
        "provider": provider.name if provider else "template",
        "llm_enabled": provider is not None,
        "model": provider.model if provider else None,
    }


# ---------------------------------------------------------------------------
# Модерация
# ---------------------------------------------------------------------------

_FORBIDDEN = (
    "обнал",
    "уйти от налог",
    "скрыть доход",
    "гарантированн",
    "без риска",
    "точно заработа",
    "100% доход",
    "инсайд",
    "взлом",
)


def moderate_question(question: str) -> Optional[str]:
    text = question.lower().replace("ё", "е")
    for marker in _FORBIDDEN:
        if marker in text:
            return (
                "Не могу помочь с гарантиями доходности или схемами ухода от "
                "налогов. Могу объяснить расчёт, риски и легальные налоговые "
                "вычеты. " + DISCLAIMER
            )
    return None


def moderate_answer(answer: str) -> str:
    text = answer.strip()
    if not text:
        return "Не удалось сформировать ответ. " + DISCLAIMER
    return text


# ---------------------------------------------------------------------------
# Публичные функции
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> Optional[Dict[str, object]]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _merge_explanation(
    payload: Dict[str, object],
    fallback: AIExplanation,
) -> AIExplanation:
    def text(key: str, default: str) -> str:
        value = payload.get(key)
        return str(value).strip() if isinstance(value, str) and value.strip() else default

    risk_profiles = fallback.risk_profiles
    raw_risks = payload.get("risk_profiles")
    if isinstance(raw_risks, dict):
        merged = dict(risk_profiles)
        for key in ("low", "medium", "high"):
            value = raw_risks.get(key)
            if isinstance(value, str) and value.strip():
                merged[key] = value.strip()
        risk_profiles = merged

    steps = fallback.steps
    raw_steps = payload.get("steps")
    if isinstance(raw_steps, list):
        cleaned_steps = [str(item).strip() for item in raw_steps if str(item).strip()]
        if cleaned_steps:
            steps = cleaned_steps[:7]

    return AIExplanation(
        summary=text("summary", fallback.summary),
        risk_profiles=risk_profiles,
        steps=steps,
        why=text("why", fallback.why),
        risks=text("risks", fallback.risks),
        disclaimer=text("disclaimer", fallback.disclaimer),
        generated_by="llm",
    )


def explain(
    context_id: Optional[str] = None,
    context: Optional[Dict[str, object]] = None,
    use_llm: bool = True,
) -> AIExplanation:
    resolved, resolved_id = resolve_context(context_id, context)
    if resolved is None:
        raise ValueError("Контекст не найден. Сначала выполните расчёт.")
    fallback = template_explanation(resolved)
    provider = get_provider() if use_llm else None
    if provider is None:
        return fallback

    cache_key = hashlib.sha256(
        f"{resolved_id}:{provider.name}:{provider.model}".encode("utf-8")
    ).hexdigest()
    cached = RESPONSE_CACHE.get(cache_key)
    if isinstance(cached, AIExplanation):
        return cached

    messages = [
        {
            "role": "user",
            "content": (
                "JSON-контекст расчёта:\n"
                + canonical_json(resolved)
                + "\n\nСформируй объяснение строго по схеме из системной инструкции."
            ),
        }
    ]
    try:
        raw = provider.complete(SYSTEM_PROMPT, messages, max_tokens=1400)
    except Exception:  # noqa: BLE001
        return fallback

    payload = _extract_json(raw)
    if payload is None:
        return fallback
    explanation = _merge_explanation(payload, fallback)
    violations = _validate_explanation(explanation, resolved)
    if violations:
        fallback.generated_by = "template:validator_fallback"
        return fallback
    RESPONSE_CACHE.set(cache_key, explanation, RESPONSE_TTL_SECONDS)
    return explanation


def chat(
    context_id: Optional[str] = None,
    context: Optional[Dict[str, object]] = None,
    question: str = "",
    history: Optional[Sequence[AIChatMessage]] = None,
    use_llm: bool = True,
) -> AIChatResponse:
    resolved, resolved_id = resolve_context(context_id, context)
    if resolved is None:
        raise ValueError("Контекст не найден. Сначала выполните расчёт.")
    if not question.strip():
        raise ValueError("Пустой вопрос.")

    moderated = moderate_question(question)
    if moderated:
        return AIChatResponse(
            answer=moderated,
            context_id=resolved_id,
            disclaimer=DISCLAIMER,
            generated_by="moderation",
        )

    fallback_answer = template_chat(resolved, question, history)
    provider = get_provider() if use_llm else None
    if provider is None:
        return AIChatResponse(
            answer=fallback_answer,
            context_id=resolved_id,
            disclaimer=DISCLAIMER,
            generated_by="template",
        )

    cache_key = hashlib.sha256(
        (
            f"{resolved_id}:{provider.name}:{provider.model}:"
            f"{question.strip()}:{canonical_json([m.model_dump() for m in (history or [])])}"
        ).encode("utf-8")
    ).hexdigest()
    cached = RESPONSE_CACHE.get(cache_key)
    if isinstance(cached, str):
        return AIChatResponse(
            answer=cached,
            context_id=resolved_id,
            disclaimer=DISCLAIMER,
            generated_by=f"llm:{provider.name}:cache",
        )

    messages: List[Dict[str, str]] = []
    for item in (history or [])[-8:]:
        messages.append({"role": item.role, "content": item.content})
    messages.append(
        {
            "role": "user",
            "content": (
                "JSON-контекст расчёта:\n"
                + canonical_json(resolved)
                + "\n\nВопрос пользователя: "
                + question.strip()
                + "\n\nОтветь текстом, используя только числа из контекста."
            ),
        }
    )
    try:
        answer = provider.complete(SYSTEM_PROMPT, messages, max_tokens=900)
    except Exception:  # noqa: BLE001
        answer = fallback_answer

    answer = moderate_answer(answer)
    violations = validate_numbers(answer, resolved)
    if violations:
        answer = fallback_answer
        generated_by = "template:validator_fallback"
    else:
        generated_by = f"llm:{provider.name}"
    RESPONSE_CACHE.set(cache_key, answer, RESPONSE_TTL_SECONDS)
    return AIChatResponse(
        answer=answer,
        context_id=resolved_id,
        disclaimer=DISCLAIMER,
        generated_by=generated_by,
    )


def _sse(event: str, payload: Dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def stream_explanation(
    context_id: Optional[str] = None,
    context: Optional[Dict[str, object]] = None,
    use_llm: bool = True,
) -> Iterator[str]:
    yield _sse("start", {"message": "Готовим объяснение", "context_id": context_id})
    try:
        explanation = explain(context_id=context_id, context=context, use_llm=use_llm)
    except Exception as exc:  # noqa: BLE001
        yield _sse("error", {"message": str(exc)})
        return
    payload = explanation.model_dump()
    summary = explanation.summary
    words = summary.split()
    buffer: List[str] = []
    for index, word in enumerate(words):
        buffer.append(word)
        if len(buffer) >= 6 or index == len(words) - 1:
            yield _sse("token", {"text": " ".join(buffer) + " "})
            buffer = []
    yield _sse("result", payload)
    yield _sse("done", {"generated_by": explanation.generated_by})


def stream_chat(
    context_id: Optional[str] = None,
    context: Optional[Dict[str, object]] = None,
    question: str = "",
    history: Optional[Sequence[AIChatMessage]] = None,
    use_llm: bool = True,
) -> Iterator[str]:
    yield _sse("start", {"message": "Думаем", "context_id": context_id})
    try:
        response = chat(
            context_id=context_id,
            context=context,
            question=question,
            history=history,
            use_llm=use_llm,
        )
    except Exception as exc:  # noqa: BLE001
        yield _sse("error", {"message": str(exc)})
        return
    text = response.answer
    chunk: List[str] = []
    for char in text:
        chunk.append(char)
        if len(chunk) >= 24:
            yield _sse("token", {"text": "".join(chunk)})
            chunk = []
    if chunk:
        yield _sse("token", {"text": "".join(chunk)})
    yield _sse("result", response.model_dump())
    yield _sse("done", {"generated_by": response.generated_by})
