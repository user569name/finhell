"""Планирование, облигации и Монте-Карло для экономического симулятора."""

from __future__ import annotations

from dataclasses import replace
from math import ceil, log, sqrt
from random import Random
from typing import Dict, List, Optional, Sequence, Tuple

try:
    from .simulator_engine import (
        DEFAULT_RISK_FACTORS,
        INSTRUMENTS,
        RISK_FACTOR_LABELS,
        RISK_PROFILES,
        Debt,
        SimulationParams,
        build_allocation,
        clamp,
        effective_risk,
        effective_volatility,
        expected_return,
        risk_label,
    )
except ImportError:  # запуск как обычного скрипта
    from simulator_engine import (
        DEFAULT_RISK_FACTORS,
        INSTRUMENTS,
        RISK_FACTOR_LABELS,
        RISK_PROFILES,
        Debt,
        SimulationParams,
        build_allocation,
        clamp,
        effective_risk,
        effective_volatility,
        expected_return,
        risk_label,
    )


# ---------------------------------------------------------------------------
# Долги
# ---------------------------------------------------------------------------

def _debt_stats(debt: Debt) -> Dict[str, object]:
    rate = debt.annual_rate / 12.0
    payment = debt.monthly_payment
    if payment <= 0:
        return {
            "remaining_months": None,
            "remaining_interest": None,
            "warning": "Не указан ежемесячный платёж — срок и переплату оценить нельзя.",
        }
    if rate <= 0:
        months = max(1, ceil(debt.balance / payment))
        interest = max(0.0, payment * months - debt.balance)
        return {
            "remaining_months": months,
            "remaining_interest": interest,
            "warning": None,
        }
    if payment <= debt.balance * rate:
        return {
            "remaining_months": None,
            "remaining_interest": None,
            "warning": "Платёж не покрывает начисленные проценты.",
        }
    months = max(1, ceil(-log(1.0 - debt.balance * rate / payment) / log(1.0 + rate)))
    interest = max(0.0, payment * months - debt.balance)
    return {
        "remaining_months": months,
        "remaining_interest": interest,
        "warning": None,
    }


def build_debt_advice(
    params: SimulationParams,
    high_debts: Sequence[Debt],
    payoff: float,
    threshold: float,
) -> Dict[str, object]:
    payoff_by_index: Dict[int, float] = {}
    left = max(0.0, payoff)
    high_indices = {id(debt) for debt in high_debts}
    for index, debt in sorted(
        enumerate(params.debts),
        key=lambda pair: pair[1].annual_rate,
        reverse=True,
    ):
        if id(debt) not in high_indices:
            continue
        portion = min(debt.balance, left)
        if portion > 0:
            payoff_by_index[index] = portion
            left -= portion

    items: List[Dict[str, object]] = []
    total_balance = 0.0
    saved_interest = 0.0
    freed_payment = 0.0

    for index, debt in enumerate(params.debts):
        stats = _debt_stats(debt)
        total_balance += debt.balance
        portion = payoff_by_index.get(index, 0.0)
        interest = stats["remaining_interest"]
        saved = 0.0
        if interest is not None and debt.balance > 0 and portion > 0:
            saved = float(interest) * portion / debt.balance
        saved_interest += saved
        if portion >= debt.balance - 1e-9:
            freed_payment += debt.monthly_payment
        elif debt.balance > 0:
            freed_payment += debt.monthly_payment * portion / debt.balance

        items.append(
            {
                "name": debt.name,
                "balance": round(debt.balance, 2),
                "annual_rate": round(debt.annual_rate, 4),
                "monthly_payment": round(debt.monthly_payment, 2),
                "remaining_months": stats["remaining_months"],
                "remaining_interest": (
                    round(float(interest), 2) if interest is not None else None
                ),
                "high_rate": debt.annual_rate >= threshold,
                "payoff_from_capital": round(portion, 2),
                "saved_interest": round(saved, 2),
                "warning": stats["warning"],
            }
        )

    if not params.debts:
        recommendation = "Долгов нет — можно сразу переходить к резерву и инвестициям."
    elif payoff > 0:
        recommendation = (
            "Сначала гасим долги со ставкой выше безрисковой доходности. "
            "Это гарантированная «доходность» без рыночного риска."
        )
    else:
        recommendation = (
            "Дорогих долгов нет. Плановые платежи не мешают инвестировать, "
            "но досрочно гасить такие долги невыгодно."
        )

    return {
        "has_debts": bool(params.debts),
        "threshold": round(threshold, 4),
        "total_balance": round(total_balance, 2),
        "payoff": round(payoff, 2),
        "saved_interest": round(saved_interest, 2),
        "freed_monthly_payment": round(freed_payment, 2),
        "items": items,
        "recommendation": recommendation,
    }


