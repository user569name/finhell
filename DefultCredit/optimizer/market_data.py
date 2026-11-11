"""Макроданные: ЦБ РФ, MOEX ISS, банковские ставки и недвижимость.

Логика:
  * по умолчанию отдаём демо-срез с явной пометкой fallback;
  * при refresh=true пытаемся получить живые данные ЦБ/MOEX с коротким
    таймаутом и кэшируем результат;
  * при любой ошибке сохраняем последние значения и помечаем источник;
  * банковские ставки и недвижимость — ручной/админский ввод, т.к.
    единого открытого API в РФ нет.
"""

from __future__ import annotations

import json
import re
import statistics
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from .models import (
    CurvePoint,
    DataPoint,
    DataSourceInfo,
    MacroSnapshot,
    MarketOverrides,
)

CBR_FX_URL = "https://www.cbr.ru/scripts/XML_daily.asp"
CBR_KEY_RATE_URL = "https://www.cbr.ru/hd_base/KeyRate/"
CBR_INFLATION_URL = "https://www.cbr.ru/statistics/macro_itm/inflation/"
MOEX_BONDS_URLS = (
    "https://iss.moex.com/iss/engines/stock/markets/bonds/boards/TQOB/"
    "securities.json?iss.meta=off&iss.only=securities,marketdata",
    "https://iss.moex.com/iss/engines/stock/markets/bonds/boards/TQCB/"
    "securities.json?iss.meta=off&iss.only=securities,marketdata",
)

USER_AGENT = "CapitalOptimizer/2.0 (+educational; contact: local)"
LIVE_TIMEOUT = 4.0
CACHE_TTL_SECONDS = 6 * 60 * 60
DEFAULT_TTL_SECONDS = 5 * 60


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class _CacheEntry:
    value: object
    expires_at: float


class TTLCache:
    """Простой потокобезопасный TTL-кэш; в production заменяется Redis."""

    def __init__(self) -> None:
        self._items: Dict[str, _CacheEntry] = {}

    def get(self, key: str) -> Optional[object]:
        entry = self._items.get(key)
        if entry is None:
            return None
        if entry.expires_at < time.time():
            self._items.pop(key, None)
            return None
        return entry.value

    def set(self, key: str, value: object, ttl: float) -> None:
        self._items[key] = _CacheEntry(value=value, expires_at=time.time() + ttl)


CACHE = TTLCache()


def _default_curve() -> list[CurvePoint]:
    # Иллюстративная кривая; в live-режиме заменяется данными MOEX/ЦБ.
    return [
        CurvePoint(tenor_months=3, yield_rate=0.150),
        CurvePoint(tenor_months=6, yield_rate=0.148),
        CurvePoint(tenor_months=12, yield_rate=0.145),
        CurvePoint(tenor_months=24, yield_rate=0.140),
        CurvePoint(tenor_months=36, yield_rate=0.137),
        CurvePoint(tenor_months=60, yield_rate=0.135),
        CurvePoint(tenor_months=84, yield_rate=0.134),
        CurvePoint(tenor_months=120, yield_rate=0.135),
        CurvePoint(tenor_months=180, yield_rate=0.140),
        CurvePoint(tenor_months=240, yield_rate=0.145),
    ]


def _dp(
    value: float,
    source: str,
    *,
    unit: str = "ratio",
    fallback: bool = True,
    note: Optional[str] = None,
    updated_at: Optional[str] = None,
) -> DataPoint:
    return DataPoint(
        value=value,
        unit=unit,
        source=source,
        updated_at=updated_at or _now_iso(),
        is_fallback=fallback,
        note=note,
    )


def default_macro() -> MacroSnapshot:
    """Демо-срез, если живые API недоступны.

    Значения — ориентиры для сценариев, а не прогноз. Пользователь может
    переопределить любое значение вручную.
    """
    now = _now_iso()
    sources = [
        DataSourceInfo(
            key="cbr",
            name="Банк России",
            url="https://www.cbr.ru/",
            status="fallback",
            updated_at=now,
            note="Ключевая ставка, инфляция и курсы: демо-значения до обновления.",
        ),
        DataSourceInfo(
            key="moex",
            name="Московская Биржа (MOEX ISS)",
            url="https://iss.moex.com/",
            status="fallback",
            updated_at=now,
            note="Доходности ОФЗ и корпоративных облигаций: демо-значения.",
        ),
        DataSourceInfo(
            key="bank_rates",
            name="Агрегатор банковских ставок",
            url=None,
            status="manual",
            updated_at=now,
            note="Среднерыночные ставки по вкладам и кредитам: ручной/админский ввод.",
        ),
        DataSourceInfo(
            key="real_estate",
            name="Рынок недвижимости",
            url=None,
            status="manual",
            updated_at=now,
            note="Средняя доходность аренды и рост цен: админ-панель/ручной ввод.",
        ),
    ]
    return MacroSnapshot(
        key_rate=_dp(0.16, "Банк России / демо", note="Ключевая ставка"),
        inflation_yoy=_dp(0.085, "Банк России / демо", note="Инфляция год к году"),
        inflation_expected=_dp(0.060, "Банк России / демо", note="Ожидаемая инфляция"),
        deposit_rate=_dp(0.150, "Агрегатор / демо", note="Средняя ставка по вкладам"),
        savings_rate=_dp(0.140, "Агрегатор / демо", note="Накопительный счёт"),
        credit_rate=_dp(0.240, "Агрегатор / демо", note="Потребительский кредит"),
        mortgage_rate=_dp(0.200, "Агрегатор / демо", note="Ипотека"),
        ofz_yield_10y=_dp(0.135, "MOEX / демо", note="ОФЗ, 10 лет"),
        corporate_yield=_dp(0.165, "MOEX / демо", note="Корпоративные облигации IG"),
        municipal_yield=_dp(0.145, "MOEX / демо", note="Муниципальные облигации"),
        real_estate_growth=_dp(0.080, "Админ-панель / демо", note="Рост цен на недвижимость"),
        rent_yield=_dp(0.050, "Админ-панель / демо", note="Доходность аренды"),
        usd_rub=_dp(90.0, "Банк России / демо", unit="rub", note="Курс USD/RUB"),
        eur_rub=_dp(100.0, "Банк России / демо", unit="rub", note="Курс EUR/RUB"),
        ofz_curve=_default_curve(),
        fetched_at=now,
        data_sources=sources,
    )


