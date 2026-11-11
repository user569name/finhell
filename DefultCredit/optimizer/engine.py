"""Расчётный движок оптимизатора капитала.

Содержит:
  * генерацию сценариев;
  * Монте-Карло (нормальное / t-Стьюдента / историческое);
  * метрики риска и доходности;
  * стресс-тесты;
  * сравнения «аренда vs покупка» и «погасить vs вложить»;
  * ранжирование сценариев внутри трёх уровней риска.
"""

from __future__ import annotations

import math
import random
import uuid
import zlib
from datetime import datetime, timezone
from statistics import mean
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from . import ai
from .instruments import (
    Asset,
    Scenario,
    allocation_items,
    build_assets,
    liquidity_label,
    portfolio_duration,
    portfolio_expected_return,
    portfolio_liquidity,
    portfolio_volatility,
    scenario_templates,
)
from .market_data import get_macro_snapshot
from .models import (
    AllocationItem,
    ComparisonItem,
    ComparisonResult,
    FeeSummary,
    LiquidityNeed,
    MacroSnapshot,
    MonteCarloSummary,
    OptimizeRequest,
    OptimizeResponse,
    RiskLevel,
    RiskProfileResult,
    ScenarioResult,
    StressResult,
    TaxSummary,
    UserProfile,
)
from .taxes import (
    annuity_payment,
    cashflow_irr,
    cashflow_npv,
    coupon_tax,
    deposit_interest_tax,
    iis_deduction,
    loan_remaining_balance,
    loan_total_interest,
    property_deduction,
    rent_tax,
)

DISCLAIMER = (
    "Это не индивидуальная инвестиционная рекомендация. Расчёты основаны "
    "на модельных допущениях и доступных макроданных; фактические доходности, "
    "ставки, налоги и цены могут отличаться. Проверяйте условия у банка, "
    "брокера и налогового консультанта."
)

RISK_LABELS = {
    RiskLevel.low: "Низкий риск",
    RiskLevel.medium: "Средний риск",
    RiskLevel.high: "Высокий риск",
}

