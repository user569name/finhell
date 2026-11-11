"""Тесты оптимизатора капитала v2.

Запуск из корня проекта:
    .\\myvenv\\Scripts\\python.exe -m unittest discover -s DefultCredit/tests -v

Тесты не ходят в сеть: используется демо-макросрез и небольшие
Монте-Карло прогоны (100 путей), чтобы набор проходил быстро.
"""

from __future__ import annotations

import unittest

from DefultCredit.optimizer import ai
from DefultCredit.optimizer.engine import (
    _histogram,
    _percentile,
    _simulate_standard,
    _stress_tests,
    run_optimization,
)
from DefultCredit.optimizer.instruments import (
    build_assets,
    portfolio_expected_return,
    portfolio_liquidity,
    portfolio_volatility,
    scenario_templates,
)
from DefultCredit.optimizer.market_data import _parse_moex_board, default_macro
from DefultCredit.optimizer.models import (
    Distribution,
    ExistingMortgage,
    IISProfile,
    LiquidityNeed,
    OptimizeOptions,
    OptimizeRequest,
    RiskTolerance,
    UserProfile,
)
from DefultCredit.optimizer.taxes import (
    annuity_payment,
    cashflow_irr,
    cashflow_npv,
    coupon_tax,
    deposit_interest_tax,
    iis_deduction,
    loan_remaining_balance,
    loan_total_interest,
    progressive_tax,
    property_deduction,
    rent_tax,
)


def make_profile(**overrides) -> UserProfile:
    values = {
        "capital": 500_000,
        "monthly": 20_000,
        "horizon_months": 60,
        "risk_tolerance": RiskTolerance.moderate,
        "liquidity_need": LiquidityNeed.medium,
        "goal_amount": 1_500_000,
        "monthly_expenses": 50_000,
        "emergency_fund_months": 6,
    }
    values.update(overrides)
    return UserProfile(**values)


def make_options(**overrides) -> OptimizeOptions:
    values = {
        "monte_carlo_paths": 100,
        "distribution": Distribution.normal,
        "seed": 42,
        "max_scenarios": 10,
        "run_stress_tests": True,
    }
    values.update(overrides)
    return OptimizeOptions(**values)


class TaxTests(unittest.TestCase):
    def test_progressive_tax_brackets(self) -> None:
        self.assertEqual(progressive_tax(0), 0.0)
        self.assertAlmostEqual(progressive_tax(1_000_000), 130_000.0)
        # 2,4 млн × 13% + 0,6 млн × 15% = 312 000 + 90 000.
        self.assertAlmostEqual(progressive_tax(3_000_000), 402_000.0)
        # Свыше 50 млн добавляется ставка 22%.
        self.assertGreater(progressive_tax(60_000_000), progressive_tax(50_000_000))

    def test_deposit_interest_tax_threshold(self) -> None:
        # Порог: ключевая ставка × 1 млн. При 16% это 160 000 ₽ процентов.
        self.assertEqual(deposit_interest_tax(150_000, 0.16), 0.0)
        self.assertAlmostEqual(deposit_interest_tax(200_000, 0.16), 40_000 * 0.13)
        self.assertEqual(deposit_interest_tax(0, 0.16), 0.0)

    def test_coupon_and_rent_tax(self) -> None:
        self.assertAlmostEqual(coupon_tax(100_000), 13_000.0)
        self.assertAlmostEqual(rent_tax(100_000), 13_000.0)
        self.assertAlmostEqual(rent_tax(100_000, self_employed=True), 4_000.0)

    def test_iis_deduction_limits(self) -> None:
        self.assertEqual(iis_deduction(100_000, "none"), 0.0)
        self.assertAlmostEqual(iis_deduction(100_000, "A"), 13_000.0)
        self.assertAlmostEqual(iis_deduction(400_000, "A"), 52_000.0)
        # Взнос выше лимита не увеличивает вычет.
        self.assertAlmostEqual(iis_deduction(1_000_000, "A"), 52_000.0)
        # Вычет не больше уплаченного НДФЛ.
        self.assertAlmostEqual(iis_deduction(400_000, "A", tax_paid=10_000), 10_000.0)
        # Тип B освобождает доход, но не даёт возврат со взносов.
        self.assertEqual(iis_deduction(400_000, "B"), 0.0)

    def test_property_deduction_limits(self) -> None:
        # 2 млн цена + 3 млн процентов, максимум 13%.
        self.assertAlmostEqual(property_deduction(2_000_000), 260_000.0)
        self.assertAlmostEqual(property_deduction(5_000_000, 5_000_000), 650_000.0)

    def test_annuity_and_balance(self) -> None:
        payment = annuity_payment(1_000_000, 0.12, 12)
        self.assertAlmostEqual(payment, 88_848.79, places=2)
        self.assertAlmostEqual(
            loan_remaining_balance(1_000_000, 0.12, 12, 0), 1_000_000.0, places=2
        )
        self.assertAlmostEqual(
            loan_remaining_balance(1_000_000, 0.12, 12, 12), 0.0, places=2
        )
        self.assertGreater(loan_total_interest(1_000_000, 0.12, 12), 0.0)
        self.assertEqual(annuity_payment(0, 0.12, 12), 0.0)

    def test_cashflow_npv_and_irr(self) -> None:
        # Вложили 1 000, через год получили 1 100 — IRR около 10%.
        irr = cashflow_irr(1_000, 0, 12, 1_100)
        self.assertIsNotNone(irr)
        self.assertAlmostEqual(float(irr), 0.10, places=3)
        npv = cashflow_npv(0.10, 1_000, 0, 12, 1_100)
        self.assertAlmostEqual(npv, 0.0, places=4)
        self.assertLess(cashflow_npv(0.20, 1_000, 0, 12, 1_100), 0.0)


class AssetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.macro = default_macro()
        self.assets = build_assets(self.macro)

    def test_assets_catalog(self) -> None:
        expected = {
            "cash", "savings", "deposit", "ofz_short",
            "ofz_long", "corporate", "municipal", "real_estate",
        }
        self.assertEqual(set(self.assets), expected)
        for asset in self.assets.values():
            self.assertGreaterEqual(asset.expected_return, 0.0)
            self.assertGreaterEqual(asset.volatility, 0.0)
            self.assertGreaterEqual(asset.liquidity, 0.0)
            self.assertLessEqual(asset.liquidity, 1.0)
            self.assertIn(asset.tax_type, {"interest", "coupon", "rent", "capital_gain"})

    def test_scenario_templates_cover_all_levels(self) -> None:
        scenarios = scenario_templates(
            make_profile(), self.macro, self.assets, max_scenarios=18
        )
        self.assertGreaterEqual(len(scenarios), 10)
        self.assertLessEqual(len(scenarios), 18)
        levels = {scenario.risk_level.value for scenario in scenarios}
        self.assertEqual(levels, {"low", "medium", "high"})
        ids = [scenario.id for scenario in scenarios]
        self.assertEqual(len(ids), len(set(ids)))
        for scenario in scenarios:
            self.assertAlmostEqual(sum(scenario.weights.values()), 1.0, places=6)
            self.assertTrue(all(weight > 0 for weight in scenario.weights.values()))
            self.assertTrue(set(scenario.weights).issubset(self.assets))
            self.assertIsInstance(scenario.tags, list)

    def test_high_liquidity_need_is_enforced(self) -> None:
        profile = make_profile(liquidity_need=LiquidityNeed.high)
        scenarios = scenario_templates(profile, self.macro, self.assets, max_scenarios=18)
        self.assertTrue(scenarios)
        liquid_keys = {"cash", "savings", "deposit", "ofz_short"}
        for scenario in scenarios:
            liquid = sum(
                weight for key, weight in scenario.weights.items()
                if key in liquid_keys
            )
            self.assertGreaterEqual(liquid, 0.30 - 1e-6)

    def test_small_capital_affordability(self) -> None:
        profile = make_profile(capital=10_000, monthly=5_000)
        scenarios = scenario_templates(profile, self.macro, self.assets, max_scenarios=18)
        self.assertTrue(scenarios)
        # Недвижимость недоступна при таком капитале.
        for scenario in scenarios:
            self.assertNotIn("real_estate", scenario.weights)

    def test_mortgage_scenarios_require_consent(self) -> None:
        without = scenario_templates(make_profile(), self.macro, self.assets, 18)
        self.assertNotIn("high_mortgage", {scenario.id for scenario in without})

        consent = make_profile(
            capital=1_000_000,
            credit_willingness=True,
            credit_type="mortgage",
        )
        with_mortgage = scenario_templates(consent, self.macro, self.assets, 18)
        self.assertIn("high_mortgage", {scenario.id for scenario in with_mortgage})

    def test_portfolio_metrics(self) -> None:
        weights = {"deposit": 0.5, "ofz_long": 0.3, "corporate": 0.2}
        expected = portfolio_expected_return(weights, self.assets)
        self.assertGreater(expected, 0.0)
        self.assertGreaterEqual(portfolio_volatility(weights, self.assets), 0.0)
        liquidity = portfolio_liquidity(weights, self.assets)
        self.assertGreater(liquidity, 0.0)
        self.assertLess(liquidity, 1.0)


