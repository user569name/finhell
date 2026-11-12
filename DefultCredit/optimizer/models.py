"""Pydantic-модели оптимизатора капитала v2.

Все ставки и доходности передаются в долях: 0.16 = 16% годовых.
Суммы — в рублях.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class RiskTolerance(str, Enum):
    conservative = "conservative"
    moderate = "moderate"
    aggressive = "aggressive"


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class LiquidityNeed(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class CreditType(str, Enum):
    none = "none"
    consumer = "consumer"
    mortgage = "mortgage"


class Distribution(str, Enum):
    normal = "normal"
    student_t = "student_t"
    historical = "historical"


class IISProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["none", "A", "B"] = "none"
    annual_contribution: float = Field(0, ge=0, le=10_000_000)
    years: int = Field(0, ge=0, le=30)


class ExistingMortgage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    balance: float = Field(0, ge=0, le=1_000_000_000)
    annual_rate: float = Field(0, ge=0, le=1)
    monthly_payment: float = Field(0, ge=0, le=10_000_000)
    remaining_months: int = Field(0, ge=0, le=600)
    property_value: float = Field(0, ge=0, le=1_000_000_000)


class ExistingDeposit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: float = Field(0, ge=0, le=1_000_000_000)
    annual_rate: float = Field(0, ge=0, le=1)
    term_months: int = Field(0, ge=0, le=600)


class UserProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capital: float = Field(500_000, ge=0, le=1_000_000_000_000)
    monthly: float = Field(20_000, ge=0, le=100_000_000)
    horizon_months: int = Field(60, ge=1, le=600)
    risk_tolerance: RiskTolerance = RiskTolerance.moderate
    liquidity_need: LiquidityNeed = LiquidityNeed.medium
    credit_willingness: bool = False
    credit_type: CreditType = CreditType.none
    goal_amount: Optional[float] = Field(None, ge=0, le=1_000_000_000_000)
    monthly_expenses: float = Field(50_000, ge=0, le=100_000_000)
    emergency_fund_months: int = Field(6, ge=0, le=36)
    existing_mortgage: Optional[ExistingMortgage] = None
    iis: Optional[IISProfile] = None
    deposits: List[ExistingDeposit] = Field(default_factory=list)
    region: str = Field("Москва", max_length=120)


class MarketOverrides(BaseModel):
    """Ручные значения макропараметров. Все ставки — в долях."""

    model_config = ConfigDict(extra="forbid")

    key_rate: Optional[float] = Field(None, ge=0, le=1)
    inflation_yoy: Optional[float] = Field(None, ge=-0.5, le=1)
    inflation_expected: Optional[float] = Field(None, ge=-0.5, le=1)
    deposit_rate: Optional[float] = Field(None, ge=0, le=1)
    savings_rate: Optional[float] = Field(None, ge=0, le=1)
    credit_rate: Optional[float] = Field(None, ge=0, le=1)
    mortgage_rate: Optional[float] = Field(None, ge=0, le=1)
    ofz_yield_10y: Optional[float] = Field(None, ge=0, le=1)
    corporate_yield: Optional[float] = Field(None, ge=0, le=1)
    municipal_yield: Optional[float] = Field(None, ge=0, le=1)
    real_estate_growth: Optional[float] = Field(None, ge=-0.5, le=1)
    rent_yield: Optional[float] = Field(None, ge=0, le=1)
    usd_rub: Optional[float] = Field(None, ge=0, le=10_000)
    eur_rub: Optional[float] = Field(None, ge=0, le=10_000)


class OptimizeOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    monte_carlo_paths: int = Field(
        10_000, ge=100, le=50_000,
        description="Число симуляций на сценарий. По умолчанию 10 000.",
    )
    distribution: Distribution = Distribution.normal
    seed: int = Field(42, ge=0, le=2_147_483_647)
    max_scenarios: int = Field(18, ge=10, le=30)
    include_real_estate: bool = True
    include_mortgage: bool = True
    run_stress_tests: bool = True


class OptimizeRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "profile": {
                    "capital": 500000,
                    "monthly": 20000,
                    "horizon_months": 60,
                    "risk_tolerance": "moderate",
                    "liquidity_need": "medium",
                    "credit_willingness": False,
                    "credit_type": "none",
                    "goal_amount": 1500000,
                    "monthly_expenses": 50000,
                    "emergency_fund_months": 6,
                    "region": "Москва",
                },
                "options": {
                    "monte_carlo_paths": 10000,
                    "distribution": "normal",
                    "seed": 42,
                    "max_scenarios": 18,
                },
            }
        },
    )

    profile: UserProfile = Field(default_factory=UserProfile)
    market_overrides: Optional[MarketOverrides] = None
    options: OptimizeOptions = Field(default_factory=OptimizeOptions)
    refresh_macro: bool = False


class DataPoint(BaseModel):
    value: float
    unit: str = "ratio"
    source: str
    updated_at: str
    is_fallback: bool = False
    note: Optional[str] = None


class CurvePoint(BaseModel):
    tenor_months: int
    yield_rate: float


class DataSourceInfo(BaseModel):
    key: str
    name: str
    url: Optional[str] = None
    status: Literal["live", "cache", "fallback", "manual"] = "fallback"
    updated_at: str
    note: Optional[str] = None


class MacroSnapshot(BaseModel):
    key_rate: DataPoint
    inflation_yoy: DataPoint
    inflation_expected: DataPoint
    deposit_rate: DataPoint
    savings_rate: DataPoint
    credit_rate: DataPoint
    mortgage_rate: DataPoint
    ofz_yield_10y: DataPoint
    corporate_yield: DataPoint
    municipal_yield: DataPoint
    real_estate_growth: DataPoint
    rent_yield: DataPoint
    usd_rub: DataPoint
    eur_rub: DataPoint
    ofz_curve: List[CurvePoint]
    fetched_at: str
    data_sources: List[DataSourceInfo]


class AllocationItem(BaseModel):
    key: str
    name: str
    weight: float
    amount: float
    expected_return: float
    volatility: float
    liquidity: float
    tax_type: str
    tax_note: str


class Percentiles(BaseModel):
    p5: float
    p25: float
    p50: float
    p75: float
    p95: float


class StressResult(BaseModel):
    scenario: str
    impact_p50: float
    impact_p5: float
    terminal_p50: float
    note: str


class TaxSummary(BaseModel):
    annual_tax: float
    total_tax_estimate: float
    effective_rate: float
    deductions: float
    note: str


class FeeSummary(BaseModel):
    annual_fee: float
    total_fee_estimate: float
    effective_rate: float
    note: str


class MonteCarloSummary(BaseModel):
    paths: int
    distribution: str
    terminal_p5: float
    terminal_p25: float
    terminal_p50: float
    terminal_p75: float
    terminal_p95: float
    real_terminal_p50: float
    total_contributions: float
    probability_goal: Optional[float]
    probability_loss: float
    var_95: float
    cvar_95: float
    max_drawdown_median: float
    max_drawdown_p90: float
    histogram: List[Dict[str, float]]
    series: List[Dict[str, float]]
    sample_paths: List[List[float]]


class ScenarioResult(BaseModel):
    id: str
    name: str
    risk_level: RiskLevel
    description: str
    allocation: List[AllocationItem]
    expected_return_nominal: float
    expected_return_real: float
    after_tax_return: float
    volatility: float
    sharpe: float
    sortino: float
    var_95: float
    cvar_95: float
    max_drawdown: float
    probability_goal: Optional[float]
    probability_loss: float
    liquidity: float
    liquidity_label: str
    duration_years: float
    taxes: TaxSummary
    fees: FeeSummary
    monte_carlo: MonteCarloSummary
    stress_tests: List[StressResult]
    npv: float
    irr: Optional[float]
    score: float
    rank: int
    why_recommended: str
    tags: List[str]


class RiskProfileResult(BaseModel):
    level: RiskLevel
    label: str
    description: str
    best_option_id: Optional[str]
    options: List[ScenarioResult]
    summary: Dict[str, float]


class ComparisonItem(BaseModel):
    name: str
    better_option: str
    npv_difference: float
    irr_difference: Optional[float]
    details: Dict[str, float]
    note: str


class ComparisonResult(BaseModel):
    rent_vs_buy: Optional[ComparisonItem] = None
    prepay_vs_invest: Optional[ComparisonItem] = None


class AIExplanation(BaseModel):
    summary: str
    risk_profiles: Dict[str, str]
    steps: List[str]
    why: str
    risks: str
    disclaimer: str
    generated_by: str = "template"


class OptimizeResponse(BaseModel):
    request_id: str
    generated_at: str
    profile: UserProfile
    macro: MacroSnapshot
    risk_profiles: Dict[str, RiskProfileResult]
    top_options: List[ScenarioResult]
    comparisons: ComparisonResult
    warnings: List[str]
    disclaimer: str
    context_id: str
    ai_template: AIExplanation


class AuthRegisterRequest(BaseModel):
    """Регистрация по email и паролю."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(..., max_length=254)
    password: str = Field(..., max_length=128)
    name: str = Field("", max_length=120)