RISK_DESCRIPTIONS = {
    RiskLevel.low: "Вклады, накопительные счета и короткие ОФЗ. Главное — сохранить капитал и ликвидность.",
    RiskLevel.medium: "Длинные ОФЗ, корпоративные и муниципальные облигации, недвижимость под аренду.",
    RiskLevel.high: "Длинная дюрация, кредитный риск, ипотечное плечо и недвижимость с заёмными средствами.",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _annual_to_monthly(rate: float) -> float:
    return (1.0 + rate) ** (1.0 / 12.0) - 1.0


def _scenario_seed(base_seed: int, scenario_id: str, salt: int = 0) -> int:
    """Детерминированное зерно, не зависящее от PYTHONHASHSEED."""
    checksum = zlib.crc32(scenario_id.encode("utf-8")) & 0x7FFFFFFF
    return int(base_seed + checksum % 100_000 + salt) % 2_147_483_647


def _future_value(initial: float, monthly: float, years: float, annual_return: float) -> float:
    months = max(1, int(round(years * 12)))
    monthly_rate = _annual_to_monthly(annual_return)
    value = initial
    for _ in range(months):
        value *= 1.0 + monthly_rate
        value += monthly
    return value


def _percentile(sorted_values: Sequence[float], quantile: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    position = (len(sorted_values) - 1) * max(0.0, min(1.0, quantile))
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower
    return float(sorted_values[lower] * (1.0 - fraction) + sorted_values[upper] * fraction)


def _histogram(values: Sequence[float], bins: int = 20) -> List[Dict[str, float]]:
    if not values:
        return []
    low, high = min(values), max(values)
    if high <= low:
        return [{"from": round(low, 2), "to": round(high, 2), "count": len(values)}]
    width = (high - low) / bins
    counts = [0] * bins
    for value in values:
        index = min(bins - 1, int((value - low) / width))
        counts[index] += 1
    return [
        {
            "from": round(low + index * width, 2),
            "to": round(low + (index + 1) * width, 2),
            "count": counts[index],
        }
        for index in range(bins)
    ]


def _normalized_betas(asset: Asset) -> Tuple[float, float, float, float]:
    """Возвращает market, rate, inflation и долю идиосинкратического шума."""
    market = max(0.0, asset.market_beta)
    rate = max(0.0, asset.rate_beta)
    inflation = max(0.0, asset.inflation_beta)
    norm = math.sqrt(market * market + rate * rate + inflation * inflation)
    if norm > 0.98:
        scale = 0.98 / norm
        market *= scale
        rate *= scale
        inflation *= scale
    idiosyncratic = math.sqrt(max(0.0, 1.0 - market * market - rate * rate - inflation * inflation))
    return market, rate, inflation, idiosyncratic


def _tax_summary(
    scenario: Scenario,
    profile: UserProfile,
    macro: MacroSnapshot,
    assets: Dict[str, Asset],
    years: float,
) -> TaxSummary:
    interest_income = 0.0
    coupon_income = 0.0
    rent_income = 0.0
    for key, weight in scenario.weights.items():
        asset = assets[key]
        income = profile.capital * weight * asset.expected_return
        if asset.tax_type == "interest":
            interest_income += income
        elif asset.tax_type == "coupon":
            coupon_income += income
        elif asset.tax_type == "rent":
            rent_income += income

    annual_tax = deposit_interest_tax(interest_income, macro.key_rate.value)
    if not (profile.iis and profile.iis.type == "B"):
        annual_tax += coupon_tax(coupon_income)
    annual_tax += rent_tax(rent_income)

    deductions = 0.0
    if profile.iis and profile.iis.type == "A":
        deductions = iis_deduction(
            profile.iis.annual_contribution,
            profile.iis.type,
            tax_paid=annual_tax,
        )
    net_tax = max(0.0, annual_tax - deductions)
    total_tax = net_tax * years
    effective = net_tax / profile.capital if profile.capital > 0 else 0.0
    note = (
        "Оценка НДФЛ: проценты по вкладам — сверх порога ключевая ставка × 1 млн ₽, "
        "купоны — 13–15%, аренда — 13–15%. ИИС и имущественный вычет учтены упрощённо."
    )
    return TaxSummary(
        annual_tax=round(net_tax, 2),
        total_tax_estimate=round(total_tax, 2),
        effective_rate=round(effective, 4),
        deductions=round(deductions, 2),
        note=note,
    )


def _fee_summary(
    scenario: Scenario,
    profile: UserProfile,
    assets: Dict[str, Asset],
    years: float,
) -> FeeSummary:
    weighted_fee = sum(
        weight * assets[key].fee_rate for key, weight in scenario.weights.items()
    )
    annual_fee = profile.capital * weighted_fee
    total_fee = annual_fee * years
    return FeeSummary(
        annual_fee=round(annual_fee, 2),
        total_fee_estimate=round(total_fee, 2),
        effective_rate=round(weighted_fee, 4),
        note="Комиссии брокера, биржи, управления недвижимостью и транзакционные издержки.",
    )


def _prepare_assets(
    scenario: Scenario,
    profile: UserProfile,
    macro: MacroSnapshot,
    assets: Dict[str, Asset],
    years: float,
) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, float], Dict[str, Tuple[float, float, float, float]]]:
    """Привести доходности к посленалоговым и послекомиссионным.

    Налог считается по типу дохода (проценты / купон / аренда), а не
    размазывается по всему портфелю. Комиссия вычитается из доходности
    конкретного инструмента.
    """
    taxes = _tax_summary(scenario, profile, macro, assets, years)

    interest_income = 0.0
    coupon_income = 0.0
    rent_income = 0.0
    for key, weight in scenario.weights.items():
        asset = assets[key]
        income = profile.capital * weight * asset.expected_return
        if asset.tax_type == "interest":
            interest_income += income
        elif asset.tax_type == "coupon":
            coupon_income += income
        elif asset.tax_type == "rent":
            rent_income += income

    interest_tax = deposit_interest_tax(interest_income, macro.key_rate.value)
    coupon_tax_amount = 0.0
    if not (profile.iis and profile.iis.type == "B"):
        coupon_tax_amount = coupon_tax(coupon_income)
    rent_tax_amount = rent_tax(rent_income)
    gross_tax = interest_tax + coupon_tax_amount + rent_tax_amount
    # Учитываем вычеты ИИС: уменьшаем эффективную ставку пропорционально.
    scale = taxes.annual_tax / gross_tax if gross_tax > 1e-9 else 0.0
    tax_rates = {
        "interest": (interest_tax * scale / interest_income) if interest_income > 1e-9 else 0.0,
        "coupon": (coupon_tax_amount * scale / coupon_income) if coupon_income > 1e-9 else 0.0,
        "rent": (rent_tax_amount * scale / rent_income) if rent_income > 1e-9 else 0.0,
    }

    monthly_mu: Dict[str, float] = {}
    monthly_sigma: Dict[str, float] = {}
    weights: Dict[str, float] = {}
    betas: Dict[str, Tuple[float, float, float, float]] = {}

    for key, weight in scenario.weights.items():
        asset = assets[key]
        tax_rate = max(0.0, min(0.60, tax_rates.get(asset.tax_type, 0.0)))
        net_return = asset.expected_return * (1.0 - tax_rate) - asset.fee_rate
        monthly_mu[key] = _annual_to_monthly(max(-0.95, net_return))
        monthly_sigma[key] = asset.volatility / math.sqrt(12.0)
        weights[key] = weight
        betas[key] = _normalized_betas(asset)

    total = sum(weights.values())
    if total <= 0:
        weights = {"deposit": 1.0}
        monthly_mu = {"deposit": _annual_to_monthly(0.0)}
        monthly_sigma = {"deposit": 0.0}
        betas = {"deposit": (0.0, 0.0, 0.0, 1.0)}
    else:
        weights = {key: value / total for key, value in weights.items()}
    return weights, monthly_mu, monthly_sigma, betas


