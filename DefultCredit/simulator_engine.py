"""
Движок экономического симулятора.

Что умеет:
  * каталог инструментов: деньги, вклад, ОФЗ, корпоративные облигации,
    акции, золото, недвижимость, криптовалюта;
  * факторы риска (рыночный, кредитный, процентный, ликвидности,
    валютный, инфляционный) и их влияние на волатильность;
  * подбор структуры портфеля под срок, сумму и риск-профиль;
  * Монте-Карло (p10 / p50 / p90, вероятность цели, просадки);
  * расчёт облигации: текущая доходность, YTM, дюрация, купонный доход.

Модуль не зависит от FastAPI и может использоваться отдельно.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil, log, sqrt
from random import Random
from typing import Dict, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Константы и каталог инструментов
# ---------------------------------------------------------------------------

RISK_FACTOR_KEYS: Tuple[str, ...] = (
    "market",
    "credit",
    "rate",
    "liquidity",
    "currency",
    "inflation",
)

RISK_FACTOR_LABELS: Dict[str, str] = {
    "market": "Рыночный риск",
    "credit": "Кредитный риск",
    "rate": "Процентный риск",
    "liquidity": "Риск ликвидности",
    "currency": "Валютный риск",
    "inflation": "Инфляционный риск",
}

DEFAULT_RISK_FACTORS: Dict[str, float] = {
    "market": 0.50,
    "credit": 0.30,
    "rate": 0.40,
    "liquidity": 0.20,
    "currency": 0.30,
    "inflation": 0.50,
}

RISK_PROFILES: Dict[str, Dict[str, object]] = {
    "conservative": {
        "label": "Консервативный",
        "risk_aversion": 3.0,
        "deposit_floor": 0.35,
        "description": (
            "Главное — сохранить капитал. Основа: вклад, ОФЗ и немного "
            "корпоративных облигаций. Акции и криптовалюта — минимально "
            "или совсем без них."
        ),
    },
    "balanced": {
        "label": "Сбалансированный",
        "risk_aversion": 1.2,
        "deposit_floor": 0.12,
        "description": (
            "Компромисс между доходностью и риском. Облигации дают "
            "предсказуемый доход, акции и золото — защиту от инфляции "
            "и рост на длинном горизонте."
        ),
    },
    "aggressive": {
        "label": "Агрессивный",
        "risk_aversion": 0.45,
        "deposit_floor": 0.05,
        "description": (
            "Максимум роста на длинном горизонте. Большая доля акций, "
            "корпоративных облигаций и небольшая доля криптовалюты. "
            "Возможны глубокие просадки."
        ),
    },
}

PROFILE_BASELINES: Dict[str, Dict[str, float]] = {
    "conservative": {
        "cash": 0.05,
        "deposit": 0.40,
        "ofz": 0.30,
        "corporate_bonds": 0.15,
        "gold": 0.10,
    },
    "balanced": {
        "cash": 0.03,
        "deposit": 0.20,
        "ofz": 0.25,
        "corporate_bonds": 0.20,
        "stocks": 0.22,
        "gold": 0.10,
    },
    "aggressive": {
        "cash": 0.02,
        "deposit": 0.08,
        "ofz": 0.15,
        "corporate_bonds": 0.20,
        "stocks": 0.42,
        "gold": 0.08,
        "crypto": 0.05,
    },
}


@dataclass(frozen=True)
class Instrument:
    key: str
    name: str
    short_name: str
    annual_return: float
    volatility: float
    base_risk: float
    liquidity: float
    min_investment: float
    max_share: Dict[str, float]
    factor_loadings: Dict[str, float]
    description: str
    income_type: str = "interest"


# Доходности и волатильности — это ориентиры-допущения, а не прогноз.
# Их можно переопределить в запросе через return_overrides.
INSTRUMENTS: Dict[str, Instrument] = {
    "cash": Instrument(
        key="cash",
        name="Денежный резерв / накопительный счёт",
        short_name="Деньги",
        annual_return=0.03,
        volatility=0.005,
        base_risk=0.02,
        liquidity=1.0,
        min_investment=0.0,
        max_share={"conservative": 0.10, "balanced": 0.05, "aggressive": 0.03},
        factor_loadings={"inflation": 0.90, "rate": 0.30, "currency": 0.10},
        description=(
            "Максимальная ликвидность. Доходность почти не покрывает "
            "инфляцию, зато деньги доступны в любой момент."
        ),
        income_type="cash",
    ),
    "deposit": Instrument(
        key="deposit",
        name="Банковский вклад",
        short_name="Вклад",
        annual_return=0.15,
        volatility=0.01,
        base_risk=0.08,
        liquidity=1.0,
        min_investment=1_000.0,
        max_share={"conservative": 0.80, "balanced": 0.45, "aggressive": 0.25},
        factor_loadings={"inflation": 0.50, "rate": 0.60, "credit": 0.15},
        description=(
            "Предсказуемый процент и высокая ликвидность. Вклады "
            "застрахованы государством в пределах лимита АСВ."
        ),
        income_type="interest",
    ),
    "ofz": Instrument(
        key="ofz",
        name="ОФЗ — государственные облигации",
        short_name="ОФЗ",
        annual_return=0.135,
        volatility=0.055,
        base_risk=0.16,
        liquidity=0.90,
        min_investment=1_000.0,
        max_share={"conservative": 0.60, "balanced": 0.45, "aggressive": 0.30},
        factor_loadings={
            "market": 0.10,
            "credit": 0.05,
            "rate": 0.85,
            "liquidity": 0.10,
            "inflation": 0.30,
        },
        description=(
            "Самый надёжный рыночный инструмент. Купонный доход, "
            "высокая ликвидность и низкий кредитный риск."
        ),
        income_type="coupon",
    ),
    "corporate_bonds": Instrument(
        key="corporate_bonds",
        name="Корпоративные облигации",
        short_name="Корп. облигации",
        annual_return=0.165,
        volatility=0.12,
        base_risk=0.32,
        liquidity=0.60,
        min_investment=1_000.0,
        max_share={"conservative": 0.20, "balanced": 0.25, "aggressive": 0.30},
        factor_loadings={
            "market": 0.25,
            "credit": 0.75,
            "rate": 0.60,
            "liquidity": 0.35,
            "currency": 0.10,
            "inflation": 0.30,
        },
        description=(
            "Выше купон, чем у ОФЗ, но есть кредитный риск эмитента "
            "и риск ликвидности. Лучше держать до погашения."
        ),
        income_type="coupon",
    ),
    "stocks": Instrument(
        key="stocks",
        name="Акции / индекс широкого рынка",
        short_name="Акции",
        annual_return=0.20,
        volatility=0.25,
        base_risk=0.65,
        liquidity=0.90,
        min_investment=1_000.0,
        max_share={"conservative": 0.10, "balanced": 0.40, "aggressive": 0.65},
        factor_loadings={
            "market": 0.95,
            "credit": 0.15,
            "rate": 0.30,
            "liquidity": 0.10,
            "currency": 0.20,
            "inflation": 0.40,
        },
        description=(
            "Главный двигатель доходности на длинном горизонте. "
            "Высокая волатильность и глубокие просадки в кризисы."
        ),
        income_type="dividends",
    ),
    "gold": Instrument(
        key="gold",
        name="Золото",
        short_name="Золото",
        annual_return=0.11,
        volatility=0.17,
        base_risk=0.42,
        liquidity=0.80,
        min_investment=1_000.0,
        max_share={"conservative": 0.10, "balanced": 0.08, "aggressive": 0.15},
        factor_loadings={
            "market": 0.35,
            "rate": 0.35,
            "liquidity": 0.15,
            "currency": 0.80,
            "inflation": 0.75,
        },
        description=(
            "Защита от инфляции и ослабления валюты. Не платит купоны "
            "и дивиденды, может долго стоять на месте."
        ),
        income_type="price",
    ),
    "real_estate": Instrument(
        key="real_estate",
        name="Недвижимость",
        short_name="Недвижимость",
        annual_return=0.13,
        volatility=0.10,
        base_risk=0.48,
        liquidity=0.15,
        min_investment=1_500_000.0,
        max_share={"conservative": 0.10, "balanced": 0.15, "aggressive": 0.20},
        factor_loadings={
            "market": 0.50,
            "credit": 0.20,
            "rate": 0.55,
            "liquidity": 0.90,
            "currency": 0.05,
            "inflation": 0.85,
        },
        description=(
            "Защита от инфляции и арендный поток, но высокий порог "
            "входа и низкая ликвидность. В модели — без ипотеки."
        ),
        income_type="rent",
    ),
    "crypto": Instrument(
        key="crypto",
        name="Криптовалюта",
        short_name="Крипта",
        annual_return=0.28,
        volatility=0.55,
        base_risk=0.90,
        liquidity=0.80,
        min_investment=1_000.0,
        max_share={"conservative": 0.0, "balanced": 0.03, "aggressive": 0.08},
        factor_loadings={
            "market": 0.90,
            "credit": 0.05,
            "rate": 0.20,
            "liquidity": 0.20,
            "currency": 0.60,
            "inflation": 0.10,
        },
        description=(
            "Высокий потенциал роста и очень высокая волатильность. "
            "Только как небольшая спекулятивная доля портфеля."
        ),
        income_type="price",
    ),
}


@dataclass
class Debt:
    name: str
    balance: float
    annual_rate: float
    monthly_payment: float = 0.0


@dataclass
class SimulationParams:
    initial_capital: float
    monthly_contribution: float
    horizon_months: int
    risk_profile: str = "balanced"
    inflation_rate: float = 0.08
    monthly_expenses: float = 0.0
    emergency_fund_months: int = 6
    goal_amount: Optional[float] = None
    risk_factors: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_RISK_FACTORS))
    asset_risk_overrides: Dict[str, float] = field(default_factory=dict)
    return_overrides: Dict[str, float] = field(default_factory=dict)
    include_crypto: bool = True
    monte_carlo_paths: int = 800
    seed: int = 42
    debts: List[Debt] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Риск и доходность отдельных инструментов
# ---------------------------------------------------------------------------

def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def factor_exposure(instrument: Instrument, factors: Dict[str, float]) -> float:
    """Средневзвешенная подверженность инструмента факторам риска (0..1)."""
    loadings = instrument.factor_loadings
    total = sum(loadings.values())
    if total <= 0:
        return 0.0
    weighted = sum(
        loadings.get(key, 0.0) * clamp(factors.get(key, 0.0))
        for key in loadings
    )
    return weighted / total


def effective_risk(
    instrument: Instrument,
    factors: Dict[str, float],
    override: Optional[float] = None,
) -> float:
    """Итоговая оценка риска инструмента с учётом факторов (0..1)."""
    if override is not None:
        return clamp(override)
    exposure = factor_exposure(instrument, factors)
    score = instrument.base_risk * (0.75 + 0.50 * exposure) + 0.10 * exposure
    return clamp(score)


def effective_volatility(
    instrument: Instrument,
    factors: Dict[str, float],
    override: Optional[float] = None,
) -> float:
    """Волатильность растёт вместе с оценкой риска."""
    risk = effective_risk(instrument, factors, override)
    return instrument.volatility * (0.75 + 0.75 * risk)


def expected_return(instrument: Instrument, params: SimulationParams) -> float:
    return float(params.return_overrides.get(instrument.key, instrument.annual_return))


# ---------------------------------------------------------------------------
# Подбор структуры портфеля
# ---------------------------------------------------------------------------

def _is_eligible(instrument: Instrument, params: SimulationParams, capital: float) -> bool:
    key = instrument.key
    horizon = params.horizon_months
    if key == "cash" or key == "deposit":
        return True
    if key == "ofz":
        return horizon >= 3
    if key == "corporate_bonds":
        return horizon >= 12
    if key == "stocks":
        return horizon >= 18
    if key == "gold":
        return horizon >= 12
    if key == "real_estate":
        return horizon >= 48 and capital >= instrument.min_investment
    if key == "crypto":
        return (
            params.include_crypto
            and params.risk_profile != "conservative"
            and horizon >= 24
        )
    return True


def _horizon_cap_factor(key: str, horizon: int) -> float:
    if key == "ofz":
        return clamp(horizon / 24.0)
    if key == "stocks":
        return clamp((horizon - 18) / 42.0)
    if key == "crypto":
        return clamp((horizon - 24) / 36.0)
    if key == "corporate_bonds":
        return clamp((horizon - 6) / 30.0)
    if key == "gold":
        return clamp((horizon - 12) / 24.0)
    if key == "real_estate":
        return clamp(horizon / 60.0)
    return 1.0


def _score_weights(
    params: SimulationParams,
    capital: float,
) -> Tuple[Dict[str, float], Dict[str, Dict[str, float]]]:
    profile = RISK_PROFILES[params.risk_profile]
    horizon = params.horizon_months
    inflation = params.inflation_rate
    risk_aversion = float(profile["risk_aversion"])
    # На коротком горизонте риск штрафуется сильнее.
    horizon_multiplier = 1.0 + max(0.0, (60 - horizon) / 60.0)
    lam = risk_aversion * horizon_multiplier

    scores: Dict[str, float] = {}
    caps: Dict[str, float] = {}
    floors: Dict[str, float] = {}
    details: Dict[str, Dict[str, float]] = {}

    for key, instrument in INSTRUMENTS.items():
        if not _is_eligible(instrument, params, capital):
            continue

        ret = expected_return(instrument, params)
        risk = effective_risk(
            instrument,
            params.risk_factors,
            params.asset_risk_overrides.get(key),
        )
        vol = effective_volatility(
            instrument,
            params.risk_factors,
            params.asset_risk_overrides.get(key),
        )
        real_ret = (1.0 + ret) / (1.0 + inflation) - 1.0
        score = real_ret - 0.5 * lam * vol * vol

        # Неликвидные активы на коротком горизонте менее уместны.
        if horizon < 36:
            score -= 0.02 * (1.0 - instrument.liquidity)
        if key == "real_estate":
            score -= 0.01
        score = max(0.0, score)

        cap = instrument.max_share.get(params.risk_profile, 0.0)
        cap *= _horizon_cap_factor(key, horizon)
        cap = clamp(cap)

        floor = 0.0
        if key == "cash":
            floor = 0.02
        elif key == "deposit":
            floor = float(profile["deposit_floor"])
        elif key == "ofz" and horizon >= 6:
            floor = 0.05
        elif key == "gold" and params.risk_factors.get("inflation", 0.0) >= 0.40:
            floor = 0.03
        floor = min(floor, cap)

        scores[key] = score
        caps[key] = cap
        floors[key] = floor
        details[key] = {
            "expected_return": ret,
            "real_return": real_ret,
            "risk": risk,
            "volatility": vol,
            "score": score,
            "cap": cap,
            "floor": floor,
        }

    if "deposit" not in scores:
        scores["deposit"] = 1.0
        caps["deposit"] = 1.0
        floors["deposit"] = 0.0
        details["deposit"] = {
            "expected_return": INSTRUMENTS["deposit"].annual_return,
            "real_return": 0.0,
            "risk": 0.0,
            "volatility": 0.0,
            "score": 1.0,
            "cap": 1.0,
            "floor": 0.0,
        }

    # Базовая стратегия профиля + оптимизационная поправка по score.
    baseline_raw = {
        key: PROFILE_BASELINES[params.risk_profile].get(key, 0.0)
        for key in scores
    }
    baseline_total = sum(baseline_raw.values())
    if baseline_total > 0:
        baseline = {key: value / baseline_total for key, value in baseline_raw.items()}
    else:
        baseline = {key: 1.0 / len(scores) for key in scores}

    score_total = sum(scores.values())
    if score_total > 0:
        score_norm = {key: value / score_total for key, value in scores.items()}
    else:
        score_norm = {key: 1.0 / len(scores) for key in scores}

    blended = {
        key: 0.55 * baseline[key] + 0.45 * score_norm[key]
        for key in scores
    }

    # Сумма caps должна позволять набрать 100%.
    if sum(caps.values()) < 1.0:
        caps["deposit"] = caps.get("deposit", 0.0) + (1.0 - sum(caps.values()))

    # Сумма floors не должна превышать 100%.
    floor_total = sum(floors.values())
    if floor_total > 1.0:
        floors = {key: value / floor_total * 0.95 for key, value in floors.items()}

    weights = _apply_limits(blended, caps, floors)
    weights = _drop_small_real_estate(weights, caps, floors, capital)
    return weights, details


def _apply_limits(
    weights: Dict[str, float],
    caps: Dict[str, float],
    floors: Dict[str, float],
) -> Dict[str, float]:
    keys = list(weights)
    total = sum(max(0.0, weights[key]) for key in keys)
    if total <= 0:
        result = {key: 1.0 / len(keys) for key in keys}
    else:
        result = {key: max(0.0, weights[key]) / total for key in keys}

    for _ in range(200):
        excess = 0.0
        for key in keys:
            cap = caps.get(key, 1.0)
            if result[key] > cap + 1e-12:
                excess += result[key] - cap
                result[key] = cap

        if excess > 1e-12:
            room = {
                key: caps.get(key, 1.0) - result[key]
                for key in keys
                if caps.get(key, 1.0) - result[key] > 1e-12
            }
            total_room = sum(room.values())
            if total_room > 1e-12:
                for key, value in room.items():
                    result[key] += excess * value / total_room

        deficit = 0.0
        for key in keys:
            floor = floors.get(key, 0.0)
            if result[key] < floor - 1e-12:
                deficit += floor - result[key]
                result[key] = floor

        if deficit > 1e-12:
            room = {
                key: result[key] - floors.get(key, 0.0)
                for key in keys
                if result[key] - floors.get(key, 0.0) > 1e-12
            }
            total_room = sum(room.values())
            if total_room > 1e-12:
                for key, value in room.items():
                    result[key] -= deficit * value / total_room

        if excess <= 1e-12 and deficit <= 1e-12:
            break

    total = sum(result.values())
    if total > 0:
        result = {key: value / total for key, value in result.items()}
    return {key: value for key, value in result.items() if value > 1e-6}


def _drop_small_real_estate(
    weights: Dict[str, float],
    caps: Dict[str, float],
    floors: Dict[str, float],
    capital: float,
) -> Dict[str, float]:
    """Убирает недвижимость, если на неё не хватает минимальной суммы."""
    instrument = INSTRUMENTS["real_estate"]
    weight = weights.get("real_estate", 0.0)
    if weight <= 0:
        return weights
    if capital < instrument.min_investment:
        return weights
    if weight * capital >= instrument.min_investment - 1e-9:
        return weights

    remaining = {key: value for key, value in weights.items() if key != "real_estate"}
    if not remaining:
        return {"deposit": 1.0}
    total = sum(remaining.values())
    remaining = {key: value / total for key, value in remaining.items()}
    remaining = _apply_limits(
        remaining,
        {key: caps.get(key, 1.0) for key in remaining},
        {key: floors.get(key, 0.0) for key in remaining},
    )
    return remaining


def portfolio_volatility(weights: Dict[str, float], params: SimulationParams) -> float:
    """Волатильность портфеля с учётом общей рыночной компоненты."""
    keys = list(weights)
    vols = {
        key: effective_volatility(
            INSTRUMENTS[key],
            params.risk_factors,
            params.asset_risk_overrides.get(key),
        )
        for key in keys
    }
    market = {
        key: clamp(INSTRUMENTS[key].factor_loadings.get("market", 0.0))
        for key in keys
    }
    variance = 0.0
    for left in keys:
        for right in keys:
            if left == right:
                correlation = 1.0
            else:
                correlation = sqrt(market[left] * market[right])
            variance += (
                weights[left]
                * weights[right]
                * vols[left]
                * vols[right]
                * correlation
            )
    return sqrt(max(0.0, variance))


def risk_label(score: float) -> str:
    if score < 0.18:
        return "Низкий"
    if score < 0.35:
        return "Умеренный"
    if score < 0.55:
        return "Повышенный"
    return "Высокий"


def build_allocation(
    params: SimulationParams,
    investable_capital: float,
) -> Dict[str, object]:
    weights, details = _score_weights(params, investable_capital)
    items: List[Dict[str, object]] = []

    for key, share in sorted(weights.items(), key=lambda pair: pair[1], reverse=True):
        instrument = INSTRUMENTS[key]
        info = details[key]
        items.append(
            {
                "key": key,
                "name": instrument.name,
                "short_name": instrument.short_name,
                "share": round(share, 4),
                "initial_amount": round(share * investable_capital, 2),
                "monthly_amount": round(share * params.monthly_contribution, 2),
                "expected_return": round(info["expected_return"], 4),
                "real_return": round(info["real_return"], 4),
                "risk": round(info["risk"], 4),
                "volatility": round(info["volatility"], 4),
                "liquidity": instrument.liquidity,
                "min_investment": instrument.min_investment,
                "description": instrument.description,
                "income_type": instrument.income_type,
                "score": round(info["score"], 6),
            }
        )

    expected = sum(
        item["share"] * item["expected_return"] for item in items
    )
    expected_real = (1.0 + expected) / (1.0 + params.inflation_rate) - 1.0
    risk = sum(item["share"] * item["risk"] for item in items)
    volatility = portfolio_volatility(weights, params)

    return {
        "items": items,
        "weights": weights,
        "expected_return": round(expected, 4),
        "real_expected_return": round(expected_real, 4),
        "risk": round(risk, 4),
        "volatility": round(volatility, 4),
        "risk_label": risk_label(risk),
    }