def _fetch_text(url: str, timeout: float = LIVE_TIMEOUT) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _fetch_json(url: str, timeout: float = LIVE_TIMEOUT) -> object:
    return json.loads(_fetch_text(url, timeout=timeout))


def fetch_cbr_fx() -> Optional[Tuple[float, float, str]]:
    """Курсы USD/RUB и EUR/RUB с XML-эндпоинта ЦБ."""
    try:
        raw = _fetch_text(CBR_FX_URL)
        root = ET.fromstring(raw)
        date = root.attrib.get("Date", _now_iso())
        values: Dict[str, float] = {}
        for valute in root.findall("Valute"):
            code = valute.findtext("CharCode")
            nominal = float(valute.findtext("Nominal", "1").replace(",", "."))
            value = float(valute.findtext("Value", "0").replace(",", "."))
            if code in {"USD", "EUR"} and nominal > 0:
                values[code] = value / nominal
        if "USD" in values and "EUR" in values:
            return values["USD"], values["EUR"], date
    except Exception:
        return None
    return None


def fetch_cbr_key_rate() -> Optional[float]:
    """Ключевая ставка: best-effort парсинг публичной страницы ЦБ."""
    try:
        html = _fetch_text(CBR_KEY_RATE_URL)
        rates = re.findall(r"<td[^>]*>\s*(\d{1,2}[.,]\d{1,2})\s*</td>", html)
        if rates:
            return float(rates[-1].replace(",", ".")) / 100.0
    except Exception:
        return None
    return None