def _simulate_standard(
    scenario: Scenario,
    profile: UserProfile,
    macro: MacroSnapshot,
    assets: Dict[str, Asset],
    options,
    *,
    include_stress: bool = True,
    paths_override: Optional[int] = None,
) -> Dict[str, object]:
    horizon = profile.horizon_months
    years = horizon / 12.0
    weights, monthly_mu, monthly_sigma, betas = _prepare_assets(
        scenario, profile, macro, assets, years
    )
    expected_return = portfolio_expected_return(scenario.weights, assets)
    volatility = portfolio_volatility(scenario.weights, assets)
    duration = portfolio_duration(scenario.weights, assets)
    liquidity = portfolio_liquidity(scenario.weights, assets)
    taxes = _tax_summary(scenario, profile, macro, assets, years)
    fees = _fee_summary(scenario, profile, assets, years)
    tax_drag = taxes.effective_rate
    fee_drag = fees.effective_rate
    after_tax_return = expected_return - tax_drag - fee_drag
    after_tax_return = max(-0.95, after_tax_return)

    paths = int(paths_override or options.monte_carlo_paths)
    paths = max(100, paths)
    rng = random.Random(_scenario_seed(options.seed, scenario.id))
    distribution = options.distribution.value
    initial = profile.capital
    monthly = profile.monthly
    total_contributions = initial + monthly * horizon

    history: Dict[str, List[float]] = {}
    if distribution == "historical":
        history_rng = random.Random(options.seed + 991)
        for key in weights:
            mu = monthly_mu[key]
            sigma = monthly_sigma[key]
            history[key] = [
                max(-0.95, mu + sigma * history_rng.gauss(0.0, 1.0))
                for _ in range(120)
            ]

    terminal_values: List[float] = []
    drawdowns: List[float] = []
    monthly_returns_sample: List[float] = []
    yearly_values: Dict[int, List[float]] = {0: [initial]}
    sample_paths: List[List[float]] = []
    year_marks = set(range(12, horizon + 1, 12))
    if horizon not in year_marks:
        year_marks.add(horizon)

    for path_index in range(paths):
        value = initial
        peak = value
        max_drawdown = 0.0
        path_values = [value] if path_index < 50 else None
        for month in range(1, horizon + 1):
            if distribution == "student_t":
                chi2 = rng.gammavariate(2.5, 2.0)
                t_scale = math.sqrt(5.0 / max(1e-9, chi2))
                systemic = rng.gauss(0.0, 1.0) * t_scale
            elif distribution == "historical":
                systemic = 0.0
            else:
                systemic = rng.gauss(0.0, 1.0)

            portfolio_return = 0.0
            for key, weight in weights.items():
                if distribution == "historical":
                    asset_return = rng.choice(history[key])
                else:
                    market_beta, rate_beta, inflation_beta, idio = betas[key]
                    # Один системный шок + идиосинкратический шум.
                    systemic_loading = math.sqrt(
                        max(0.0, market_beta * market_beta + rate_beta * rate_beta + inflation_beta * inflation_beta)
                    )
                    shock = systemic_loading * systemic + idio * rng.gauss(0.0, 1.0)
                    asset_return = monthly_mu[key] + monthly_sigma[key] * shock
                asset_return = max(-0.95, asset_return)
                portfolio_return += weight * asset_return

            value *= 1.0 + portfolio_return
            value += monthly
            if path_index < 1000:
                monthly_returns_sample.append(portfolio_return)
            if value > peak:
                peak = value
            if peak > 0:
                max_drawdown = max(max_drawdown, (peak - value) / peak)
            if month in year_marks:
                yearly_values.setdefault(month, []).append(value)
            if path_values is not None:
                path_values.append(value)

        terminal_values.append(value)
        drawdowns.append(max_drawdown)
        if path_values is not None:
            sample_paths.append(path_values)

    terminal_sorted = sorted(terminal_values)
    drawdown_sorted = sorted(drawdowns)
    p5 = _percentile(terminal_sorted, 0.05)
    p25 = _percentile(terminal_sorted, 0.25)
    p50 = _percentile(terminal_sorted, 0.50)
    p75 = _percentile(terminal_sorted, 0.75)
    p95 = _percentile(terminal_sorted, 0.95)
    inflation_factor = (1.0 + macro.inflation_expected.value) ** years
    real_p50 = p50 / inflation_factor if inflation_factor > 0 else p50

    terminal_returns = [
        (value / total_contributions - 1.0) if total_contributions > 0 else 0.0
        for value in terminal_values
    ]
    terminal_returns_sorted = sorted(terminal_returns)
    var_95 = _percentile(terminal_returns_sorted, 0.05)
    tail = [value for value in terminal_returns_sorted if value <= var_95]
    cvar_95 = mean(tail) if tail else var_95

    probability_loss = sum(1 for value in terminal_values if value < total_contributions) / paths
    probability_goal = None
    if profile.goal_amount:
        probability_goal = sum(1 for value in terminal_values if value >= profile.goal_amount) / paths

    downside = 0.0
    if monthly_returns_sample:
        downside = math.sqrt(
            sum(min(0.0, value) ** 2 for value in monthly_returns_sample)
            / len(monthly_returns_sample)
        ) * math.sqrt(12.0)
    risk_free = macro.key_rate.value
    sharpe = (after_tax_return - risk_free) / volatility if volatility > 1e-9 else 0.0
    sortino = (
        (after_tax_return - risk_free) / downside
        if downside > 1e-9
        else 0.0
    )

    discount_rate = max(macro.key_rate.value, macro.inflation_expected.value + 0.02)
    npv_value = cashflow_npv(
        discount_rate, initial, monthly, horizon, p50
    )
    irr_value = cashflow_irr(initial, monthly, horizon, p50)

    series: List[Dict[str, float]] = [
        {"month": 0, "p5": round(initial, 2), "p50": round(initial, 2), "p95": round(initial, 2), "contributed": round(initial, 2)}
    ]
    for month in sorted(year_marks):
        values = yearly_values.get(month, [p50])
        ordered = sorted(values)
        series.append(
            {
                "month": month,
                "p5": round(_percentile(ordered, 0.05), 2),
                "p50": round(_percentile(ordered, 0.50), 2),
                "p95": round(_percentile(ordered, 0.95), 2),
                "contributed": round(initial + monthly * month, 2),
            }
        )

    mc = MonteCarloSummary(
        paths=paths,
        distribution=distribution,
        terminal_p5=round(p5, 2),
        terminal_p25=round(p25, 2),
        terminal_p50=round(p50, 2),
        terminal_p75=round(p75, 2),
        terminal_p95=round(p95, 2),
        real_terminal_p50=round(real_p50, 2),
        total_contributions=round(total_contributions, 2),
        probability_goal=round(probability_goal, 4) if probability_goal is not None else None,
        probability_loss=round(probability_loss, 4),
        var_95=round(var_95, 4),
        cvar_95=round(cvar_95, 4),
        max_drawdown_median=round(_percentile(drawdown_sorted, 0.50), 4),
        max_drawdown_p90=round(_percentile(drawdown_sorted, 0.90), 4),
        histogram=_histogram(terminal_values),
        series=series,
        sample_paths=[
            [round(value, 2) for value in path]
            for path in sample_paths[:30]
        ],
    )

    stress: List[StressResult] = []
    if include_stress and options.run_stress_tests:
        stress = _stress_tests(scenario, profile, macro, assets, expected_return, volatility, years)

    return {
        "scenario": scenario,
        "years": years,
        "expected_return": expected_return,
        "volatility": volatility,
        "duration": duration,
        "liquidity": liquidity,
        "taxes": taxes,
        "fees": fees,
        "after_tax_return": after_tax_return,
        "mc": mc,
        "sharpe": sharpe,
        "sortino": sortino,
        "var_95": var_95,
        "cvar_95": cvar_95,
        "max_drawdown": _percentile(drawdown_sorted, 0.50),
        "max_drawdown_p90": _percentile(drawdown_sorted, 0.90),
        "npv": npv_value,
        "irr": irr_value,
        "stress": stress,
        "allocation": allocation_items(scenario.weights, profile.capital, assets),
    }


