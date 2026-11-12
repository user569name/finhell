"""HTTP API оптимизатора капитала v2.

Маршруты монтируются в основное приложение из simulator.py:
    /api/v2/health
    /api/v2/auth/register       — регистрация по email
    /api/v2/auth/login          — вход и выдача Bearer-токена
    /api/v2/auth/me             — текущий пользователь
    /api/v2/auth/logout         — выход
    /api/v2/macro
    /api/v2/instruments
    /api/v2/optimize            — синхронно, для небольших расчётов
    /api/v2/optimize/async      — фоновая задача на 10 000+ путей
    /api/v2/jobs/{job_id}
    /api/v2/ai/explain          — объяснение по детерминированному контексту
    /api/v2/ai/chat             — чат по расчёту
    /api/v2/compare/rent-vs-buy
    /api/v2/compare/prepay-vs-invest
    /optimizer                  — Sber-style веб-интерфейс

Расчёты, задания и AI требуют Bearer-токен; health, macro, instruments,
scenarios и compare остаются публичными.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse

from . import ai, auth as auth_service
from .engine import DISCLAIMER, run_optimization
from .instruments import build_assets, liquidity_label, scenario_templates
from .jobs import JOBS
from .market_data import default_macro, get_macro_snapshot
from .models import (
    AIChatRequest,
    AIChatResponse,
    AIContextRequest,
    AIExplanation,
    AuthLoginRequest,
    AuthMeResponse,
    AuthRegisterRequest,
    AuthResponse,
    AuthUser,
    JobStatus,
    MacroSnapshot,
    MarketOverrides,
    OptimizeRequest,
    OptimizeResponse,
    PrepayVsInvestRequest,
    RentVsBuyRequest,
)
from .taxes import (
    annuity_payment,
    cashflow_irr,
    cashflow_npv,
    loan_remaining_balance,
    loan_total_interest,
    property_deduction,
)

router = APIRouter(prefix="/api/v2", tags=["Оптимизатор капитала v2"])

SYNC_PATH_LIMIT = 3000
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@router.get("/health", summary="Состояние оптимизатора")
def optimizer_health() -> Dict[str, object]:
    return {
        "status": "ok",
        "version": "2.0.0",
        "engine": "pure-python",
        "monte_carlo_default_paths": 10_000,
        "sync_path_limit": SYNC_PATH_LIMIT,
        "jobs": JOBS.stats(),
        "ai": ai.provider_status(),
        "contexts_cached": ai.CONTEXT_CACHE.size(),
        "auth": {
            "mode": "email-password",
            "token_ttl_seconds": auth_service.TOKEN_TTL_SECONDS,
        },
    }


@router.post(
    "/auth/register",
    response_model=AuthResponse,
    status_code=201,
    summary="Регистрация по email",
)
def auth_register(request: AuthRegisterRequest) -> AuthResponse:
    try:
        user, token = auth_service.register(
            request.email,
            request.password,
            request.name,
        )
    except auth_service.EmailTakenError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except auth_service.ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return AuthResponse(
        token=token,
        expires_in=auth_service.TOKEN_TTL_SECONDS,
        user=AuthUser(**user),
    )


@router.post(
    "/auth/login",
    response_model=AuthResponse,
    summary="Вход по email",
)
def auth_login(request: AuthLoginRequest) -> AuthResponse:
    try:
        user, token = auth_service.login(request.email, request.password)
    except auth_service.ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except auth_service.InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=401,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return AuthResponse(
        token=token,
        expires_in=auth_service.TOKEN_TTL_SECONDS,
        user=AuthUser(**user),
    )


@router.get(
    "/auth/me",
    response_model=AuthMeResponse,
    summary="Текущий пользователь",
)
def auth_me(
    user: Dict[str, Any] = Depends(auth_service.current_user),
) -> AuthMeResponse:
    return AuthMeResponse(user=AuthUser(**user))


@router.post("/auth/logout", summary="Выход (токен удаляет клиент)")
def auth_logout(
    _user: Dict[str, Any] = Depends(auth_service.current_user),
) -> Dict[str, str]:
    return {
        "status": "ok",
        "message": "Токен удаляется на клиенте; сервер его не хранит.",
    }


@router.get("/macro", response_model=MacroSnapshot, summary="Макросрез и источники")
def macro_snapshot(
    refresh: bool = Query(
        False,
        description="Попробовать обновить данные ЦБ РФ и MOEX ISS (может занять несколько секунд).",
    ),
) -> MacroSnapshot:
    return get_macro_snapshot(refresh=refresh)


@router.post("/macro", response_model=MacroSnapshot, summary="Макросрез с ручными переопределениями")
def macro_override(
    overrides: MarketOverrides,
    refresh: bool = Query(False),
) -> MacroSnapshot:
    return get_macro_snapshot(refresh=refresh, overrides=overrides)


@router.get("/instruments", summary="Каталог инструментов и профилей риска")
def instruments_catalog() -> Dict[str, object]:
    macro = default_macro()
    assets = build_assets(macro)
    return {
        "assets": [
            {
                "key": asset.key,
                "name": asset.name,
                "kind": asset.kind,
                "expected_return": asset.expected_return,
                "volatility": asset.volatility,
                "liquidity": asset.liquidity,
                "liquidity_label": liquidity_label(asset.liquidity),
                "duration_years": asset.duration_years,
                "credit_risk": asset.credit_risk,
                "tax_type": asset.tax_type,
                "min_investment": asset.min_investment,
                "fee_rate": asset.fee_rate,
                "description": asset.description,
            }
            for asset in assets.values()
        ],
        "risk_levels": [
            {
                "key": "low",
                "label": "Низкий риск",
                "description": "Вклады, накопительные счета и короткие ОФЗ.",
            },
            {
                "key": "medium",
                "label": "Средний риск",
                "description": "Длинные ОФЗ, корпоративные и муниципальные облигации, недвижимость.",
            },
            {
                "key": "high",
                "label": "Высокий риск",
                "description": "Длинная дюрация, кредитный риск, ипотечное плечо.",
            },
        ],
        "distributions": [
            {"key": "normal", "label": "Нормальное распределение"},
            {"key": "student_t", "label": "Распределение Стьюдента (тяжёлые хвосты)"},
            {"key": "historical", "label": "Историческая выборка"},
        ],
        "liquidity_needs": [
            {"key": "high", "label": "Высокая — деньги могут понадобиться скоро"},
            {"key": "medium", "label": "Средняя — часть капитала должна быть доступна"},
            {"key": "low", "label": "Низкая — готов ждать несколько лет"},
        ],
        "credit_types": [
            {"key": "none", "label": "Без кредита"},
            {"key": "consumer", "label": "Потребительский кредит"},
            {"key": "mortgage", "label": "Ипотека"},
        ],
        "disclaimer": DISCLAIMER,
    }


@router.get("/scenarios", summary="Шаблоны сценариев под профиль")
def scenarios_preview(
    capital: float = Query(500_000, ge=0),
    monthly: float = Query(20_000, ge=0),
    horizon_months: int = Query(60, ge=1, le=600),
    risk_tolerance: str = Query("moderate"),
    liquidity_need: str = Query("medium"),
) -> Dict[str, object]:
    from .models import LiquidityNeed, RiskTolerance, UserProfile

    try:
        profile = UserProfile(
            capital=capital,
            monthly=monthly,
            horizon_months=horizon_months,
            risk_tolerance=RiskTolerance(risk_tolerance),
            liquidity_need=LiquidityNeed(liquidity_need),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    macro = get_macro_snapshot()
    assets = build_assets(macro)
    scenarios = scenario_templates(profile, macro, assets, max_scenarios=18)
    return {
        "scenarios": [
            {
                "id": scenario.id,
                "name": scenario.name,
                "risk_level": scenario.risk_level.value,
                "description": scenario.description,
                "weights": scenario.weights,
                "tags": scenario.tags,
                "leverage": scenario.leverage,
            }
            for scenario in scenarios
        ],
        "count": len(scenarios),
    }


@router.post(
    "/optimize",
    response_model=OptimizeResponse,
    summary="Синхронный расчёт (до 3000 путей на сценарий)",
)
def optimize_sync(
    request: OptimizeRequest,
    _user: Dict[str, Any] = Depends(auth_service.current_user),
) -> OptimizeResponse:
    if request.options.monte_carlo_paths > SYNC_PATH_LIMIT:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Синхронный режим ограничен {SYNC_PATH_LIMIT} путями. "
                "Для 10 000+ путей используйте POST /api/v2/optimize/async."
            ),
        )
    try:
        return run_optimization(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/optimize/async",
    status_code=202,
    summary="Фоновый расчёт на 10 000+ путей",
)
def optimize_async(
    request: OptimizeRequest,
    user: Dict[str, Any] = Depends(auth_service.current_user),
) -> Dict[str, object]:
    job_id = JOBS.submit(request, user_id=user["id"])
    estimated = max(
        2,
        int(
            request.options.max_scenarios
            * request.options.monte_carlo_paths
            * request.profile.horizon_months
            / 350_000
        ),
    )
    return {
        "job_id": job_id,
        "status": "queued",
        "poll_url": f"/api/v2/jobs/{job_id}",
        "estimated_seconds": estimated,
        "message": "Расчёт запущен. Опрашивайте статус по poll_url.",
    }


@router.get("/jobs/{job_id}", response_model=JobStatus, summary="Статус фонового расчёта")
def job_status(
    job_id: str,
    user: Dict[str, Any] = Depends(auth_service.current_user),
) -> JobStatus:
    job = JOBS.get(job_id, user_id=user["id"])
    if job is None:
        raise HTTPException(status_code=404, detail="Задание не найдено или истекло.")
    return job


@router.get("/jobs", response_model=List[JobStatus], summary="Последние задания")
def jobs_list(
    limit: int = Query(20, ge=1, le=100),
    user: Dict[str, Any] = Depends(auth_service.current_user),
) -> List[JobStatus]:
    return JOBS.list_recent(limit=limit, user_id=user["id"])


@router.post("/ai/explain", response_model=AIExplanation, summary="AI-объяснение расчёта")
def ai_explain(
    request: AIContextRequest,
    _user: Dict[str, Any] = Depends(auth_service.current_user),
) -> AIExplanation:
    try:
        return ai.explain(
            context_id=request.context_id,
            context=request.context,
            use_llm=request.use_llm,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/ai/explain/stream", summary="AI-объяснение (SSE)")
def ai_explain_stream(
    request: AIContextRequest,
    _user: Dict[str, Any] = Depends(auth_service.current_user),
) -> StreamingResponse:
    generator = ai.stream_explanation(
        context_id=request.context_id,
        context=request.context,
        use_llm=request.use_llm,
    )
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.post("/ai/chat", response_model=AIChatResponse, summary="Чат по расчёту")
def ai_chat(
    request: AIChatRequest,
    _user: Dict[str, Any] = Depends(auth_service.current_user),
) -> AIChatResponse:
    try:
        return ai.chat(
            context_id=request.context_id,
            context=request.context,
            question=request.question,
            history=request.history,
            use_llm=request.use_llm,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/ai/chat/stream", summary="Чат по расчёту (SSE)")
def ai_chat_stream(
    request: AIChatRequest,
    _user: Dict[str, Any] = Depends(auth_service.current_user),
) -> StreamingResponse:
    generator = ai.stream_chat(
        context_id=request.context_id,
        context=request.context,
        question=request.question,
        history=request.history,
        use_llm=request.use_llm,
    )
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.post("/compare/rent-vs-buy", summary="Сравнение аренды и покупки")
def compare_rent_vs_buy(request: RentVsBuyRequest) -> Dict[str, object]:
    down_payment = (
        request.down_payment
        if request.down_payment is not None
        else min(request.capital, request.property_value * 0.3)
    )
    down_payment = min(max(0.0, down_payment), request.property_value)
    mortgage = max(0.0, request.property_value - down_payment)
    payment = annuity_payment(
        mortgage, request.mortgage_rate, request.mortgage_term_months
    )
    rent = (
        request.rent_monthly
        if request.rent_monthly is not None
        else request.property_value * request.rent_yield / 12.0
    )
    years = request.horizon_months / 12.0
    remaining = loan_remaining_balance(
        mortgage,
        request.mortgage_rate,
        request.mortgage_term_months,
        request.horizon_months,
    )
    deduction = (
        property_deduction(
            request.property_value,
            loan_total_interest(
                mortgage, request.mortgage_rate, request.mortgage_term_months
            ),
        )
        if request.include_property_deduction
        else 0.0
    )
    buy_terminal = (
        request.property_value * (1.0 + request.real_estate_growth) ** years
        - remaining
        + deduction
    )
    monthly_diff = payment - rent
    rent_terminal = down_payment
    monthly_return = (1.0 + request.investment_return) ** (1.0 / 12.0) - 1.0
    for _ in range(request.horizon_months):
        rent_terminal *= 1.0 + monthly_return
        rent_terminal += monthly_diff
    npv_buy = cashflow_npv(
        request.discount_rate, down_payment, payment,
        request.horizon_months, buy_terminal,
    )
    npv_rent = cashflow_npv(
        request.discount_rate, down_payment, payment,
        request.horizon_months, rent_terminal,
    )
    irr_buy = cashflow_irr(
        down_payment, payment, request.horizon_months, buy_terminal
    )
    irr_rent = cashflow_irr(
        down_payment, payment, request.horizon_months, rent_terminal
    )
    return {
        "name": "Аренда vs покупка",
        "better_option": "Покупка" if npv_buy > npv_rent else "Аренда",
        "npv_buy": round(npv_buy, 2),
        "npv_rent": round(npv_rent, 2),
        "npv_difference": round(npv_buy - npv_rent, 2),
        "irr_buy": round(irr_buy, 4) if irr_buy is not None else None,
        "irr_rent": round(irr_rent, 4) if irr_rent is not None else None,
        "details": {
            "property_value": round(request.property_value, 2),
            "down_payment": round(down_payment, 2),
            "mortgage": round(mortgage, 2),
            "monthly_payment": round(payment, 2),
            "monthly_rent": round(rent, 2),
            "monthly_difference": round(monthly_diff, 2),
            "buy_terminal": round(buy_terminal, 2),
            "rent_terminal": round(rent_terminal, 2),
            "remaining_mortgage": round(remaining, 2),
            "property_deduction": round(deduction, 2),
        },
        "note": (
            "Упрощённая модель: одинаковый денежный поток (первый взнос и "
            "платёж по ипотеке), покупка с остатком долга и вычетами против "
            "аренды с инвестированием разницы."
        ),
    }


@router.post("/compare/prepay-vs-invest", summary="Досрочное погашение vs инвестирование")
def compare_prepay_vs_invest(request: PrepayVsInvestRequest) -> Dict[str, object]:
    prepay_capital = min(request.capital, request.balance)
    years = request.horizon_months / 12.0
    saved_interest = prepay_capital * request.annual_rate * years
    prepay_terminal = prepay_capital * (1.0 + request.annual_rate) ** years
    invest_terminal = prepay_capital * (1.0 + request.investment_return) ** years
    return {
        "name": "Досрочно погасить vs вложить",
        "better_option": "Погасить" if prepay_terminal > invest_terminal else "Вложить",
        "npv_difference": round(prepay_terminal - invest_terminal, 2),
        "irr_difference": round(request.annual_rate - request.investment_return, 4),
        "details": {
            "debt_rate": round(request.annual_rate, 4),
            "investment_return": round(request.investment_return, 4),
            "prepay_capital": round(prepay_capital, 2),
            "saved_interest": round(saved_interest, 2),
            "prepay_terminal": round(prepay_terminal, 2),
            "invest_terminal": round(invest_terminal, 2),
            "monthly_payment": round(request.monthly_payment, 2),
        },
        "note": (
            "Досрочное погашение — гарантированная экономия на процентах; "
            "инвестирование — риск, но потенциально более высокая доходность. "
            "Сравнение не учитывает налоги на инвестиционный доход."
        ),
    }


@router.get("/optimizer", response_class=HTMLResponse, include_in_schema=False)
def optimizer_page() -> HTMLResponse:
    template = Path(__file__).resolve().parent.parent / "templates" / "optimizer.html"
    if not template.exists():
        return HTMLResponse(
            "<h1>Интерфейс оптимизатора не найден</h1>"
            "<p>API доступен в <a href='/docs'>/docs</a>.</p>",
            status_code=500,
        )
    return HTMLResponse(template.read_text(encoding="utf-8"))
