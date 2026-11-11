"""Налоги, аннуитеты и финансовые функции для оптимизатора.

Ставки налогов заданы прогрессивной шкалой НДФЛ 2025+:
13% до 2,4 млн ₽, 15% до 5 млн, 18% до 20 млн, 20% до 50 млн,
22% свыше 50 млн ₽ налоговой базы в год.
"""

from __future__ import annotations

from math import ceil, log
from typing import Iterable, List, Optional, Sequence, Tuple

NDFL_BRACKETS: Tuple[Tuple[float, float], ...] = (
    (2_400_000.0, 0.13),
    (5_000_000.0, 0.15),
    (20_000_000.0, 0.18),
    (50_000_000.0, 0.20),
    (float("inf"), 0.22),
)

DEPOSIT_TAX_FREE_BASE = 1_000_000.0
IIS_CONTRIBUTION_LIMIT = 400_000.0
PROPERTY_DEDUCTION_LIMIT = 2_000_000.0
MORTGAGE_INTEREST_DEDUCTION_LIMIT = 3_000_000.0


def progressive_tax(
    income: float,
    brackets: Sequence[Tuple[float, float]] = NDFL_BRACKETS,
) -> float:
    """НДФЛ по прогрессивной шкале. income — налоговая база за год."""
    if income <= 0:
        return 0.0
    tax = 0.0
    lower = 0.0
    for upper, rate in brackets:
        if income <= lower:
            break
        taxable = min(income, upper) - lower
        if taxable > 0:
            tax += taxable * rate
        lower = upper
    return tax


def marginal_rate(
    income: float,
    brackets: Sequence[Tuple[float, float]] = NDFL_BRACKETS,
) -> float:
    if income <= 0:
        return brackets[0][1]
    lower = 0.0
    for upper, rate in brackets:
        if income <= upper:
            return rate
        lower = upper
    return brackets[-1][1]


def deposit_interest_tax(
    annual_interest: float,
    key_rate: float,
    tax_free_base: float = DEPOSIT_TAX_FREE_BASE,
) -> float:
    """НДФЛ на проценты по вкладам.

    Не облагается сумма процентов в пределах ключевая ставка × 1 млн ₽
    (упрощённая модель). Остаток — по прогрессивной шкале.
    """
    threshold = max(0.0, key_rate * tax_free_base)
    taxable = max(0.0, annual_interest - threshold)
    return progressive_tax(taxable)


def coupon_tax(annual_coupon_income: float) -> float:
    """НДФЛ с купонного дохода (без учёта ИИС)."""
    return progressive_tax(annual_coupon_income)


def rent_tax(annual_rent_income: float, self_employed: bool = False) -> float:
    """НДФЛ с аренды. Для самозанятого — 4% с физлиц / 6% с юрлиц."""
    if annual_rent_income <= 0:
        return 0.0
    if self_employed:
        return annual_rent_income * 0.04
    return progressive_tax(annual_rent_income)


def iis_deduction(
    annual_contribution: float,
    iis_type: str = "none",
    tax_paid: Optional[float] = None,
) -> float:
    """Вычет по ИИС.

    Тип A — возврат 13% от взносов до 400 000 ₽/год, но не больше
    уплаченного НДФЛ. Тип B — освобождение дохода от налога; в модели
    возвращаем 0, а налоговый агент не удерживает налог с дохода.
    """
    if iis_type != "A":
        return 0.0
    base = min(max(0.0, annual_contribution), IIS_CONTRIBUTION_LIMIT)
    deduction = base * 0.13
    if tax_paid is not None:
        deduction = min(deduction, max(0.0, tax_paid))
    return deduction


def property_deduction(
    purchase_price: float,
    mortgage_interest: float = 0.0,
) -> float:
    """Имущественный вычет и вычет по процентам ипотеки."""
    price_base = min(max(0.0, purchase_price), PROPERTY_DEDUCTION_LIMIT)
    interest_base = min(
        max(0.0, mortgage_interest),
        MORTGAGE_INTEREST_DEDUCTION_LIMIT,
    )
    return (price_base + interest_base) * 0.13