def _simulate_leveraged(
    scenario: Scenario,
    profile: UserProfile,
    macro: MacroSnapshot,
    assets: Dict[str, Asset],
    options,
    *,
    include_stress: bool = True,
    paths_override: Optional[int] = None,
) -> Dict[str, object]:
    """Ипотечная недвижимость: первоначальный взнос + плечо + аренда."""
    horizon = profile.horizon_months
    years = horizon / 12.0
    leverage = min(0.85, max(0.0, scenario.leverage))
    property_value = profile.capital / max(0.15, 1.0 - leverage)
    mortgage = max(0.0, property_value - profile.capital)
    mortgage_rate = scenario.mortgage_rate or macro.mortgage_rate.value
    term = max(12, scenario.mortgage_term_months)
    payment = annuity_payment(mortgage, mortgage_rate, term)
    rent_monthly = property_value * macro.rent_yield.value / 12.0
    net_payment = max(0.0, payment - rent_monthly)
    side_monthly = max(0.0, profile.monthly - net_payment)
    total_contributions = profile.capital + profile.monthly * horizon

    growth = macro.real_estate_growth.value
    sigma = assets["real_estate"].volatility / math.sqrt(12.0)
    monthly_growth = _annual_to_monthly(growth)
    rng = random.Random(_scenario_seed(options.seed, scenario.id))
    paths = max(100, int(paths_override or options.monte_carlo_paths))
    terminal_values: List[float] = []
    drawdowns: List[float] = []
    yearly_values: Dict[int, List[float]] = {0: [profile.capital]}
    sample_paths: List[List[float]] = []
    year_marks = set(range(12, horizon + 1, 12))
    if horizon not in year_marks:
        year_marks.add(horizon)
    deposit_monthly = _annual_to_monthly(macro.deposit_rate.value)

    for path_index in range(paths):
        value = property_value
        side = 0.0
        peak = profile.capital
        max_drawdown = 0.0
        path_values = [profile.capital] if path_index < 50 else None
        for month in range(1, horizon + 1):
            value *= 1.0 + monthly_growth + sigma * rng.gauss(0.0, 1.0)
            side *= 1.0 + deposit_monthly
            side += side_monthly
            balance = loan_remaining_balance(mortgage, mortgage_rate, term, month)
            equity = max(0.0, value - balance) + side
            if equity > peak:
                peak = equity
            if peak > 0:
                max_drawdown = max(max_drawdown, (peak - equity) / peak)
            if month in year_marks:
                yearly_values.setdefault(month, []).append(equity)
            if path_values is not None:
                path_values.append(equity)
        total_interest = max(0.0, payment * horizon - (mortgage - loan_remaining_balance(mortgage, mortgage_rate, term, horizon)))
        tax_benefit = property_deduction(property_value, total_interest)
        terminal = equity + tax_benefit
        terminal_values.append(terminal)
        drawdowns.append(max_drawdown)
        if path_values is not None:
            sample_paths.append(path_values)

    terminal_sorted = sorted(terminal_values)
    drawdown_sorted = sorted(drawdowns)
    p5 = _percentile(terminal_sorted, 0.05)
    p25 = _percentile(terminal_sorted, 0.25)
    p50 = _percentile(terminal_sorted, 0.50)
    p75 = _percentile(terminal_sorted, 0.75)
    p95 = _percentile(terminal_sorted, 0.95)
    inflation_factor = (1.0 + macro.inflation_expected.value) ** years
    real_p50 = p50 / inflation_factor if inflation_factor > 0 else p50
    returns = [
        (value / total_contributions - 1.0) if total_contributions > 0 else 0.0
        for value in terminal_values
    ]
    returns_sorted = sorted(returns)
    var_95 = _percentile(returns_sorted, 0.05)
    tail = [value for value in returns_sorted if value <= var_95]
    cvar_95 = mean(tail) if tail else var_95
    probability_loss = sum(1 for value in terminal_values if value < total_contributions) / paths
    probability_goal = None
    if profile.goal_amount:
        probability_goal = sum(1 for value in terminal_values if value >= profile.goal_amount) / paths

    expected_return = (p50 / total_contributions) ** (1.0 / max(years, 1e-9)) - 1.0 if total_contributions > 0 else 0.0
    volatility = assets["real_estate"].volatility * (1.0 + leverage)
    risk_free = macro.key_rate.value
    sharpe = (expected_return - risk_free) / volatility if volatility > 1e-9 else 0.0
    sortino = sharpe * 1.2
    discount_rate = max(macro.key_rate.value, macro.inflation_expected.value + 0.02)
    npv_value = cashflow_npv(discount_rate, profile.capital, profile.monthly, horizon, p50)
    irr_value = cashflow_irr(profile.capital, profile.monthly, horizon, p50)

    series: List[Dict[str, float]] = [
        {"month": 0, "p5": round(profile.capital, 2), "p50": round(profile.capital, 2), "p95": round(profile.capital, 2), "contributed": round(profile.capital, 2)}
    ]
    for month in sorted(year_marks):
        values = yearly_values.get(month, [p50])
        ordered = sorted(values)
        series.append(
            {
                "month": month,
                "p5": round(_percentile(ordered, 0.05), 2),
                "p50": round(_percentile(ordered, 0.50), 2),
                "p95": round(_percentile(ordered, 0.95), 2),
                "contributed": round(profile.capital + profile.monthly * month, 2),
            }
        )

    mc = MonteCarloSummary(
        paths=paths,
        distribution=options.distribution.value,
        terminal_p5=round(p5, 2),
        terminal_p25=round(p25, 2),
        terminal_p50=round(p50, 2),
        terminal_p75=round(p75, 2),
        terminal_p95=round(p95, 2),
        real_terminal_p50=round(real_p50, 2),
        total_contributions=round(total_contributions, 2),
        probability_goal=round(probability_goal, 4) if probability_goal is not None else None,
        probability_loss=round(probability_loss, 4),
        var_95=round(var_95, 4),
        cvar_95=round(cvar_95, 4),
        max_drawdown_median=round(_percentile(drawdown_sorted, 0.50), 4),
        max_drawdown_p90=round(_percentile(drawdown_sorted, 0.90), 4),
        histogram=_histogram(terminal_values),
        series=series,
        sample_paths=[[round(value, 2) for value in path] for path in sample_paths[:30]],
    )

    taxes = TaxSummary(
        annual_tax=round(rent_tax(rent_monthly * 12), 2),
        total_tax_estimate=round(rent_tax(rent_monthly * 12) * years, 2),
        effective_rate=round(rent_tax(rent_monthly * 12) / max(1.0, profile.capital), 4),
        deductions=round(property_deduction(property_value, loan_total_interest(mortgage, mortgage_rate, term)), 2),
        note="НДФЛ с аренды и имущественный/процентный вычет; ипотечные платежи учтены в денежном потоке.",
    )
    fees = FeeSummary(
        annual_fee=round(property_value * 0.01, 2),
        total_fee_estimate=round(property_value * 0.01 * years, 2),
        effective_rate=0.01,
        note="Эксплуатация, страхование, налог на имущество и транзакционные издержки — 1% стоимости в год.",
    )
    allocation = [
        {
            "key": "real_estate",
            "name": "Недвижимость с ипотекой",
            "weight": 1.0,
            "amount": round(property_value, 2),
            "expected_return": round(expected_return, 4),
            "volatility": round(volatility, 4),
            "liquidity": 0.15,
            "tax_type": "rent",
            "tax_note": f"Плечо {leverage:.0%}, ставка {mortgage_rate:.1%}, платёж {payment:,.0f} ₽/мес",
        }
    ]
    stress: List[StressResult] = []
    if include_stress and options.run_stress_tests:
        stress = _stress_tests(
            scenario, profile, macro, assets, expected_return, volatility, years
        )
    return {
        "scenario": scenario,
        "years": years,
        "expected_return": expected_return,
        "volatility": volatility,
        "duration": 10.0,
        "liquidity": 0.15,
        "taxes": taxes,
        "fees": fees,
        "after_tax_return": expected_return,
        "mc": mc,
        "sharpe": sharpe,
        "sortino": sortino,
        "var_95": var_95,
        "cvar_95": cvar_95,
        "max_drawdown": _percentile(drawdown_sorted, 0.50),
        "max_drawdown_p90": _percentile(drawdown_sorted, 0.90),
        "npv": npv_value,
        "irr": irr_value,
        "stress": stress,
        "allocation": allocation,
    }