class MonteCarloTest(unittest.TestCase):
    def setUp(self) -> None:
        self.macro = default_macro()
        self.assets = build_assets(self.macro)
        self.profile = make_profile()
        self.scenarios = scenario_templates(
            self.profile, self.macro, self.assets, max_scenarios=10
        )
        self.scenario = next(
            scenario for scenario in self.scenarios
            if scenario.risk_level.value == "medium"
        )

    def simulate(self, options: OptimizeOptions, **kwargs):
        return _simulate_standard(
            self.scenario, self.profile, self.macro, self.assets, options, **kwargs
        )

    def test_percentiles_are_ordered(self) -> None:
        result = self.simulate(make_options(), include_stress=False)
        mc = result["mc"]
        self.assertEqual(mc.paths, 100)
        self.assertLessEqual(mc.terminal_p5, mc.terminal_p25)
        self.assertLessEqual(mc.terminal_p25, mc.terminal_p50)
        self.assertLessEqual(mc.terminal_p50, mc.terminal_p75)
        self.assertLessEqual(mc.terminal_p75, mc.terminal_p95)
        self.assertGreaterEqual(mc.probability_goal, 0.0)
        self.assertLessEqual(mc.probability_goal, 1.0)
        self.assertGreaterEqual(mc.probability_loss, 0.0)
        self.assertLessEqual(mc.probability_loss, 1.0)
        self.assertEqual(len(mc.histogram), 20)
        self.assertGreaterEqual(len(mc.series), 2)
        self.assertLessEqual(len(mc.sample_paths), 50)
        self.assertAlmostEqual(
            mc.total_contributions,
            self.profile.capital + self.profile.monthly * self.profile.horizon_months,
        )

    def test_same_seed_is_deterministic(self) -> None:
        first = self.simulate(make_options(seed=123), include_stress=False)
        second = self.simulate(make_options(seed=123), include_stress=False)
        self.assertEqual(
            first["mc"].terminal_p50, second["mc"].terminal_p50
        )
        self.assertEqual(first["mc"].terminal_p5, second["mc"].terminal_p5)
        self.assertEqual(
            first["mc"].max_drawdown_median,
            second["mc"].max_drawdown_median,
        )

    def test_different_distributions_produce_valid_paths(self) -> None:
        for distribution in Distribution:
            result = self.simulate(
                make_options(distribution=distribution), include_stress=False
            )
            mc = result["mc"]
            self.assertEqual(mc.distribution, distribution.value)
            self.assertGreater(mc.terminal_p50, 0.0)

    def test_stress_tests_include_rate_shocks(self) -> None:
        result = self.simulate(make_options(), include_stress=True)
        stress = result["stress"]
        self.assertEqual(len(stress), 10)
        names = [item.scenario for item in stress]
        self.assertTrue(any("+100 bp" in name for name in names))
        self.assertTrue(any("−500 bp" in name for name in names))
        self.assertTrue(any("Инфляция" in name for name in names))
        self.assertTrue(any("Недвижимость" in name for name in names))
        for item in stress:
            self.assertGreater(item.terminal_p50, 0.0)
            self.assertLessEqual(item.impact_p50, 5.0)

    def test_stress_impacts_are_negative_for_adverse_shocks(self) -> None:
        stress = _stress_tests(
            self.scenario,
            self.profile,
            self.macro,
            self.assets,
            base_return=0.15,
            volatility=0.10,
            years=5.0,
        )
        inflation = next(item for item in stress if "Инфляция" in item.scenario)
        self.assertLess(inflation.impact_p50, 0.0)
        tax = next(item for item in stress if "Налоговый" in item.scenario)
        self.assertLess(tax.impact_p50, 0.0)

    def test_histogram_and_percentile_helpers(self) -> None:
        values = [float(value) for value in range(1, 101)]
        self.assertAlmostEqual(_percentile(values, 0.5), 50.0, delta=1.0)
        self.assertAlmostEqual(_percentile(values, 0.0), 1.0)
        self.assertAlmostEqual(_percentile(values, 1.0), 100.0)
        bins = _histogram(values, bins=10)
        self.assertEqual(len(bins), 10)
        self.assertEqual(sum(item["count"] for item in bins), 100)


class EngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.request = OptimizeRequest(
            profile=make_profile(),
            options=make_options(),
        )
        cls.result = run_optimization(cls.request)

    def test_response_structure(self) -> None:
        result = self.result
        self.assertEqual(set(result.risk_profiles), {"low", "medium", "high"})
        for level, group in result.risk_profiles.items():
            self.assertEqual(group.level.value, level)
            self.assertTrue(group.options)
            self.assertIsNotNone(group.best_option_id)
            self.assertIn(group.best_option_id, {option.id for option in group.options})
            self.assertGreaterEqual(group.summary["p50"], group.summary["p5"])
            self.assertLessEqual(group.summary["p50"], group.summary["p95"])
        self.assertTrue(result.top_options)
        self.assertLessEqual(len(result.top_options), 10)

    def test_top_options_ranked_by_score(self) -> None:
        scores = [option.score for option in self.result.top_options]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(
            [option.rank for option in self.result.top_options],
            list(range(1, len(self.result.top_options) + 1)),
        )
        for option in self.result.top_options:
            self.assertIn(option.risk_level.value, {"low", "medium", "high"})
            self.assertAlmostEqual(
                sum(item.weight for item in option.allocation), 1.0, places=6
            )
            self.assertGreaterEqual(option.taxes.effective_rate, 0.0)
            self.assertGreaterEqual(option.fees.effective_rate, 0.0)
            self.assertGreaterEqual(option.liquidity, 0.0)
            self.assertLessEqual(option.liquidity, 1.0)
            self.assertGreaterEqual(option.probability_loss, 0.0)
            self.assertLessEqual(option.probability_loss, 1.0)

    def test_ai_context_and_template(self) -> None:
        self.assertTrue(self.result.context_id.startswith("ctx_"))
        self.assertEqual(self.result.ai_template.generated_by, "template")
        context = ai.load_context(self.result.context_id)
        self.assertIsNotNone(context)
        assert context is not None
        self.assertEqual(set(context["risk_profiles"]), {"low", "medium", "high"})
        self.assertEqual(context["meta"]["currency"], "RUB")
        violations = ai.validate_numbers(self.result.ai_template.summary, context)
        self.assertEqual(violations, [])

    def test_comparisons_and_warnings(self) -> None:
        comparisons = self.result.comparisons
        self.assertIsNotNone(comparisons.rent_vs_buy)
        rent = comparisons.rent_vs_buy
        assert rent is not None
        self.assertIn(rent.better_option, {"Аренда", "Покупка"})
        self.assertIn("property_value", rent.details)
        self.assertIsInstance(self.result.warnings, list)

    def test_same_request_is_deterministic(self) -> None:
        second = run_optimization(self.request)
        self.assertEqual(
            [option.id for option in self.result.top_options],
            [option.id for option in second.top_options],
        )
        self.assertEqual(
            [option.monte_carlo.terminal_p50 for option in self.result.top_options],
            [option.monte_carlo.terminal_p50 for option in second.top_options],
        )

    def test_exclude_real_estate(self) -> None:
        request = OptimizeRequest(
            profile=make_profile(capital=2_000_000),
            options=make_options(include_real_estate=False),
        )
        result = run_optimization(request)
        options = [
            option
            for group in result.risk_profiles.values()
            for option in group.options
        ]
        self.assertTrue(options)
        for option in options:
            keys = {item.key for item in option.allocation}
            self.assertNotIn("real_estate", keys)

    def test_exclude_mortgage(self) -> None:
        profile = make_profile(
            capital=1_000_000,
            credit_willingness=True,
            credit_type="mortgage",
        )
        request = OptimizeRequest(
            profile=profile,
            options=make_options(include_mortgage=False),
        )
        result = run_optimization(request)
        options = [
            option
            for group in result.risk_profiles.values()
            for option in group.options
        ]
        names = {option.name for option in options}
        self.assertNotIn("Ипотечная недвижимость", names)

    def test_iis_and_mortgage_inputs(self) -> None:
        profile = make_profile(
            existing_mortgage=ExistingMortgage(
                balance=800_000,
                annual_rate=0.18,
                monthly_payment=20_000,
                remaining_months=60,
                property_value=4_000_000,
            ),
            iis=IISProfile(type="A", annual_contribution=100_000, years=5),
        )
        result = run_optimization(
            OptimizeRequest(profile=profile, options=make_options())
        )
        self.assertTrue(result.warnings)
        self.assertIsNotNone(result.comparisons.prepay_vs_invest)
        best = result.top_options[0]
        self.assertGreaterEqual(best.taxes.deductions, 0.0)


class AILayerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_optimization(
            OptimizeRequest(profile=make_profile(), options=make_options())
        )
        cls.context = ai.load_context(cls.result.context_id)
        assert cls.context is not None

    def test_validator_blocks_invented_numbers(self) -> None:
        violations = ai.validate_numbers(
            "Доходность составит 9876543 рубля и 77% годовых.", self.context
        )
        self.assertTrue(violations)

    def test_validator_accepts_context_numbers(self) -> None:
        text = "Капитал 500000 рублей, медианный результат 2 500 000 рублей."
        # 2,5 млн может отсутствовать в контексте — проверяем только капитал.
        violations = ai.validate_numbers("Капитал 500000 рублей.", self.context)
        self.assertEqual(violations, [])
        self.assertTrue(text)

    def test_template_explanation_is_complete(self) -> None:
        explanation = ai.template_explanation(self.context)
        self.assertEqual(explanation.generated_by, "template")
        self.assertTrue(explanation.summary)
        self.assertEqual(set(explanation.risk_profiles), {"low", "medium", "high"})
        self.assertGreaterEqual(len(explanation.steps), 3)
        self.assertTrue(explanation.why)
        self.assertTrue(explanation.risks)
        self.assertTrue(explanation.disclaimer)
        self.assertEqual(ai.validate_numbers(explanation.summary, self.context), [])

    def test_explain_uses_context(self) -> None:
        explanation = ai.explain(context_id=self.result.context_id, use_llm=False)
        self.assertEqual(explanation.generated_by, "template")

    def test_explain_without_context_fails(self) -> None:
        with self.assertRaises(ValueError):
            ai.explain(context_id="ctx_missing", use_llm=False)

    def test_chat_topics(self) -> None:
        cases = {
            "Что выбрать и почему?": "Лучший сценарий по совокупности",
            "Какие риски при высокой ставке?": "Ключевая ставка",
            "Как работают налоги и ИИС?": "ИИС",
            "Что лучше: вклад или ОФЗ?": "вкладам",
            "Что с ипотекой и арендой?": "Ипотечная ставка",
        }
        for question, marker in cases.items():
            response = ai.chat(
                context_id=self.result.context_id,
                question=question,
                use_llm=False,
            )
            self.assertEqual(response.generated_by, "template")
            self.assertIn(marker, response.answer)

    def test_chat_moderation(self) -> None:
        response = ai.chat(
            context_id=self.result.context_id,
            question="Как гарантированно заработать 100% без риска?",
            use_llm=False,
        )
        self.assertEqual(response.generated_by, "moderation")
        self.assertIn("не индивидуальная инвестиционная рекомендация", response.answer)

    def test_chat_empty_question_fails(self) -> None:
        with self.assertRaises(ValueError):
            ai.chat(context_id=self.result.context_id, question="   ", use_llm=False)

    def test_provider_status_without_keys(self) -> None:
        status = ai.provider_status()
        self.assertIn("provider", status)
        self.assertIn("llm_enabled", status)
        self.assertIn(
            status["provider"],
            {"template", "openai", "anthropic", "yandex", "gigachat"},
        )


class MarketDataTest(unittest.TestCase):
    def test_default_macro_has_sources_and_timestamps(self) -> None:
        macro = default_macro()
        for field in (
            "key_rate", "inflation_yoy", "inflation_expected", "deposit_rate",
            "mortgage_rate", "ofz_yield_10y", "corporate_yield", "municipal_yield",
        ):
            point = getattr(macro, field)
            self.assertTrue(point.source)
            self.assertTrue(point.updated_at)
            self.assertIsInstance(point.is_fallback, bool)
        self.assertTrue(macro.ofz_curve)
        self.assertTrue(macro.data_sources)
        self.assertTrue(macro.fetched_at)

    def test_moex_parser_pairs_rows_by_index(self) -> None:
        payload = {
            "securities": {
                "columns": ["SECID", "SHORTNAME"],
                "data": [
                    ["SU26238RMFS4", "ОФЗ 26238"],
                    ["RU000A101234", "КорпСтрой 001P"],
                ],
            },
            "marketdata": {
                "columns": ["BOARDID", "SECID", "YIELD"],
                "data": [
                    ["TQOB", "SU26238RMFS4", 13.5],
                    ["TQCB", "RU000A101234", 16.2],
                ],
            },
        }
        ofz, corporate = _parse_moex_board(payload)
        self.assertEqual(ofz, [0.135])
        self.assertEqual(corporate, [0.162])

    def test_moex_parser_ignores_invalid_yields(self) -> None:
        payload = {
            "securities": {
                "columns": ["SECID", "SHORTNAME"],
                "data": [["SU26238RMFS4", "ОФЗ 26238"]],
            },
            "marketdata": {
                "columns": ["BOARDID", "SECID", "YIELD"],
                "data": [["TQOB", "SU26238RMFS4", None]],
            },
        }
        self.assertEqual(_parse_moex_board(payload), ([], []))
        self.assertEqual(_parse_moex_board(None), ([], []))


if __name__ == "__main__":
    unittest.main()
