"""Инструменты РФ, сценарии и портфельные характеристики.

Акции и криптовалюта в этой версии исключены. Доступны вклады,
накопительные счета, ОФЗ, корпоративные и муниципальные облигации,
недвижимость под аренду и ипотечные стратегии.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt
from typing import Dict, List, Optional, Sequence

from .models import LiquidityNeed, MacroSnapshot, RiskLevel, RiskTolerance, UserProfile

LIQUID_KEYS = {"cash", "savings", "deposit", "ofz_short"}


@dataclass(frozen=True)
class Asset:
    key: str
    name: str
    kind: str
    expected_return: float
    volatility: float
    liquidity: float
    duration_years: float
    credit_risk: float
    tax_type: str
    min_investment: float
    market_beta: float
    rate_beta: float
    inflation_beta: float
    fee_rate: float
    description: str


@dataclass
class Scenario:
    id: str
    name: str
    risk_level: RiskLevel
    weights: Dict[str, float]
    description: str
    tags: List[str] = field(default_factory=list)
    leverage: float = 0.0
    mortgage_rate: float = 0.0
    mortgage_term_months: int = 240


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def build_assets(macro: MacroSnapshot) -> Dict[str, Asset]:
    key_rate = macro.key_rate.value
    deposit_rate = macro.deposit_rate.value
    savings_rate = macro.savings_rate.value
    ofz_10y = macro.ofz_yield_10y.value
    corporate = macro.corporate_yield.value
    municipal = macro.municipal_yield.value
    growth = macro.real_estate_growth.value
    rent_yield = macro.rent_yield.value
    real_estate_return = rent_yield + growth - 0.02

    return {
        "cash": Asset(
            key="cash",
            name="Денежный резерв",
            kind="cash",
            expected_return=max(0.0, key_rate - 0.02),
            volatility=0.005,
            liquidity=1.0,
            duration_years=0.0,
            credit_risk=0.0,
            tax_type="interest",
            min_investment=0.0,
            market_beta=0.0,
            rate_beta=0.8,
            inflation_beta=0.2,
            fee_rate=0.0,
            description="Максимальная ликвидность, доходность почти не покрывает инфляцию.",
        ),
        "savings": Asset(
            key="savings",
            name="Накопительный счёт",
            kind="deposit",
            expected_return=savings_rate,
            volatility=0.005,
            liquidity=1.0,
            duration_years=0.0,
            credit_risk=0.02,
            tax_type="interest",
            min_investment=0.0,
            market_beta=0.0,
            rate_beta=0.7,
            inflation_beta=0.2,
            fee_rate=0.0,
            description="Ставка ниже вклада, но деньги доступны в любой момент.",
        ),
        "deposit": Asset(
            key="deposit",
            name="Банковский вклад",
            kind="deposit",
            expected_return=deposit_rate,
            volatility=0.01,
            liquidity=0.95,
            duration_years=0.0,
            credit_risk=0.03,
            tax_type="interest",
            min_investment=1_000.0,
            market_beta=0.0,
            rate_beta=0.6,
            inflation_beta=0.3,
            fee_rate=0.0,
            description="Предсказуемый процент, высокая ликвидность, страхование АСВ.",
        ),
        "ofz_short": Asset(
            key="ofz_short",
            name="Короткие ОФЗ",
            kind="bond",
            expected_return=max(0.05, key_rate - 0.005),
            volatility=0.03,
            liquidity=0.90,
            duration_years=2.0,
            credit_risk=0.03,
            tax_type="coupon",
            min_investment=1_000.0,
            market_beta=0.05,
            rate_beta=0.9,
            inflation_beta=0.1,
            fee_rate=0.002,
            description="Государственный риск, короткая дюрация, высокая ликвидность.",
        ),
        "ofz_long": Asset(
            key="ofz_long",
            name="Длинные ОФЗ",
            kind="bond",
            expected_return=ofz_10y,
            volatility=0.08,
            liquidity=0.80,
            duration_years=7.0,
            credit_risk=0.03,
            tax_type="coupon",
            min_investment=1_000.0,
            market_beta=0.10,
            rate_beta=1.0,
            inflation_beta=0.2,
            fee_rate=0.003,
            description="Купонный доход и рост цены при снижении ставок, но высокая дюрация.",
        ),
        "corporate": Asset(
            key="corporate",
            name="Корпоративные облигации IG",
            kind="bond",
            expected_return=corporate,
            volatility=0.10,
            liquidity=0.60,
            duration_years=4.0,
            credit_risk=0.35,
            tax_type="coupon",
            min_investment=1_000.0,
            market_beta=0.20,
            rate_beta=0.8,
            inflation_beta=0.2,
            fee_rate=0.004,
            description="Выше купон ОФЗ, но есть кредитный риск эмитента и ликвидности.",
        ),
        "municipal": Asset(
            key="municipal",
            name="Муниципальные облигации",
            kind="bond",
            expected_return=municipal,
            volatility=0.06,
            liquidity=0.70,
            duration_years=5.0,
            credit_risk=0.15,
            tax_type="coupon",
            min_investment=1_000.0,
            market_beta=0.10,
            rate_beta=0.9,
            inflation_beta=0.15,
            fee_rate=0.003,
            description="Компромисс между ОФЗ и корпоративным сегментом.",
        ),
        "real_estate": Asset(
            key="real_estate",
            name="Недвижимость под аренду",
            kind="real_estate",
            expected_return=real_estate_return,
            volatility=0.12,
            liquidity=0.15,
            duration_years=10.0,
            credit_risk=0.20,
            tax_type="rent",
            min_investment=1_500_000.0,
            market_beta=0.30,
            rate_beta=0.4,
            inflation_beta=0.9,
            fee_rate=0.01,
            description="Арендный поток и защита от инфляции, но низкая ликвидность и высокий порог входа.",
        ),
    }


def _normalize(weights: Dict[str, float]) -> Dict[str, float]:
    clean = {key: max(0.0, value) for key, value in weights.items() if value > 0}
    total = sum(clean.values())
    if total <= 0:
        return {}
    return {key: value / total for key, value in clean.items()}


def _enforce_liquidity(
    weights: Dict[str, float],
    liquidity_need: LiquidityNeed,
) -> Dict[str, float]:
    minimum = {
        LiquidityNeed.high: 0.30,
        LiquidityNeed.medium: 0.15,
        LiquidityNeed.low: 0.05,
    }[liquidity_need]
    result = _normalize(weights)
    liquid = sum(value for key, value in result.items() if key in LIQUID_KEYS)
    if liquid >= minimum - 1e-9:
        return result

    need = minimum - liquid
    # Забираем из самого неликвидного актива, затем из остальных.
    donors = sorted(
        (key for key in result if key not in LIQUID_KEYS),
        key=lambda key: result[key],
        reverse=True,
    )
    for key in donors:
        if need <= 1e-9:
            break
        take = min(result[key], need)
        result[key] -= take
        result["deposit"] = result.get("deposit", 0.0) + take
        need -= take
    return _normalize(result)


def _affordable(weights: Dict[str, float], capital: float, assets: Dict[str, Asset]) -> bool:
    for key, weight in weights.items():
        asset = assets[key]
        if asset.min_investment > 0 and weight * capital < asset.min_investment - 1e-9:
            return False
    return True


def scenario_templates(
    profile: UserProfile,
    macro: MacroSnapshot,
    assets: Dict[str, Asset],
    max_scenarios: int = 18,
) -> List[Scenario]:
    capital = profile.capital
    # Если стартового капитала мало, но есть ежемесячные взносы, инструмент
    # всё равно может стать доступен в первые месяцы горизонта.
    affordable_capital = max(capital, profile.monthly * 3.0)
    real_estate_ok = (
        profile.capital >= assets["real_estate"].min_investment
        and "real_estate" in assets
    )
    leverage_ok = (
        profile.credit_willingness
        and profile.credit_type.value == "mortgage"
        and profile.capital > 0
    )

    raw: List[Scenario] = []

    def add(
        key: str,
        name: str,
        level: RiskLevel,
        weights: Dict[str, float],
        description: str,
        tags: Optional[List[str]] = None,
        leverage: float = 0.0,
        mortgage_rate: float = 0.0,
    ) -> None:
        adjusted = _enforce_liquidity(weights, profile.liquidity_need)
        if not adjusted:
            return
        if leverage <= 0 and not _affordable(adjusted, affordable_capital, assets):
            return
        raw.append(
            Scenario(
                id=key,
                name=name,
                risk_level=level,
                weights=adjusted,
                description=description,
                tags=tags or [],
                leverage=leverage,
                mortgage_rate=mortgage_rate,
            )
        )

    # --- Низкий риск -----------------------------------------------------
    add(
        "low_savings", "Накопительный счёт", RiskLevel.low,
        {"savings": 1.0},
        "Максимальная ликвидность и минимальный риск. Подходит для резерва и коротких целей.",
        ["ликвидность", "резерв"],
    )
    add(
        "low_deposit", "Банковский вклад", RiskLevel.low,
        {"deposit": 1.0},
        "Фиксированная ставка и страхование АСВ в пределах лимита.",
        ["вклад", "АСВ"],
    )
    add(
        "low_deposit_ofz", "Вклад + короткие ОФЗ 70/30", RiskLevel.low,
        {"deposit": 0.70, "ofz_short": 0.30},
        "Основная часть в защищённом вкладе, небольшая доля в коротких ОФЗ.",
        ["вклад", "ОФЗ"],
    )
    add(
        "low_balanced", "Вклад + ОФЗ 50/50", RiskLevel.low,
        {"deposit": 0.50, "ofz_short": 0.50},
        "Чуть больше купонного дохода при короткой дюрации.",
        ["вклад", "ОФЗ"],
    )
    add(
        "low_mix", "Консервативный микс", RiskLevel.low,
        {"deposit": 0.40, "ofz_short": 0.40, "municipal": 0.20},
        "Вклад, короткие ОФЗ и муниципальные облигации для диверсификации.",
        ["диверсификация", "облигации"],
    )

    # --- Средний риск ----------------------------------------------------
    add(
        "medium_ofz_deposit", "ОФЗ 10 лет + вклад 60/40", RiskLevel.medium,
        {"ofz_long": 0.60, "deposit": 0.40},
        "Длинные ОФЗ дают купон и потенциал роста при снижении ставок.",
        ["ОФЗ", "дюрация"],
    )
    add(
        "medium_bond_mix", "ОФЗ + корпоративные + вклад", RiskLevel.medium,
        {"ofz_long": 0.50, "corporate": 0.30, "deposit": 0.20},
        "Классический облигационный портфель с разной кредитной нагрузкой.",
        ["облигации", "диверсификация"],
    )
    add(
        "medium_bonds", "Облигационный микс", RiskLevel.medium,
        {"ofz_long": 0.40, "corporate": 0.30, "municipal": 0.30},
        "Сочетание государственного, муниципального и корпоративного долга.",
        ["облигации", "купон"],
    )
    add(
        "medium_corp_muni", "Корпоративные + муниципальные 50/50", RiskLevel.medium,
        {"corporate": 0.50, "municipal": 0.50},
        "Более высокая купонная доходность при умеренном кредитном риске.",
        ["купон", "кредитный риск"],
    )
    if real_estate_ok:
        add(
            "medium_real_estate", "Недвижимость + ОФЗ 60/40", RiskLevel.medium,
            {"real_estate": 0.60, "ofz_long": 0.40},
            "Арендный поток и защита от инфляции плюс облигационная подушка.",
            ["недвижимость", "аренда"],
        )
        add(
            "medium_real_estate_mix", "Недвижимость + корпоративные + вклад", RiskLevel.medium,
            {"real_estate": 0.50, "corporate": 0.30, "deposit": 0.20},
            "Недвижимость как основа, облигации и вклад — для ликвидности.",
            ["недвижимость", "ликвидность"],
        )

    # --- Высокий риск ----------------------------------------------------
    add(
        "high_long_ofz", "Длинные ОФЗ", RiskLevel.high,
        {"ofz_long": 1.0},
        "Максимальная чувствительность к ставке: рост цены при снижении ключевой.",
        ["дюрация", "ставка"],
    )
    add(
        "high_corp_ofz", "Корпоративные + длинные ОФЗ 70/30", RiskLevel.high,
        {"corporate": 0.70, "ofz_long": 0.30},
        "Кредитная премия и дюрация — высокий потенциал, но и просадки.",
        ["кредитный риск", "дюрация"],
    )
    if real_estate_ok:
        add(
            "high_real_estate", "Недвижимость + корпоративные 50/50", RiskLevel.high,
            {"real_estate": 0.50, "corporate": 0.50},
            "Недвижимость с арендой и корпоративный долг с высокой доходностью.",
            ["недвижимость", "кредитный риск"],
        )
        add(
            "high_aggressive", "Агрессивный микс", RiskLevel.high,
            {"corporate": 0.40, "ofz_long": 0.30, "real_estate": 0.30},
            "Максимальная доходность в облигационно-недвижимом портфеле.",
            ["агрессивный", "диверсификация"],
        )
    if leverage_ok:
        add(
            "high_mortgage", "Ипотечная недвижимость", RiskLevel.high,
            {"real_estate": 1.0},
            "Покупка недвижимости с ипотекой: плечо усиливает и доход, и риск.",
            ["ипотека", "плечо"],
            leverage=0.70,
            mortgage_rate=macro.mortgage_rate.value,
        )
        add(
            "high_mortgage_mix", "Ипотека + облигации", RiskLevel.high,
            {"real_estate": 0.80, "corporate": 0.20},
            "Недвижимость с плечом и облигационная подушка.",
            ["ипотека", "плечо", "облигации"],
            leverage=0.60,
            mortgage_rate=macro.mortgage_rate.value,
        )

    # Добираем до 10–20 сценариев нейтральными комбинациями.
    extras = [
        ("low_extra", "Вклад + муниципальные 80/20", RiskLevel.low,
         {"deposit": 0.80, "municipal": 0.20}, "Умеренная добавка муниципального долга."),
        ("medium_extra", "ОФЗ + муниципальные 60/40", RiskLevel.medium,
         {"ofz_long": 0.60, "municipal": 0.40}, "Средняя дюрация и умеренный кредитный риск."),
        ("high_extra", "Корпоративные + муниципальные 70/30", RiskLevel.high,
         {"corporate": 0.70, "municipal": 0.30}, "Кредитная премия при высокой дюрации."),
    ]
    existing = {scenario.id for scenario in raw}
    for key, name, level, weights, description in extras:
        if key not in existing:
            add(key, name, level, weights, description, ["дополнительный"])

    # Ограничиваем количество, сохраняя все три уровня риска.
    by_level: Dict[RiskLevel, List[Scenario]] = {level: [] for level in RiskLevel}
    for scenario in raw:
        by_level[scenario.risk_level].append(scenario)

    selected: List[Scenario] = []
    for level in (RiskLevel.low, RiskLevel.medium, RiskLevel.high):
        selected.extend(by_level[level][: max(3, max_scenarios // 3)])
    if len(selected) < max_scenarios:
        for scenario in raw:
            if scenario not in selected:
                selected.append(scenario)
            if len(selected) >= max_scenarios:
                break
    return selected[:max_scenarios]


def portfolio_expected_return(
    weights: Dict[str, float],
    assets: Dict[str, Asset],
) -> float:
    return sum(weight * assets[key].expected_return for key, weight in weights.items())


def _correlation(left: Asset, right: Asset) -> float:
    if left.key == right.key:
        return 1.0
    value = (
        left.market_beta * right.market_beta
        + 0.4 * left.rate_beta * right.rate_beta
        + 0.3 * left.inflation_beta * right.inflation_beta
    )
    return _clamp(value, -0.95, 0.95)


def portfolio_volatility(
    weights: Dict[str, float],
    assets: Dict[str, Asset],
) -> float:
    keys = list(weights)
    variance = 0.0
    for left in keys:
        for right in keys:
            variance += (
                weights[left]
                * weights[right]
                * assets[left].volatility
                * assets[right].volatility
                * _correlation(assets[left], assets[right])
            )
    return sqrt(max(0.0, variance))


def portfolio_duration(
    weights: Dict[str, float],
    assets: Dict[str, Asset],
) -> float:
    return sum(weight * assets[key].duration_years for key, weight in weights.items())


def portfolio_liquidity(
    weights: Dict[str, float],
    assets: Dict[str, Asset],
) -> float:
    return sum(weight * assets[key].liquidity for key, weight in weights.items())


def liquidity_label(value: float) -> str:
    if value >= 0.80:
        return "Высокая"
    if value >= 0.45:
        return "Средняя"
    return "Низкая"


def allocation_items(
    weights: Dict[str, float],
    capital: float,
    assets: Dict[str, Asset],
) -> List[Dict[str, object]]:
    items: List[Dict[str, object]] = []
    for key, weight in sorted(weights.items(), key=lambda pair: pair[1], reverse=True):
        asset = assets[key]
        if asset.tax_type == "interest":
            tax_note = "НДФЛ 13–22% с процентов сверх ключевая ставка × 1 млн ₽"
        elif asset.tax_type == "coupon":
            tax_note = "НДФЛ 13–15% с купона; ИИС может уменьшить налог"
        elif asset.tax_type == "rent":
            tax_note = "НДФЛ 13–15% с аренды; возможен имущественный вычет"
        else:
            tax_note = "Налог зависит от режима"
        items.append(
            {
                "key": key,
                "name": asset.name,
                "weight": round(weight, 4),
                "amount": round(weight * capital, 2),
                "expected_return": round(asset.expected_return, 4),
                "volatility": round(asset.volatility, 4),
                "liquidity": asset.liquidity,
                "tax_type": asset.tax_type,
                "tax_note": tax_note,
            }
        )
    return items