def _stress_tests(
    scenario: Scenario,
    profile: UserProfile,
    macro: MacroSnapshot,
    assets: Dict[str, Asset],
    base_return: float,
    volatility: float,
    years: float,
) -> List[StressResult]:
    """Детерминированные стресс-тесты по сценарной доходности."""
    initial = profile.capital
    monthly = profile.monthly
    base_terminal = _future_value(initial, monthly, years, base_return)
    if base_terminal <= 0:
        base_terminal = 1.0
    cases: List[Tuple[str, float, float, str]] = []

    for delta in (0.01, 0.03, 0.05):
        stressed = base_return + delta - 0.5 * delta * max(0.0, portfolio_duration(scenario.weights, assets))
        cases.append(
            (
                f"Ключевая ставка +{int(delta * 10_000)} bp",
                stressed,
                volatility,
                "Рост ставки: вклады и новые купоны доходнее, но цена длинных облигаций падает.",
            )
        )
        stressed_down = base_return - delta + 0.5 * delta * max(0.0, portfolio_duration(scenario.weights, assets))
        cases.append(
            (
                f"Ключевая ставка −{int(delta * 10_000)} bp",
                stressed_down,
                volatility,
                "Снижение ставки: длинные облигации выигрывают, но новые вклады менее доходны.",
            )
        )
    cases.append(
        (
            "Инфляция +3 п.п.",
            base_return - 0.02,
            volatility * 1.15,
            "Инфляционный шок: реальная доходность снижается, недвижимость частично защищает.",
        )
    )
    cases.append(
        (
            "Налоговый режим +2 п.п.",
            base_return - 0.02,
            volatility,
            "Увеличение налоговой нагрузки уменьшает чистый результат.",
        )
    )
    cases.append(
        (
            "Недвижимость −20%",
            base_return - (0.20 if "real_estate" in scenario.weights else 0.02),
            volatility * 1.2,
            "Падение цен на недвижимость и арендных ставок.",
        )
    )
    cases.append(
        (
            "Ипотечная ставка +3 п.п.",
            base_return - (0.03 * scenario.leverage if scenario.leverage else 0.005),
            volatility,
            "Рост ипотечной ставки увеличивает платёж и снижает плечо.",
        )
    )

    results: List[StressResult] = []
    for name, stressed_return, stressed_vol, note in cases:
        stressed_terminal = _future_value(initial, monthly, years, stressed_return)
        p5_return = stressed_return - 1.645 * stressed_vol
        p5_terminal = _future_value(initial, monthly, years, p5_return)
        base_p5_return = base_return - 1.645 * volatility
        base_p5_terminal = _future_value(initial, monthly, years, base_p5_return)
        results.append(
            StressResult(
                scenario=name,
                impact_p50=round(stressed_terminal / base_terminal - 1.0, 4),
                impact_p5=round(
                    (p5_terminal / base_p5_terminal - 1.0) if base_p5_terminal > 0 else 0.0,
                    4,
                ),
                terminal_p50=round(stressed_terminal, 2),
                note=note,
            )
        )
    return results