def build_reserve_plan(
    params: SimulationParams,
    target: float,
    initial: float,
    gap: float,
    months_to_fill: int,
    investable_initial: float,
    payoff: float,
    has_high_debts: bool,
) -> Dict[str, object]:
    monthly_to_reserve = 0.0
    if months_to_fill > 0 and gap > 0:
        monthly_to_reserve = min(params.monthly_contribution, gap)

    if target <= 0:
        note = "Резерв не задан: месячные расходы равны нулю."
    elif gap <= 0:
        note = "Резерв уже полностью покрыт стартовым капиталом."
    elif months_to_fill >= params.horizon_months:
        note = "Резерв не успеет сформироваться до конца срока."
    elif has_high_debts and payoff > 0:
        note = (
            "Сначала откладываем один месяц расходов, затем гасим дорогой долг, "
            "после чего добираем резерв до полного."
        )
    else:
        note = "Резерв пополняется из ежемесячных взносов до целевой суммы."

    return {
        "target": round(target, 2),
        "initial": round(initial, 2),
        "gap": round(max(0.0, gap), 2),
        "months_to_fill": int(months_to_fill),
        "monthly_to_reserve": round(monthly_to_reserve, 2),
        "investable_initial": round(investable_initial, 2),
        "note": note,
    }


# ---------------------------------------------------------------------------
# Облигации
# ---------------------------------------------------------------------------

def analyze_bond(
    face_value: float,
    price: float,
    coupon_rate: float,
    coupons_per_year: int,
    years_to_maturity: float,
    reinvest_rate: Optional[float] = None,
) -> Dict[str, object]:
    if face_value <= 0 or price <= 0:
        raise ValueError("Номинал и цена облигации должны быть больше нуля.")
    if coupon_rate < 0:
        raise ValueError("Купонная ставка не может быть отрицательной.")
    if coupons_per_year < 1 or coupons_per_year > 12:
        raise ValueError("Число купонов в год должно быть от 1 до 12.")
    if years_to_maturity <= 0:
        raise ValueError("Срок до погашения должен быть больше нуля.")

    frequency = int(coupons_per_year)
    periods = max(1, int(round(years_to_maturity * frequency)))
    coupon = face_value * coupon_rate / frequency
    flows: List[Tuple[int, float]] = []
    for period in range(1, periods + 1):
        amount = coupon + (face_value if period == periods else 0.0)
        flows.append((period, amount))

    def price_at(annual_yield: float) -> float:
        base = 1.0 + annual_yield / frequency
        if base <= 0:
            return float("inf")
        return sum(amount / (base ** period) for period, amount in flows)

    low, high = -0.95, 5.0
    for _ in range(200):
        middle = (low + high) / 2.0
        if price_at(middle) > price:
            low = middle
        else:
            high = middle
    ytm = (low + high) / 2.0

    annual_coupon = coupon * frequency
    current_yield = annual_coupon / price
    discounted = [
        (period / frequency, amount / ((1.0 + ytm / frequency) ** period))
        for period, amount in flows
    ]
    macaulay = sum(time * value for time, value in discounted) / price
    modified = macaulay / (1.0 + ytm / frequency)

    total_coupons = coupon * periods
    total_payments = total_coupons + face_value
    profit = total_payments - price

    reinvest = coupon_rate if reinvest_rate is None else reinvest_rate
    future_value = face_value
    for period, amount in flows:
        coupon_part = amount - (face_value if period == periods else 0.0)
        future_value += coupon_part * ((1.0 + reinvest / frequency) ** (periods - period))
    profit_reinvested = future_value - price

    return {
        "face_value": round(face_value, 2),
        "price": round(price, 2),
        "coupon_rate": round(coupon_rate, 4),
        "coupons_per_year": frequency,
        "years_to_maturity": round(years_to_maturity, 2),
        "periods": periods,
        "annual_coupon_income": round(annual_coupon, 2),
        "current_yield": round(current_yield, 4),
        "ytm": round(ytm, 4),
        "macaulay_duration_years": round(macaulay, 4),
        "modified_duration": round(modified, 4),
        "total_coupons": round(total_coupons, 2),
        "total_payments": round(total_payments, 2),
        "profit": round(profit, 2),
        "reinvest_rate": round(reinvest, 4),
        "future_value_reinvested": round(future_value, 2),
        "profit_reinvested": round(profit_reinvested, 2),
        "note": (
            "YTM — доходность к погашению при удержании бумаги до конца срока "
            "и реинвестировании купонов по указанной ставке."
        ),
    }