class AuthLoginRequest(BaseModel):
    """Вход по email и паролю."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(..., max_length=254)
    password: str = Field(..., max_length=128)


class AuthUser(BaseModel):
    id: str
    email: str
    name: str = ""
    created_at: str


class AuthResponse(BaseModel):
    token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: AuthUser


class AuthMeResponse(BaseModel):
    user: AuthUser


class AIContextRequest(BaseModel):
    context_id: Optional[str] = None
    context: Optional[Dict[str, object]] = None
    use_llm: bool = True


class AIChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class AIChatRequest(BaseModel):
    context_id: Optional[str] = None
    context: Optional[Dict[str, object]] = None
    question: str = Field(..., min_length=1, max_length=4000)
    history: List[AIChatMessage] = Field(default_factory=list)
    use_llm: bool = True


class AIChatResponse(BaseModel):
    answer: str
    context_id: Optional[str]
    disclaimer: str
    generated_by: str


class JobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "running", "done", "error"]
    progress: int = 0
    message: str = ""
    created_at: str
    updated_at: str
    result: Optional[OptimizeResponse] = None
    error: Optional[str] = None


class RentVsBuyRequest(BaseModel):
    """Отдельное сравнение «аренда vs покупка» без полной оптимизации."""

    model_config = ConfigDict(extra="forbid")

    capital: float = Field(1_000_000, ge=0, le=1_000_000_000_000)
    property_value: float = Field(6_000_000, gt=0, le=1_000_000_000_000)
    down_payment: Optional[float] = Field(None, ge=0, le=1_000_000_000_000)
    mortgage_rate: float = Field(0.20, ge=0, le=1)
    mortgage_term_months: int = Field(240, ge=12, le=600)
    horizon_months: int = Field(60, ge=1, le=600)
    rent_monthly: Optional[float] = Field(None, ge=0, le=10_000_000)
    rent_yield: float = Field(0.05, ge=0, le=1)
    real_estate_growth: float = Field(0.08, ge=-0.5, le=1)
    investment_return: float = Field(0.15, ge=-0.5, le=1)
    discount_rate: float = Field(0.16, ge=0, le=1)
    include_property_deduction: bool = True


class PrepayVsInvestRequest(BaseModel):
    """Отдельное сравнение «досрочно погасить vs вложить»."""

    model_config = ConfigDict(extra="forbid")

    balance: float = Field(1_000_000, gt=0, le=1_000_000_000_000)
    annual_rate: float = Field(0.20, ge=0, le=1)
    capital: float = Field(500_000, ge=0, le=1_000_000_000_000)
    horizon_months: int = Field(60, ge=1, le=600)
    investment_return: float = Field(0.15, ge=-0.5, le=1)
    monthly_payment: float = Field(0, ge=0, le=10_000_000)