def _score_group(results: List[Dict[str, object]]) -> None:
    if not results:
        return

    def values(key: str) -> List[float]:
        return [float(result[key]) for result in results]

    def normalize(raw: List[float], invert: bool = False) -> List[float]:
        low, high = min(raw), max(raw)
        if high - low < 1e-12:
            return [0.5 for _ in raw]
        normalized = [(value - low) / (high - low) for value in raw]
        return [1.0 - value for value in normalized] if invert else normalized

    sharpes = normalize(values("sharpe"))
    npvs = normalize(values("npv"))
    goals = normalize(
        [
            float(result["mc"].probability_goal)
            if result["mc"].probability_goal is not None
            else 1.0 - float(result["mc"].probability_loss)
            for result in results
        ]
    )
    liquidity = normalize(values("liquidity"))
    drawdowns = normalize(
        [float(result["max_drawdown"]) for result in results], invert=True
    )
    stress_resilience_raw = []
    for result in results:
        impacts = [float(item.impact_p50) for item in result["stress"]]
        stress_resilience_raw.append(1.0 + min(impacts) if impacts else 1.0)
    stress = normalize(stress_resilience_raw)

    for index, result in enumerate(results):
        score = (
            0.30 * sharpes[index]
            + 0.25 * npvs[index]
            + 0.15 * goals[index]
            + 0.15 * stress[index]
            + 0.10 * liquidity[index]
            - 0.10 * drawdowns[index]
        )
        result["score"] = round(max(0.0, min(1.0, score)), 4)

    results.sort(key=lambda result: float(result["score"]), reverse=True)
    for rank, result in enumerate(results, start=1):
        result["rank"] = rank


def _why_recommended(result: Dict[str, object], macro: MacroSnapshot) -> str:
    scenario: Scenario = result["scenario"]  # type: ignore[assignment]
    mc: MonteCarloSummary = result["mc"]  # type: ignore[assignment]
    expected = float(result["expected_return"])
    real = (1.0 + expected) / (1.0 + macro.inflation_expected.value) - 1.0
    years = float(result.get("years") or 0.0)
    years_text = f"{years:.1f}".rstrip("0").rstrip(".") if years else "—"
    return (
        f"Сценарий «{scenario.name}» даёт ожидаемую доходность {expected:.1%} "
        f"и реальную {real:.1%} после инфляции. Медианный капитал через "
        f"{years_text} лет — {mc.terminal_p50:,.0f} ₽, "
        f"диапазон P5–P95: {mc.terminal_p5:,.0f}–{mc.terminal_p95:,.0f} ₽. "
        f"Риск: волатильность {float(result['volatility']):.1%}, "
        f"максимальная просадка (медиана) {float(result['max_drawdown']):.1%}. "
        f"Ключевая ставка {macro.key_rate.value:.1%}, инфляция "
        f"{macro.inflation_expected.value:.1%} — поэтому вклад и короткие ОФЗ "
        f"дают базовую защиту, а длинные облигации и недвижимость — премию за риск."
    )