def build_bond_ladder(
    params: SimulationParams,
    allocation: Dict[str, object],
    investable_initial: float,
    reserve_months: int,
    growth_end: int,
) -> List[Dict[str, object]]:
    items = allocation.get("items", [])
    bond_items = [
        item for item in items
        if item["key"] in ("ofz", "corporate_bonds") and item["share"] > 0
    ]
    if not bond_items:
        return []

    horizon = params.horizon_months
    rungs = min(4, max(1, horizon // 12))
    growth_months = max(0, growth_end - max(0, reserve_months))
    planned = investable_initial + params.monthly_contribution * growth_months

    ladder: List[Dict[str, object]] = []
    for item in bond_items:
        instrument_money = planned * item["share"]
        per_rung = instrument_money / rungs
        for rung in range(rungs):
            maturity = max(1, round(horizon * (rung + 1) / rungs))
            ladder.append(
                {
                    "instrument": item["key"],
                    "name": item["short_name"],
                    "maturity_months": maturity,
                    "share_of_portfolio": round(item["share"] / rungs, 4),
                    "approx_amount": round(per_rung, 2),
                    "expected_yield": item["expected_return"],
                    "note": (
                        f"Погашение примерно к месяцу {maturity}. "
                        "Покупайте выпуск с подходящим сроком."
                    ),
                }
            )
    return sorted(ladder, key=lambda row: (row["instrument"], row["maturity_months"]))


# ---------------------------------------------------------------------------
# Последовательность действий
# ---------------------------------------------------------------------------

def _period_label(start: int, end: int) -> str:
    if start == end:
        return f"Месяц {start}"
    return f"Месяцы {start}–{end}"


def _fmt_money(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ")


def _allocation_entries(
    allocation: Dict[str, object],
    amount_key: str,
    monthly: bool = False,
) -> List[Dict[str, object]]:
    entries: List[Dict[str, object]] = []
    items = sorted(allocation.get("items", []), key=lambda item: item["risk"])
    for order, item in enumerate(items, start=1):
        amount = float(item.get(amount_key, 0.0))
        if amount <= 0:
            continue
        note = ""
        if item["key"] in ("ofz", "corporate_bonds"):
            note = "Покупать лестницей и держать до погашения."
        elif item["key"] == "stocks":
            note = "Покупать равными долями каждый месяц."
        elif item["key"] == "gold":
            note = "Небольшая доля как страховка от инфляции."
        elif item["key"] == "real_estate":
            note = "Покупка после накопления минимальной суммы."
        elif item["key"] == "crypto":
            note = "Только небольшая спекулятивная доля."
        elif item["key"] == "deposit":
            note = "Ликвидная часть и резерв."
        entries.append(
            {
                "order": order,
                "key": item["key"],
                "name": item["name"],
                "share": item["share"],
                "amount": round(amount, 2),
                "monthly_amount": round(amount, 2) if monthly else 0.0,
                "risk": item["risk"],
                "expected_return": item["expected_return"],
                "note": note,
            }
        )
    return entries


def build_sequence(
    params: SimulationParams,
    allocation: Dict[str, object],
    reserve_plan: Dict[str, object],
    debt_advice: Dict[str, object],
    bond_ladder: Sequence[Dict[str, object]],
    mc: Dict[str, object],
    derisk_months: int,
    growth_end: int,
) -> List[Dict[str, object]]:
    stages: List[Dict[str, object]] = []
    step = 1
    horizon = params.horizon_months
    monthly = params.monthly_contribution
    reserve_target = float(reserve_plan["target"])
    reserve_months = int(reserve_plan["months_to_fill"])
    payoff = float(debt_advice["payoff"])
    investable_initial = float(reserve_plan["investable_initial"])

    def deposit_entry(
        amount: float,
        monthly_amount: float,
        note: str,
    ) -> Dict[str, object]:
        return {
            "order": 1,
            "key": "deposit",
            "name": INSTRUMENTS["deposit"].name,
            "share": 1.0,
            "amount": round(amount, 2),
            "monthly_amount": round(monthly_amount, 2),
            "risk": round(effective_risk(INSTRUMENTS["deposit"], params.risk_factors), 4),
            "expected_return": round(expected_return(INSTRUMENTS["deposit"], params), 4),
            "note": note,
        }

    reserve_initial = float(reserve_plan["initial"])
    reserve_gap = max(0.0, reserve_target - reserve_initial)
    starter_reserve = min(reserve_target, reserve_initial)
    split_reserve = payoff > 0 and reserve_months > 0 and starter_reserve > 0

    if reserve_target > 0:
        if split_reserve:
            stages.append(
                {
                    "step": step,
                    "period": "Сразу",
                    "title": "Стартовый резерв",
                    "description": (
                        f"Отложите {_fmt_money(starter_reserve)} ₽ из стартового "
                        "капитала — это минимум на время погашения долга. "
                        + str(reserve_plan["note"])
                    ),
                    "reason": (
                        "Один месяц расходов защищает от кассового разрыва, "
                        "пока долг ещё не погашен."
                    ),
                    "amount": round(starter_reserve, 2),
                    "monthly_amount": 0.0,
                    "instruments": [
                        deposit_entry(
                            starter_reserve,
                            0.0,
                            "Деньги должны быть доступны в любой момент.",
                        )
                    ],
                }
            )
            step += 1
        else:
            if reserve_months > 0:
                period = _period_label(1, reserve_months)
            else:
                period = "Сразу"
            stages.append(
                {
                    "step": step,
                    "period": period,
                    "title": "Резерв безопасности",
                    "description": (
                        f"Соберите {_fmt_money(reserve_target)} ₽ — это "
                        f"{params.emergency_fund_months} мес. расходов. "
                        + str(reserve_plan["note"])
                    ),
                    "reason": (
                        "Резерв позволяет не продавать инвестиции в кризис "
                        "и не брать новые долги."
                    ),
                    "amount": round(reserve_target, 2),
                    "monthly_amount": round(float(reserve_plan["monthly_to_reserve"]), 2),
                    "instruments": [
                        deposit_entry(
                            reserve_target,
                            float(reserve_plan["monthly_to_reserve"]),
                            "Деньги должны быть доступны в любой момент.",
                        )
                    ],
                }
            )
            step += 1

    if payoff > 0:
        stages.append(
            {
                "step": step,
                "period": "Месяц 1",
                "title": "Погашение дорогих долгов",
                "description": (
                    f"Направьте {_fmt_money(payoff)} ₽ на досрочное погашение. "
                    f"Экономия на процентах — около "
                    f"{_fmt_money(float(debt_advice['saved_interest']))} ₽."
                ),
                "reason": (
                    "Ставка по долгу выше безрисковой доходности. "
                    "Погашение — гарантированный возврат без риска."
                ),
                "amount": round(payoff, 2),
                "monthly_amount": 0.0,
                "instruments": [
                    {
                        "order": 1,
                        "key": "debt_payoff",
                        "name": "Досрочное погашение долга",
                        "share": 0.0,
                        "amount": round(payoff, 2),
                        "monthly_amount": 0.0,
                        "risk": 0.0,
                        "expected_return": round(float(debt_advice["threshold"]), 4),
                        "note": "Сначала самые дорогие долги.",
                    }
                ],
            }
        )
        step += 1

    if split_reserve and reserve_gap > 0:
        stages.append(
            {
                "step": step,
                "period": _period_label(1, reserve_months),
                "title": "Пополнение резерва",
                "description": (
                    f"Доберите резерв до {_fmt_money(reserve_target)} ₽: "
                    f"не хватает {_fmt_money(reserve_gap)} ₽. "
                    "Последний взнос может быть меньше."
                ),
                "reason": (
                    "После погашения дорогого долга освободившиеся деньги "
                    "сначала закрывают подушку безопасности."
                ),
                "amount": round(reserve_gap, 2),
                "monthly_amount": round(float(reserve_plan["monthly_to_reserve"]), 2),
                "instruments": [
                    deposit_entry(
                        reserve_gap,
                        float(reserve_plan["monthly_to_reserve"]),
                        "Пополняйте резерв из ежемесячных взносов.",
                    )
                ],
            }
        )
        step += 1

    if investable_initial > 0:
        stages.append(
            {
                "step": step,
                "period": "Месяц 1",
                "title": "Размещение стартового капитала",
                "description": (
                    "Распределите свободный капитал по целевой структуре. "
                    "Сначала облигации, затем акции, золото и другие активы."
                ),
                "reason": (
                    "Стартовый капитал сразу работает, а не лежит без дела."
                ),
                "amount": round(investable_initial, 2),
                "monthly_amount": 0.0,
                "instruments": _allocation_entries(allocation, "initial_amount"),
            }
        )
        step += 1

    regular_start = reserve_months + 1
    if monthly > 0 and growth_end >= regular_start:
        months = growth_end - reserve_months
        description = (
            "Ежемесячно докупайте активы по целевым долям. "
            "Облигации — лестницей, акции — равными частями."
        )
        if bond_ladder:
            description += (
                " Лестница облигаций: "
                + ", ".join(
                    f"{row['name']} ~{row['maturity_months']} мес"
                    for row in bond_ladder[:4]
                )
                + "."
            )
        stages.append(
            {
                "step": step,
                "period": _period_label(regular_start, growth_end),
                "title": "Регулярные инвестиции",
                "description": description,
                "reason": (
                    "Усреднение стоимости снижает риск неудачного момента входа."
                ),
                "amount": round(monthly * months, 2),
                "monthly_amount": round(monthly, 2),
                "instruments": _allocation_entries(allocation, "monthly_amount", monthly=True),
            }
        )
        step += 1

    if derisk_months > 0 and growth_end < horizon:
        start = growth_end + 1
        stages.append(
            {
                "step": step,
                "period": _period_label(start, horizon),
                "title": "Защита капитала перед целью",
                "description": (
                    "Постепенно переводите накопленное в вклад и короткие "
                    "инструменты денежного рынка. Новые взносы — только туда."
                ),
                "reason": (
                    "За несколько месяцев до цели риск падения рынка "
                    "перевешивает потенциал роста."
                ),
                "amount": round(monthly * derisk_months, 2),
                "monthly_amount": round(monthly, 2),
                "instruments": [
                    {
                        "order": 1,
                        "key": "deposit",
                        "name": INSTRUMENTS["deposit"].name,
                        "share": 1.0,
                        "amount": round(monthly * derisk_months, 2),
                        "monthly_amount": round(monthly, 2),
                        "risk": round(effective_risk(INSTRUMENTS["deposit"], params.risk_factors), 4),
                        "expected_return": round(expected_return(INSTRUMENTS["deposit"], params), 4),
                        "note": "Зафиксировать результат и защитить капитал.",
                    }
                ],
            }
        )
        step += 1

    goal_text = ""
    if params.goal_amount:
        probability = mc.get("probability_goal")
        if probability is not None:
            goal_text = f" Вероятность достичь цели — {probability * 100:.0f}%."
    stages.append(
        {
            "step": step,
            "period": f"Месяц {horizon}",
            "title": "Результат",
            "description": (
                f"Ожидаемый капитал (медиана): "
                f"{_fmt_money(float(mc['terminal_p50']))} ₽. "
                f"С учётом инфляции: {_fmt_money(float(mc['real_p50']))} ₽."
                + goal_text
            ),
            "reason": (
                "Медиана — не гарантия. Смотрите также пессимистичный "
                "сценарий p10 и вероятность убытка."
            ),
            "amount": round(float(mc["terminal_p50"]), 2),
            "monthly_amount": 0.0,
            "instruments": [],
        }
    )
    return stages


# ---------------------------------------------------------------------------
# Монте-Карло
# ---------------------------------------------------------------------------

def _percentile(sorted_values: Sequence[float], quantile: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    position = (len(sorted_values) - 1) * clamp(quantile)
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower
    return float(
        sorted_values[lower] * (1.0 - fraction)
        + sorted_values[upper] * fraction
    )


def _monthly_irr(
    initial_outflow: float,
    monthly: float,
    final_value: float,
    horizon: int,
) -> Optional[float]:
    if final_value <= 0:
        return None
    if initial_outflow <= 0 and monthly <= 0:
        return None

    def npv(rate: float) -> float:
        value = -initial_outflow
        for month in range(horizon):
            value -= monthly / ((1.0 + rate) ** month)
        value += final_value / ((1.0 + rate) ** horizon)
        return value

    previous_rate = -0.90
    previous_value = npv(previous_rate)
    bracket: Optional[Tuple[float, float]] = None
    for step in range(1, 381):
        rate = -0.90 + step * 0.005
        value = npv(rate)
        if previous_value == 0:
            return previous_rate
        if previous_value * value < 0:
            bracket = (previous_rate, rate)
            break
        previous_rate, previous_value = rate, value

    if bracket is None:
        return None

    low, high = bracket
    for _ in range(120):
        middle = (low + high) / 2.0
        if npv(middle) > 0:
            low = middle
        else:
            high = middle
    return (low + high) / 2.0


def run_monte_carlo(
    params: SimulationParams,
    allocation: Dict[str, object],
    reserve_plan: Dict[str, object],
    debt_payoff: float,
    derisk_months: int,
    paths: Optional[int] = None,
    seed: Optional[int] = None,
    collect_series: bool = True,
) -> Dict[str, object]:
    n_paths = max(50, int(paths or params.monte_carlo_paths))
    rng_seed = params.seed if seed is None else seed
    horizon = params.horizon_months
    monthly = params.monthly_contribution
    reserve_target = float(reserve_plan["target"])
    reserve_initial = float(reserve_plan["initial"])
    invested_initial = float(reserve_plan["investable_initial"])
    deployed_initial = max(0.0, params.initial_capital - debt_payoff)

    weights = {
        item["key"]: float(item["share"])
        for item in allocation.get("items", [])
    }
    if not weights:
        weights = {"deposit": 1.0}
    total_weight = sum(weights.values())
    weights = {key: value / total_weight for key, value in weights.items()}

    asset_mu: Dict[str, float] = {}
    asset_sigma: Dict[str, float] = {}
    asset_beta: Dict[str, float] = {}
    for key, instrument in INSTRUMENTS.items():
        ret = max(-0.95, expected_return(instrument, params))
        vol = effective_volatility(
            instrument,
            params.risk_factors,
            params.asset_risk_overrides.get(key),
        )
        asset_mu[key] = (1.0 + ret) ** (1.0 / 12.0) - 1.0
        asset_sigma[key] = vol / sqrt(12.0)
        asset_beta[key] = sqrt(clamp(instrument.factor_loadings.get("market", 0.0)))

    deposit_m = asset_mu["deposit"]
    de_risk_weights = {"deposit": 1.0}
    total_contributions = deployed_initial + monthly * horizon

    values_by_month: Optional[List[List[float]]] = (
        [[] for _ in range(horizon + 1)] if collect_series else None
    )
    terminal_values: List[float] = []
    drawdowns: List[float] = []
    goal_hits = 0
    loss_hits = 0

    for path in range(n_paths):
        rng = Random(rng_seed + path * 100_003)
        reserve = reserve_initial
        portfolio = invested_initial
        peak = reserve + portfolio
        max_drawdown = 0.0
        if values_by_month is not None:
            values_by_month[0].append(peak)

        for month in range(horizon):
            if reserve < reserve_target - 1e-9:
                reserve_add = min(monthly, reserve_target - reserve)
                portfolio_add = monthly - reserve_add
                reserve += reserve_add
            else:
                portfolio_add = monthly

            reserve *= 1.0 + deposit_m
            portfolio += portfolio_add

            if derisk_months > 0 and month >= horizon - derisk_months:
                current_weights = de_risk_weights
            else:
                current_weights = weights

            market_shock = rng.gauss(0.0, 1.0)
            portfolio_return = 0.0
            for key, weight in current_weights.items():
                beta = asset_beta.get(key, 0.0)
                idiosyncratic = rng.gauss(0.0, 1.0)
                shock = beta * market_shock + sqrt(max(0.0, 1.0 - beta * beta)) * idiosyncratic
                asset_return = asset_mu.get(key, 0.0) + asset_sigma.get(key, 0.0) * shock
                asset_return = max(-0.95, asset_return)
                portfolio_return += weight * asset_return

            portfolio *= 1.0 + portfolio_return
            total = reserve + portfolio
            if total > peak:
                peak = total
            if peak > 0:
                drawdown = (peak - total) / peak
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
            if values_by_month is not None:
                values_by_month[month + 1].append(total)

        terminal = reserve + portfolio
        terminal_values.append(terminal)
        drawdowns.append(max_drawdown)
        if params.goal_amount and terminal >= params.goal_amount:
            goal_hits += 1
        if terminal < total_contributions:
            loss_hits += 1

    terminal_sorted = sorted(terminal_values)
    drawdown_sorted = sorted(drawdowns)
    terminal_p10 = _percentile(terminal_sorted, 0.10)
    terminal_p50 = _percentile(terminal_sorted, 0.50)
    terminal_p90 = _percentile(terminal_sorted, 0.90)
    terminal_p5 = _percentile(terminal_sorted, 0.05)
    mean_terminal = sum(terminal_values) / len(terminal_values)
    inflation_factor = (1.0 + params.inflation_rate) ** (horizon / 12.0)
    real_p50 = terminal_p50 / inflation_factor if inflation_factor > 0 else terminal_p50

    irr_monthly = _monthly_irr(deployed_initial, monthly, terminal_p50, horizon)
    irr_annual = (
        (1.0 + irr_monthly) ** 12.0 - 1.0
        if irr_monthly is not None and irr_monthly > -1.0
        else None
    )

    series: List[Dict[str, object]] = []
    yearly: List[Dict[str, object]] = []
    if values_by_month is not None:
        for month, values in enumerate(values_by_month):
            ordered = sorted(values)
            point = {
                "month": month,
                "p10": round(_percentile(ordered, 0.10), 2),
                "p50": round(_percentile(ordered, 0.50), 2),
                "p90": round(_percentile(ordered, 0.90), 2),
                "contributed": round(deployed_initial + monthly * month, 2),
            }
            series.append(point)

        year_marks = list(range(12, horizon + 1, 12))
        if horizon % 12 != 0 or not year_marks:
            year_marks.append(horizon)
        for month in sorted(set(year_marks)):
            point = dict(series[month])
            point["year"] = round(month / 12.0, 2)
            yearly.append(point)

    return {
        "paths": n_paths,
        "terminal_p5": round(terminal_p5, 2),
        "terminal_p10": round(terminal_p10, 2),
        "terminal_p50": round(terminal_p50, 2),
        "terminal_p90": round(terminal_p90, 2),
        "mean_terminal": round(mean_terminal, 2),
        "real_p50": round(real_p50, 2),
        "total_contributions": round(total_contributions, 2),
        "profit_p50": round(terminal_p50 - total_contributions, 2),
        "return_pct": round(
            (terminal_p50 - total_contributions) / total_contributions, 4
        ) if total_contributions > 0 else 0.0,
        "irr_annual": round(irr_annual, 4) if irr_annual is not None else None,
        "probability_goal": (
            round(goal_hits / n_paths, 4) if params.goal_amount else None
        ),
        "probability_loss": round(loss_hits / n_paths, 4),
        "max_drawdown_median": round(_percentile(drawdown_sorted, 0.50), 4),
        "max_drawdown_p90": round(_percentile(drawdown_sorted, 0.90), 4),
        "var_95": round(max(0.0, total_contributions - terminal_p5), 2),
        "series": series,
        "yearly": yearly,
    }


# ---------------------------------------------------------------------------
# Сборка полного ответа
# ---------------------------------------------------------------------------

DISCLAIMER = (
    "Симулятор — учебно-аналитический инструмент, а не индивидуальная "
    "инвестиционная рекомендация. Доходности, волатильности и инфляция — "
    "это допущения модели; реальные результаты могут отличаться. "
    "Перед сделками проверяйте актуальные ставки, условия и риски."
)


def run_simulation(params: SimulationParams) -> Dict[str, object]:
    if params.risk_profile not in RISK_PROFILES:
        raise ValueError("Неизвестный риск-профиль.")
    if params.horizon_months < 1 or params.horizon_months > 600:
        raise ValueError("Срок должен быть от 1 до 600 месяцев.")
    if params.initial_capital < 0 or params.monthly_contribution < 0:
        raise ValueError("Суммы не могут быть отрицательными.")
    if params.inflation_rate <= -1.0:
        raise ValueError("Инфляция должна быть больше -100%.")

    warnings: List[str] = []
    profile = RISK_PROFILES[params.risk_profile]
    horizon = params.horizon_months
    monthly = params.monthly_contribution

    full_reserve_target = max(
        0.0,
        params.monthly_expenses * params.emergency_fund_months,
    )
    threshold = max(
        0.17,
        INSTRUMENTS["deposit"].annual_return + 0.02,
        params.inflation_rate + 0.03,
    )
    high_debts = [
        debt for debt in params.debts if debt.annual_rate >= threshold
    ]

    starter_target = (
        params.monthly_expenses * min(1, params.emergency_fund_months)
        if high_debts and params.monthly_expenses > 0
        else full_reserve_target
    )
    reserve_initial = min(params.initial_capital, starter_target)
    available = params.initial_capital - reserve_initial

    total_high_balance = sum(debt.balance for debt in high_debts)
    debt_payoff = min(available, total_high_balance) if high_debts else 0.0
    available -= debt_payoff

    reserve_top_up = min(
        available,
        max(0.0, full_reserve_target - reserve_initial),
    )
    reserve_initial += reserve_top_up
    available -= reserve_top_up
    investable_initial = max(0.0, available)

    reserve_gap = max(0.0, full_reserve_target - reserve_initial)
    if reserve_gap <= 0:
        reserve_months = 0
    elif monthly > 0:
        reserve_months = min(horizon, ceil(reserve_gap / monthly))
    else:
        reserve_months = horizon
        warnings.append(
            "Ежемесячных взносов нет: резерв не будет сформирован из взносов."
        )

    reserve_plan = build_reserve_plan(
        params=params,
        target=full_reserve_target,
        initial=reserve_initial,
        gap=reserve_gap,
        months_to_fill=reserve_months,
        investable_initial=investable_initial,
        payoff=debt_payoff,
        has_high_debts=bool(high_debts),
    )
    debt_advice = build_debt_advice(
        params=params,
        high_debts=high_debts,
        payoff=debt_payoff,
        threshold=threshold,
    )

    allocation = build_allocation(params, investable_initial)
    items = allocation["items"]

    if horizon < 12:
        derisk_months = 0
    else:
        derisk_months = min(12, max(3, horizon // 12))
    growth_end = max(reserve_months, horizon - derisk_months)
    if growth_end >= horizon:
        derisk_months = 0
        growth_end = horizon

    bond_ladder = build_bond_ladder(
        params=params,
        allocation=allocation,
        investable_initial=investable_initial,
        reserve_months=reserve_months,
        growth_end=growth_end,
    )

    mc = run_monte_carlo(
        params=params,
        allocation=allocation,
        reserve_plan=reserve_plan,
        debt_payoff=debt_payoff,
        derisk_months=derisk_months,
    )

    scenarios: List[Dict[str, object]] = []
    scenario_paths = max(150, min(400, params.monte_carlo_paths // 2))
    for scenario_key in ("conservative", "balanced", "aggressive"):
        scenario_params = replace(params, risk_profile=scenario_key)
        scenario_allocation = build_allocation(
            scenario_params,
            investable_initial,
        )
        scenario_mc = run_monte_carlo(
            params=scenario_params,
            allocation=scenario_allocation,
            reserve_plan=reserve_plan,
            debt_payoff=debt_payoff,
            derisk_months=derisk_months,
            paths=scenario_paths,
            seed=params.seed,
            collect_series=False,
        )
        scenarios.append(
            {
                "key": scenario_key,
                "label": RISK_PROFILES[scenario_key]["label"],
                "final_p10": scenario_mc["terminal_p10"],
                "final_p50": scenario_mc["terminal_p50"],
                "final_p90": scenario_mc["terminal_p90"],
                "expected_return": scenario_allocation["expected_return"],
                "risk": scenario_allocation["risk"],
                "risk_label": scenario_allocation["risk_label"],
                "is_recommended": scenario_key == params.risk_profile,
            }
        )

    sequence = build_sequence(
        params=params,
        allocation=allocation,
        reserve_plan=reserve_plan,
        debt_advice=debt_advice,
        bond_ladder=bond_ladder,
        mc=mc,
        derisk_months=derisk_months,
        growth_end=growth_end,
    )

    total_outlay = params.initial_capital + monthly * horizon
    net_effect = (
        float(mc["terminal_p50"])
        + debt_payoff
        + float(debt_advice["saved_interest"])
        - total_outlay
    )

    summary = {
        "risk_profile": params.risk_profile,
        "risk_profile_label": profile["label"],
        "horizon_months": horizon,
        "horizon_years": round(horizon / 12.0, 2),
        "initial_capital": round(params.initial_capital, 2),
        "monthly_contribution": round(monthly, 2),
        "total_contributions": mc["total_contributions"],
        "total_outlay": round(total_outlay, 2),
        "final_p10": mc["terminal_p10"],
        "final_p50": mc["terminal_p50"],
        "final_p90": mc["terminal_p90"],
        "final_real_p50": mc["real_p50"],
        "profit_p50": mc["profit_p50"],
        "return_pct": mc["return_pct"],
        "irr_annual": mc["irr_annual"],
        "portfolio_expected_return": allocation["expected_return"],
        "portfolio_real_return": allocation["real_expected_return"],
        "portfolio_risk": allocation["risk"],
        "portfolio_volatility": allocation["volatility"],
        "risk_label": allocation["risk_label"],
        "probability_goal": mc["probability_goal"],
        "goal_amount": (
            round(params.goal_amount, 2) if params.goal_amount else None
        ),
        "probability_loss": mc["probability_loss"],
        "max_drawdown_median": mc["max_drawdown_median"],
        "max_drawdown_p90": mc["max_drawdown_p90"],
        "var_95": mc["var_95"],
        "reserve_target": reserve_plan["target"],
        "reserve_initial": reserve_plan["initial"],
        "reserve_months": reserve_plan["months_to_fill"],
        "debt_payoff": round(debt_payoff, 2),
        "saved_interest": round(float(debt_advice["saved_interest"]), 2),
        "net_effect_p50": round(net_effect, 2),
        "investable_initial": round(investable_initial, 2),
    }

    if horizon < 12:
        warnings.append(
            "Срок меньше года: рискованные активы почти исключены, "
            "доходность в основном даёт вклад."
        )
    if monthly <= 0 and investable_initial <= 0:
        warnings.append(
            "Нет свободных денег для инвестирования: добавьте стартовый "
            "капитал или ежемесячный взнос."
        )
    if reserve_gap > 0 and reserve_months >= horizon:
        warnings.append(
            "Резерв не успеет сформироваться до конца срока — "
            "увеличьте взнос или срок."
        )
    if float(allocation["expected_return"]) <= params.inflation_rate:
        warnings.append(
            "Ожидаемая доходность портфеля ниже инфляции: "
            "покупательная способность может снижаться."
        )
    if debt_payoff > 0:
        warnings.append(
            "Досрочное погашение долга уменьшает стартовый портфель, "
            "но экономит проценты и снижает обязательства."
        )
    if any(item["key"] == "crypto" for item in items):
        warnings.append(
            "Криптовалюта — высокорисковый актив. Её доля ограничена "
            "профилем и сроком."
        )
    if (
        params.goal_amount
        and mc["probability_goal"] is not None
        and float(mc["probability_goal"]) < 0.5
    ):
        warnings.append(
            "Вероятность достичь цели ниже 50%. Увеличьте взнос, "
            "срок или допустимый риск."
        )
    if float(mc["probability_loss"]) > 0.35:
        warnings.append(
            "Вероятность убытка (капитал меньше вложенного) выше 35%. "
            "Обратите внимание на пессимистичный сценарий."
        )
    if (
        investable_initial > 0
        and investable_initial < INSTRUMENTS["real_estate"].min_investment
    ):
        warnings.append(
            "Недвижимость не включена: стартового капитала меньше "
            "минимального порога входа."
        )
    if horizon > 240:
        warnings.append(
            "Очень длинный горизонт: прогноз чувствителен к инфляции, "
            "ставкам и допущениям о доходности."
        )

    risk_factors = [
        {
            "key": key,
            "label": RISK_FACTOR_LABELS[key],
            "value": round(clamp(params.risk_factors.get(key, 0.0)), 4),
        }
        for key in RISK_FACTOR_LABELS
    ]

    projection = {
        key: value for key, value in mc.items()
        if key not in ("series", "yearly")
    }
    projection["series"] = mc["series"]
    projection["yearly"] = mc["yearly"]

    return {
        "input": {
            "initial_capital": round(params.initial_capital, 2),
            "monthly_contribution": round(monthly, 2),
            "horizon_months": horizon,
            "horizon_years": round(horizon / 12.0, 2),
            "risk_profile": params.risk_profile,
            "inflation_rate": round(params.inflation_rate, 4),
            "monthly_expenses": round(params.monthly_expenses, 2),
            "emergency_fund_months": params.emergency_fund_months,
            "goal_amount": (
                round(params.goal_amount, 2) if params.goal_amount else None
            ),
            "include_crypto": params.include_crypto,
            "monte_carlo_paths": mc["paths"],
            "seed": params.seed,
            "debts": [
                {
                    "name": debt.name,
                    "balance": round(debt.balance, 2),
                    "annual_rate": round(debt.annual_rate, 4),
                    "monthly_payment": round(debt.monthly_payment, 2),
                }
                for debt in params.debts
            ],
        },
        "profile": {
            "key": params.risk_profile,
            "label": profile["label"],
            "description": profile["description"],
            "risk_aversion": profile["risk_aversion"],
        },
        "summary": summary,
        "allocation": items,
        "allocation_summary": {
            "expected_return": allocation["expected_return"],
            "real_expected_return": allocation["real_expected_return"],
            "risk": allocation["risk"],
            "volatility": allocation["volatility"],
            "risk_label": allocation["risk_label"],
        },
        "reserve": reserve_plan,
        "debt_advice": debt_advice,
        "sequence": sequence,
        "bond_ladder": bond_ladder,
        "projection": projection,
        "scenarios": scenarios,
        "risk_factors": risk_factors,
        "warnings": warnings,
        "disclaimer": DISCLAIMER,
    }