def fetch_cbr_inflation() -> Optional[float]:
    """Инфляция год к году: best-effort парсинг страницы ЦБ."""
    try:
        html = _fetch_text(CBR_INFLATION_URL)
        match = re.search(
            r"инфляц[^<]{0,300}?(\d{1,2}[.,]\d{1,2})\s*%",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if match:
            return float(match.group(1).replace(",", ".")) / 100.0
    except Exception:
        return None
    return None


def _parse_moex_board(payload: object) -> Tuple[list[float], list[float]]:
    """Разобрать один ответ MOEX ISS.

    securities и marketdata — параллельные массивы строк: строка i в обоих
    блоках относится к одной бумаге. Поэтому сопоставляем по индексу, а не
    по SECID из marketdata (там первым столбцом идёт BOARDID).
    """
    ofz: list[float] = []
    corporate: list[float] = []
    if not isinstance(payload, dict):
        return ofz, corporate
    securities = payload.get("securities") or {}
    marketdata = payload.get("marketdata") or {}
    if not isinstance(securities, dict) or not isinstance(marketdata, dict):
        return ofz, corporate
    sec_columns = securities.get("columns") or []
    md_columns = marketdata.get("columns") or []
    sec_rows = securities.get("data") or []
    md_rows = marketdata.get("data") or []
    if not sec_columns or not md_columns:
        return ofz, corporate

    sec_index = {name: index for index, name in enumerate(sec_columns)}
    md_index = {name: index for index, name in enumerate(md_columns)}
    secid_i = sec_index.get("SECID")
    short_i = sec_index.get("SHORTNAME")
    yield_i = md_index.get("YIELD")
    if secid_i is None or yield_i is None:
        return ofz, corporate

    for index, sec_row in enumerate(sec_rows):
        if index >= len(md_rows):
            break
        if not isinstance(sec_row, list) or len(sec_row) <= secid_i:
            continue
        md_row = md_rows[index]
        if not isinstance(md_row, list) or len(md_row) <= yield_i:
            continue
        raw_yield = md_row[yield_i]
        if raw_yield in (None, ""):
            continue
        try:
            value = float(raw_yield) / 100.0
        except (TypeError, ValueError):
            continue
        if value <= 0 or value > 1:
            continue
        secid = str(sec_row[secid_i])
        short = (
            str(sec_row[short_i])
            if short_i is not None and len(sec_row) > short_i
            else ""
        )
        if secid.startswith("SU") or "ОФЗ" in short.upper():
            ofz.append(value)
        else:
            corporate.append(value)
    return ofz, corporate


def fetch_moex_bonds() -> Optional[Tuple[float, float, str]]:
    """Средние доходности ОФЗ и корпоративных облигаций с MOEX ISS."""
    ofz: list[float] = []
    corporate: list[float] = []
    try:
        for url in MOEX_BONDS_URLS:
            try:
                payload = _fetch_json(url)
            except Exception:
                continue
            board_ofz, board_corporate = _parse_moex_board(payload)
            ofz.extend(board_ofz)
            corporate.extend(board_corporate)
        if not ofz and not corporate:
            return None
        ofz_yield = statistics.median(ofz) if ofz else None
        corp_yield = statistics.median(corporate) if corporate else None
        return (
            ofz_yield if ofz_yield is not None else 0.0,
            corp_yield if corp_yield is not None else 0.0,
            _now_iso(),
        )
    except Exception:
        return None


def _apply_overrides(
    macro: MacroSnapshot,
    overrides: Optional[MarketOverrides],
) -> MacroSnapshot:
    if overrides is None:
        return macro
    data = macro.model_dump()
    changed = False
    for field, value in overrides.model_dump(exclude_none=True).items():
        if field in data and isinstance(data[field], dict):
            data[field] = {
                **data[field],
                "value": float(value),
                "source": "Пользовательские данные",
                "updated_at": _now_iso(),
                "is_fallback": False,
                "note": "Ручной ввод пользователя",
            }
            changed = True
    if changed:
        data["data_sources"] = list(data["data_sources"]) + [
            DataSourceInfo(
                key="user_override",
                name="Пользовательские данные",
                status="manual",
                updated_at=_now_iso(),
                note="Часть макропараметров изменена вручную.",
            )
        ]
        data["fetched_at"] = _now_iso()
    return MacroSnapshot(**data)


def get_macro_snapshot(
    refresh: bool = False,
    overrides: Optional[MarketOverrides] = None,
) -> MacroSnapshot:
    """Вернуть макросрез.

    refresh=False отдаёт кэш или демо-срез, не блокируя запрос сетью.
    refresh=True пытается обновить данные ЦБ/ MOEX; при ошибке — fallback.
    """
    if not refresh:
        cached = CACHE.get("macro_v2")
        if isinstance(cached, MacroSnapshot):
            return _apply_overrides(cached.model_copy(deep=True), overrides)
        macro = default_macro()
        CACHE.set("macro_v2", macro.model_copy(deep=True), DEFAULT_TTL_SECONDS)
        return _apply_overrides(macro, overrides)

    macro = default_macro()
    sources = {source.key: source for source in macro.data_sources}
    live_any = False

    fx = fetch_cbr_fx()
    if fx is not None:
        usd, eur, date = fx
        macro.usd_rub = _dp(usd, "Банк России", unit="rub", fallback=False, updated_at=date)
        macro.eur_rub = _dp(eur, "Банк России", unit="rub", fallback=False, updated_at=date)
        live_any = True
        sources["cbr"] = sources["cbr"].model_copy(
            update={"status": "live", "updated_at": date, "note": "Курсы валют ЦБ РФ."}
        )

    key_rate = fetch_cbr_key_rate()
    if key_rate is not None:
        macro.key_rate = _dp(key_rate, "Банк России", fallback=False, note="Ключевая ставка")
        live_any = True

    inflation = fetch_cbr_inflation()
    if inflation is not None:
        macro.inflation_yoy = _dp(
            inflation, "Банк России", fallback=False, note="Инфляция год к году"
        )
        live_any = True

    moex = fetch_moex_bonds()
    if moex is not None:
        ofz_yield, corp_yield, date = moex
        if ofz_yield > 0:
            macro.ofz_yield_10y = _dp(
                ofz_yield, "MOEX ISS", fallback=False, updated_at=date, note="Средняя доходность ОФЗ"
            )
        if corp_yield > 0:
            macro.corporate_yield = _dp(
                corp_yield, "MOEX ISS", fallback=False, updated_at=date,
                note="Средняя доходность корпоративных облигаций",
            )
        live_any = True
        sources["moex"] = sources["moex"].model_copy(
            update={
                "status": "live",
                "updated_at": date,
                "note": "Доходности облигаций MOEX ISS.",
            }
        )

    if not live_any:
        sources["cbr"] = sources["cbr"].model_copy(
            update={"status": "fallback", "note": "ЦБ РФ недоступен, используются демо-значения."}
        )
        sources["moex"] = sources["moex"].model_copy(
            update={"status": "fallback", "note": "MOEX недоступен, используются демо-значения."}
        )

    macro.fetched_at = _now_iso()
    macro.data_sources = list(sources.values())
    CACHE.set("macro_v2", macro.model_copy(deep=True), CACHE_TTL_SECONDS)
    return _apply_overrides(macro, overrides)


def macro_to_dict(macro: MacroSnapshot) -> Dict[str, object]:
    return macro.model_dump()