def _build_scenario_result(result: Dict[str, object], macro: MacroSnapshot) -> ScenarioResult:
    scenario: Scenario = result["scenario"]  # type: ignore[assignment]
    mc: MonteCarloSummary = result["mc"]  # type: ignore[assignment]
    expected = float(result["expected_return"])
    real = (1.0 + expected) / (1.0 + macro.inflation_expected.value) - 1.0
    allocation = [AllocationItem(**item) for item in result["allocation"]]
    return ScenarioResult(
        id=scenario.id,
        name=scenario.name,
        risk_level=scenario.risk_level,
        description=scenario.description,
        allocation=allocation,
        expected_return_nominal=round(expected, 4),
        expected_return_real=round(real, 4),
        after_tax_return=round(float(result["after_tax_return"]), 4),
        volatility=round(float(result["volatility"]), 4),
        sharpe=round(float(result["sharpe"]), 4),
        sortino=round(float(result["sortino"]), 4),
        var_95=round(float(result["var_95"]), 4),
        cvar_95=round(float(result["cvar_95"]), 4),
        max_drawdown=round(float(result["max_drawdown"]), 4),
        probability_goal=mc.probability_goal,
        probability_loss=mc.probability_loss,
        liquidity=round(float(result["liquidity"]), 4),
        liquidity_label=liquidity_label(float(result["liquidity"])),
        duration_years=round(float(result["duration"]), 2),
        taxes=result["taxes"],  # type: ignore[arg-type]
        fees=result["fees"],  # type: ignore[arg-type]
        monte_carlo=mc,
        stress_tests=result["stress"],  # type: ignore[arg-type]
        npv=round(float(result["npv"]), 2),
        irr=round(float(result["irr"]), 4) if result["irr"] is not None else None,
        score=float(result.get("score", 0.0)),
        rank=int(result.get("rank", 0)),
        why_recommended=_why_recommended(result, macro),
        tags=scenario.tags,
    )


def _build_risk_profiles(
    results: List[Dict[str, object]],
    macro: MacroSnapshot,
) -> Dict[str, RiskProfileResult]:
    profiles: Dict[str, RiskProfileResult] = {}
    for level in (RiskLevel.low, RiskLevel.medium, RiskLevel.high):
        group = [result for result in results if result["scenario"].risk_level == level]
        _score_group(group)
        options = [_build_scenario_result(result, macro) for result in group[:5]]
        if not options:
            continue
        best = options[0]
        summary = {
            "expected_return": best.expected_return_nominal,
            "expected_return_real": best.expected_return_real,
            "p5": best.monte_carlo.terminal_p5,
            "p50": best.monte_carlo.terminal_p50,
            "p95": best.monte_carlo.terminal_p95,
            "probability_goal": best.probability_goal or 0.0,
            "probability_loss": best.probability_loss,
            "max_drawdown": best.max_drawdown,
            "var_95": best.var_95,
            "cvar_95": best.cvar_95,
            "liquidity": best.liquidity,
        }
        profiles[level.value] = RiskProfileResult(
            level=level,
            label=RISK_LABELS[level],
            description=RISK_DESCRIPTIONS[level],
            best_option_id=best.id,
            options=options,
            summary=summary,
        )
    return profiles


def _build_comparisons(
    profile: UserProfile,
    macro: MacroSnapshot,
    assets: Dict[str, Asset],
    best_return: float,
) -> ComparisonResult:
    rent_vs_buy = None
    prepay_vs_invest = None

    if profile.capital > 0 and profile.horizon_months >= 12:
        property_value = max(assets["real_estate"].min_investment, profile.capital / 0.3)
        down_payment = min(profile.capital, property_value * 0.3)
        mortgage = max(0.0, property_value - down_payment)
        rate = macro.mortgage_rate.value
        term = 240
        payment = annuity_payment(mortgage, rate, term)
        rent = property_value * macro.rent_yield.value / 12.0
        years = profile.horizon_months / 12.0
        buy_terminal = (
            property_value * (1.0 + macro.real_estate_growth.value) ** years
            - loan_remaining_balance(mortgage, rate, term, profile.horizon_months)
            + property_deduction(property_value, loan_total_interest(mortgage, rate, term))
        )
        # Сравниваем одинаковый денежный поток: первый взнос и платёж по
        # ипотеке. Арендатор платит аренду, а разницу (платёж − аренда)
        # инвестирует. Поэтому в NPV у обоих вариантов одинаковый отток.
        monthly_diff = payment - rent
        rent_terminal = down_payment
        for _ in range(profile.horizon_months):
            rent_terminal *= 1.0 + _annual_to_monthly(best_return)
            rent_terminal += monthly_diff
        npv_buy = cashflow_npv(
            macro.key_rate.value, down_payment, payment,
            profile.horizon_months, buy_terminal,
        )
        npv_rent = cashflow_npv(
            macro.key_rate.value, down_payment, payment,
            profile.horizon_months, rent_terminal,
        )
        rent_vs_buy = ComparisonItem(
            name="Аренда vs покупка",
            better_option="Покупка" if buy_terminal > rent_terminal else "Аренда",
            npv_difference=round(npv_buy - npv_rent, 2),
            irr_difference=None,
            details={
                "property_value": round(property_value, 2),
                "down_payment": round(down_payment, 2),
                "mortgage": round(mortgage, 2),
                "monthly_payment": round(payment, 2),
                "monthly_rent": round(rent, 2),
                "buy_terminal": round(buy_terminal, 2),
                "rent_terminal": round(rent_terminal, 2),
            },
            note="Упрощённая модель: покупка с ипотекой и вычетами против аренды и инвестирования разницы.",
        )

    debt = profile.existing_mortgage
    if debt and debt.balance > 0 and debt.annual_rate > 0:
        years = profile.horizon_months / 12.0
        prepay_capital = min(profile.capital, debt.balance)
        saved_interest = prepay_capital * debt.annual_rate * years
        prepay_terminal = prepay_capital * (1.0 + debt.annual_rate) ** years
        invest_terminal = prepay_capital * (1.0 + best_return) ** years
        prepay_vs_invest = ComparisonItem(
            name="Досрочно погасить vs вложить",
            better_option="Погасить" if prepay_terminal > invest_terminal else "Вложить",
            npv_difference=round(prepay_terminal - invest_terminal, 2),
            irr_difference=round(debt.annual_rate - best_return, 4),
            details={
                "debt_rate": round(debt.annual_rate, 4),
                "portfolio_return": round(best_return, 4),
                "prepay_capital": round(prepay_capital, 2),
                "saved_interest": round(saved_interest, 2),
                "prepay_terminal": round(prepay_terminal, 2),
                "invest_terminal": round(invest_terminal, 2),
            },
            note="Сравнение гарантированной экономии на процентах с ожидаемой доходностью портфеля.",
        )
    return ComparisonResult(rent_vs_buy=rent_vs_buy, prepay_vs_invest=prepay_vs_invest)