def annuity_payment(
    principal: float,
    annual_rate: float,
    months: int,
) -> float:
    """Аннуитетный платёж по кредиту."""
    if principal <= 0 or months <= 0:
        return 0.0
    monthly_rate = annual_rate / 12.0
    if monthly_rate <= 0:
        return principal / months
    factor = (1.0 + monthly_rate) ** months
    return principal * monthly_rate * factor / (factor - 1.0)


def loan_total_interest(
    principal: float,
    annual_rate: float,
    months: int,
) -> float:
    payment = annuity_payment(principal, annual_rate, months)
    return max(0.0, payment * months - principal)


def loan_remaining_balance(
    principal: float,
    annual_rate: float,
    months: int,
    paid_months: int,
) -> float:
    """Остаток долга после paid_months платежей."""
    if principal <= 0 or months <= 0:
        return 0.0
    paid_months = max(0, min(paid_months, months))
    monthly_rate = annual_rate / 12.0
    if monthly_rate <= 0:
        return principal * (1.0 - paid_months / months)
    payment = annuity_payment(principal, annual_rate, months)
    balance = principal * (1.0 + monthly_rate) ** paid_months
    balance -= payment * (((1.0 + monthly_rate) ** paid_months - 1.0) / monthly_rate)
    return max(0.0, balance)


def months_to_payoff(
    principal: float,
    annual_rate: float,
    payment: float,
) -> Optional[int]:
    """Срок погашения при фиксированном платеже."""
    if principal <= 0:
        return 0
    if payment <= 0:
        return None
    monthly_rate = annual_rate / 12.0
    if monthly_rate <= 0:
        return max(1, ceil(principal / payment))
    if payment <= principal * monthly_rate:
        return None
    return max(1, ceil(-log(1.0 - principal * monthly_rate / payment) / log(1.0 + monthly_rate)))


def npv(annual_rate: float, cashflows: Iterable[Tuple[int, float]]) -> float:
    """NPV денежных потоков. cashflows: (месяц, сумма)."""
    monthly = (1.0 + annual_rate) ** (1.0 / 12.0) - 1.0
    return sum(amount / ((1.0 + monthly) ** month) for month, amount in cashflows)


def irr_monthly(cashflows: Sequence[Tuple[int, float]]) -> Optional[float]:
    """Месячная IRR через бисекцию. cashflows: (месяц, сумма)."""
    if not cashflows:
        return None

    def value(rate: float) -> float:
        return sum(amount / ((1.0 + rate) ** month) for month, amount in cashflows)

    low, high = -0.99, 1.0
    low_value = value(low)
    high_value = value(high)
    if low_value * high_value > 0:
        return None
    for _ in range(160):
        middle = (low + high) / 2.0
        middle_value = value(middle)
        if low_value * middle_value <= 0:
            high = middle
        else:
            low = middle
            low_value = middle_value
    return (low + high) / 2.0


def irr_annual(cashflows: Sequence[Tuple[int, float]]) -> Optional[float]:
    monthly = irr_monthly(cashflows)
    if monthly is None or monthly <= -1.0:
        return None
    return (1.0 + monthly) ** 12.0 - 1.0


def cashflow_npv(
    annual_discount_rate: float,
    initial: float,
    monthly: float,
    months: int,
    terminal: float,
) -> float:
    flows: List[Tuple[int, float]] = [(0, -initial)]
    flows.extend((month, -monthly) for month in range(1, months + 1))
    flows.append((months, terminal))
    return npv(annual_discount_rate, flows)


def cashflow_irr(
    initial: float,
    monthly: float,
    months: int,
    terminal: float,
) -> Optional[float]:
    flows: List[Tuple[int, float]] = [(0, -initial)]
    flows.extend((month, -monthly) for month in range(1, months + 1))
    flows.append((months, terminal))
    return irr_annual(flows)


def tax_drag(
    annual_income: float,
    annual_tax: float,
    capital: float,
) -> float:
    """Эффективная годовая налоговая нагрузка на капитал."""
    if capital <= 0:
        return 0.0
    return max(0.0, annual_tax) / capital
