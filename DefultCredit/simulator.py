"""FastAPI-приложение экономического симулятора.

Запуск:
    python simulator.py
    # или из корня проекта:
    uvicorn DefultCredit.simulator:app --reload --port 8001

Swagger: http://127.0.0.1:8001/docs
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

try:
    from .simulator_engine import (
        DEFAULT_RISK_FACTORS,
        INSTRUMENTS,
        RISK_FACTOR_LABELS,
        RISK_PROFILES,
        Debt,
        SimulationParams,
        clamp,
        effective_risk,
    )
    from .simulator_plan import DISCLAIMER, analyze_bond, run_simulation
    from .optimizer.api import router as optimizer_router
except ImportError:  # запуск как обычного скрипта
    from simulator_engine import (
        DEFAULT_RISK_FACTORS,
        INSTRUMENTS,
        RISK_FACTOR_LABELS,
        RISK_PROFILES,
        Debt,
        SimulationParams,
        clamp,
        effective_risk,
    )
    from simulator_plan import DISCLAIMER, analyze_bond, run_simulation
    from optimizer.api import router as optimizer_router


# ---------------------------------------------------------------------------
# Модели запросов
# ---------------------------------------------------------------------------

class RiskFactorsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market: float = Field(
        0.50, ge=0, le=1,
        description="Рыночный риск: общая нестабильность рынков.",
    )
    credit: float = Field(
        0.30, ge=0, le=1,
        description="Кредитный риск: вероятность дефолта эмитента.",
    )
    rate: float = Field(
        0.40, ge=0, le=1,
        description="Процентный риск: рост/падение ключевой ставки.",
    )
    liquidity: float = Field(
        0.20, ge=0, le=1,
        description="Риск ликвидности: насколько трудно продать актив.",
    )
    currency: float = Field(
        0.30, ge=0, le=1,
        description="Валютный риск: ослабление/укрепление рубля.",
    )
    inflation: float = Field(
        0.50, ge=0, le=1,
        description="Инфляционный риск: рост цен.",
    )


class DebtInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field("Долг", max_length=120)
    balance: float = Field(..., gt=0, le=1_000_000_000_000)
    annual_rate: float = Field(
        ..., ge=0, le=1,
        description="Ставка в долях: 0.21 = 21% годовых.",
    )
    monthly_payment: float = Field(
        0.0, ge=0, le=1_000_000_000,
        description="Плановый ежемесячный платёж.",
    )


class SimulationRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "initial_capital": 1_000_000,
                "monthly_contribution": 30_000,
                "horizon_months": 60,
                "risk_profile": "balanced",
                "inflation_rate": 0.08,
                "monthly_expenses": 50_000,
                "emergency_fund_months": 6,
                "goal_amount": 3_000_000,
                "risk_factors": {
                    "market": 0.5,
                    "credit": 0.3,
                    "rate": 0.4,
                    "liquidity": 0.2,
                    "currency": 0.3,
                    "inflation": 0.5,
                },
                "debts": [],
                "monte_carlo_paths": 800,
                "seed": 42,
            }
        },
    )

    initial_capital: float = Field(
        1_000_000, ge=0, le=1_000_000_000_000,
        description="Сколько денег есть сейчас.",
    )
    monthly_contribution: float = Field(
        30_000, ge=0, le=1_000_000_000,
        description="Сколько готовы откладывать каждый месяц.",
    )
    horizon_months: int = Field(
        60, ge=1, le=600,
        description="Срок в месяцах.",
    )
    risk_profile: Literal["conservative", "balanced", "aggressive"] = Field(
        "balanced",
        description="Допустимый риск портфеля.",
    )
    inflation_rate: float = Field(
        0.08, ge=0, le=1,
        description="Ожидаемая инфляция в долях: 0.08 = 8%.",
    )
    monthly_expenses: float = Field(
        50_000, ge=0, le=1_000_000_000,
        description="Расходы в месяц — для расчёта резерва.",
    )
    emergency_fund_months: int = Field(
        6, ge=0, le=36,
        description="На сколько месяцев расходов нужен резерв.",
    )
    goal_amount: Optional[float] = Field(
        None, ge=0, le=1_000_000_000_000,
        description="Цель по капиталу, если есть.",
    )
    risk_factors: RiskFactorsInput = Field(
        default_factory=RiskFactorsInput,
        description="Оценка факторов риска от 0 до 1.",
    )
    asset_risk_overrides: Dict[str, float] = Field(
        default_factory=dict,
        description="Точечный риск по активу: {stocks: 0.8}.",
    )
    return_overrides: Dict[str, float] = Field(
        default_factory=dict,
        description="Свои ожидаемые доходности: {stocks: 0.18}.",
    )
    debts: List[DebtInput] = Field(
        default_factory=list,
        description="Необязательный список долгов.",
    )
    include_crypto: bool = Field(
        True,
        description="Разрешить криптовалюту в агрессивных профилях.",
    )
    monte_carlo_paths: int = Field(
        800, ge=100, le=5000,
        description="Число сценариев Монте-Карло.",
    )
    seed: int = Field(
        42, ge=0, le=2_147_483_647,
        description="Зерно генератора для воспроизводимости.",
    )

    @field_validator("asset_risk_overrides")
    @classmethod
    def validate_asset_overrides(cls, value: Dict[str, float]) -> Dict[str, float]:
        unknown = sorted(set(value) - set(INSTRUMENTS))
        if unknown:
            raise ValueError(
                "Неизвестные активы: " + ", ".join(unknown)
            )
        return {key: clamp(float(item)) for key, item in value.items()}

    @field_validator("return_overrides")
    @classmethod
    def validate_return_overrides(cls, value: Dict[str, float]) -> Dict[str, float]:
        unknown = sorted(set(value) - set(INSTRUMENTS))
        if unknown:
            raise ValueError(
                "Неизвестные активы: " + ", ".join(unknown)
            )
        for key, item in value.items():
            if item < -0.5 or item > 1.5:
                raise ValueError(
                    f"Доходность {key} должна быть от -50% до 150%."
                )
        return {key: float(item) for key, item in value.items()}


class BondRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "face_value": 1000,
                "price": 950,
                "coupon_rate": 0.12,
                "coupons_per_year": 2,
                "years_to_maturity": 5,
                "reinvest_rate": 0.12,
            }
        },
    )

    face_value: float = Field(1000, gt=0, le=1_000_000_000)
    price: float = Field(1000, gt=0, le=1_000_000_000)
    coupon_rate: float = Field(
        0.12, ge=0, le=1,
        description="Купон в долях: 0.12 = 12% годовых.",
    )
    coupons_per_year: int = Field(2, ge=1, le=12)
    years_to_maturity: float = Field(5, gt=0, le=100)
    reinvest_rate: Optional[float] = Field(
        None, ge=-0.5, le=1,
        description="Ставка реинвестирования купонов; по умолчанию равен купону.",
    )


# ---------------------------------------------------------------------------
# Приложение
# ---------------------------------------------------------------------------

app = FastAPI(
    title="ФинХелл — экономический симулятор и оптимизатор капитала",
    description=(
        "v1: пошаговый симулятор под стартовый капитал, взнос, срок и факторы "
        "риска. v2: оптимизатор капитала с тремя уровнями риска, 10 000+ "
        "Монте-Карло путей, стресс-тестами, сравнениями и AI-объяснениями. "
        "Инструменты v2: вклады, накопительные счета, ОФЗ, корпоративные и "
        "муниципальные облигации, недвижимость и ипотека. Акции и криптовалюта "
        "в v2 исключены."
    ),
    version="2.1.0",
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(optimizer_router)


@app.get("/optimizer", response_class=HTMLResponse, include_in_schema=False)
def optimizer_page() -> HTMLResponse:
    template = Path(__file__).resolve().parent / "templates" / "optimizer.html"
    if not template.exists():
        return HTMLResponse(
            "<h1>Шаблон оптимизатора не найден</h1>"
            "<p>Откройте <a href='/docs'>/docs</a> для работы через API.</p>",
            status_code=500,
        )
    return HTMLResponse(template.read_text(encoding="utf-8"))


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index() -> HTMLResponse:
    template = Path(__file__).resolve().parent / "templates" / "simulator.html"
    if not template.exists():
        return HTMLResponse(
            "<h1>Шаблон интерфейса не найден</h1>"
            "<p>Откройте <a href='/docs'>/docs</a> для работы через API.</p>",
            status_code=500,
        )
    return HTMLResponse(template.read_text(encoding="utf-8"))


@app.get("/health", tags=["Служебное"], summary="Проверка живости")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/instruments", tags=["Справочники"], summary="Каталог инструментов")
def instruments() -> Dict[str, object]:
    return {
        "risk_profiles": [
            {
                "key": key,
                "label": profile["label"],
                "description": profile["description"],
                "risk_aversion": profile["risk_aversion"],
            }
            for key, profile in RISK_PROFILES.items()
        ],
        "risk_factors": [
            {
                "key": key,
                "label": RISK_FACTOR_LABELS[key],
                "default": DEFAULT_RISK_FACTORS[key],
            }
            for key in RISK_FACTOR_LABELS
        ],
        "instruments": [
            {
                "key": instrument.key,
                "name": instrument.name,
                "short_name": instrument.short_name,
                "annual_return": instrument.annual_return,
                "volatility": instrument.volatility,
                "risk": round(
                    effective_risk(instrument, DEFAULT_RISK_FACTORS), 4
                ),
                "liquidity": instrument.liquidity,
                "min_investment": instrument.min_investment,
                "income_type": instrument.income_type,
                "description": instrument.description,
            }
            for instrument in INSTRUMENTS.values()
        ],
        "disclaimer": DISCLAIMER,
    }


@app.post("/simulate", tags=["Симулятор"], summary="Построить финансовый план")
def simulate_endpoint(request: SimulationRequest) -> Dict[str, object]:
    params = SimulationParams(
        initial_capital=request.initial_capital,
        monthly_contribution=request.monthly_contribution,
        horizon_months=request.horizon_months,
        risk_profile=request.risk_profile,
        inflation_rate=request.inflation_rate,
        monthly_expenses=request.monthly_expenses,
        emergency_fund_months=request.emergency_fund_months,
        goal_amount=request.goal_amount,
        risk_factors=request.risk_factors.model_dump(),
        asset_risk_overrides=request.asset_risk_overrides,
        return_overrides=request.return_overrides,
        include_crypto=request.include_crypto,
        monte_carlo_paths=request.monte_carlo_paths,
        seed=request.seed,
        debts=[
            Debt(
                name=debt.name,
                balance=debt.balance,
                annual_rate=debt.annual_rate,
                monthly_payment=debt.monthly_payment,
            )
            for debt in request.debts
        ],
    )
    try:
        return run_simulation(params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/bond/analyze", tags=["Облигации"], summary="Расчёт доходности облигации")
def bond_endpoint(request: BondRequest) -> Dict[str, object]:
    try:
        return analyze_bond(
            face_value=request.face_value,
            price=request.price,
            coupon_rate=request.coupon_rate,
            coupons_per_year=request.coupons_per_year,
            years_to_maturity=request.years_to_maturity,
            reinvest_rate=request.reinvest_rate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8001)