def _warnings(
    profile: UserProfile,
    macro: MacroSnapshot,
    scenarios: List[Scenario],
) -> List[str]:
    warnings: List[str] = []
    if profile.capital <= 0 and profile.monthly <= 0:
        warnings.append("Нет свободных средств для инвестирования: добавьте капитал или ежемесячный взнос.")
    if profile.horizon_months < 12:
        warnings.append("Срок меньше года: длинные облигации и недвижимость могут быть неуместны.")
    if profile.liquidity_need == LiquidityNeed.high:
        warnings.append("Высокая потребность в ликвидности: доля вкладов и коротких ОФЗ повышена.")
    if profile.credit_willingness and profile.credit_type.value == "mortgage":
        warnings.append("Ипотечные сценарии используют плечо: просадка и платёж могут быть выше расчётных.")
    if not any("real_estate" in scenario.weights for scenario in scenarios):
        warnings.append("Недвижимость не включена: капитала меньше минимального порога входа или она отключена.")
    if macro.inflation_expected.value >= 0.08:
        warnings.append("Ожидаемая инфляция выше 8%: реальная доходность может быть ниже номинальной.")
    if not profile.iis or profile.iis.type == "none":
        warnings.append("ИИС не используется: налоговый вычет мог бы улучшить результат.")
    return warnings


def run_optimization(
    request: OptimizeRequest,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> OptimizeResponse:
    profile = request.profile
    options = request.options
    macro = get_macro_snapshot(
        refresh=request.refresh_macro,
        overrides=request.market_overrides,
    )
    assets = build_assets(macro)
    scenarios = scenario_templates(
        profile, macro, assets, max_scenarios=options.max_scenarios
    )
    if not options.include_real_estate:
        scenarios = [
            scenario for scenario in scenarios
            if "real_estate" not in scenario.weights
        ]
    if not options.include_mortgage:
        scenarios = [
            scenario for scenario in scenarios
            if scenario.leverage <= 0
        ]
    if not scenarios:
        raise ValueError("Не удалось построить ни одного сценария под заданные параметры.")

    results: List[Dict[str, object]] = []
    total = len(scenarios)
    for index, scenario in enumerate(scenarios):
        if progress_callback:
            progress_callback(
                int(5 + 85 * index / max(1, total)),
                f"Считаем сценарий {index + 1} из {total}: {scenario.name}",
            )
        if scenario.leverage > 0:
            result = _simulate_leveraged(
                scenario, profile, macro, assets, options
            )
        else:
            result = _simulate_standard(
                scenario, profile, macro, assets, options
            )
        results.append(result)

    if progress_callback:
        progress_callback(92, "Ранжируем сценарии и считаем метрики")

    risk_profiles = _build_risk_profiles(results, macro)
    all_options = [option for profile_result in risk_profiles.values() for option in profile_result.options]
    all_options.sort(key=lambda option: option.score, reverse=True)
    top_options = all_options[:10]
    for index, option in enumerate(top_options, start=1):
        option.rank = index
    best_return = (
        top_options[0].expected_return_nominal if top_options else macro.deposit_rate.value
    )
    comparisons = _build_comparisons(profile, macro, assets, best_return)
    warnings = _warnings(profile, macro, scenarios)

    data: Dict[str, object] = {
        "request_id": uuid.uuid4().hex,
        "generated_at": _now_iso(),
        "profile": profile,
        "macro": macro,
        "risk_profiles": risk_profiles,
        "top_options": top_options,
        "comparisons": comparisons,
        "warnings": warnings,
        "disclaimer": DISCLAIMER,
    }
    context = ai.build_context(data)
    context_id = ai.store_context(context)
    template = ai.template_explanation(context)
    data["context_id"] = context_id
    data["ai_template"] = template
    if progress_callback:
        progress_callback(100, "Готово")
    return OptimizeResponse(**data)
