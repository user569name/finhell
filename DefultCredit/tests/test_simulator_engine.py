"""Тесты движка, облигаций, Монте-Карло и последовательности плана.

Запуск из корня проекта:
    .\\myvenv\\Scripts\\python.exe -m unittest discover -s DefultCredit/tests -v
"""

from __future__ import annotations

import unittest

from DefultCredit.simulator_engine import (
    DEFAULT_RISK_FACTORS,
    INSTRUMENTS,
    Debt,
    SimulationParams,
    build_allocation,
    effective_risk,
    effective_volatility,
)
from DefultCredit.simulator_plan import (
    analyze_bond,
    build_debt_advice,
    run_simulation,
)


def make_params(**overrides) -> SimulationParams:
    values = {
        "initial_capital": 500_000,
        "monthly_contribution": 30_000,
        "horizon_months": 60,
        "risk_profile": "balanced",
        "inflation_rate": 0.08,
        "monthly_expenses": 50_000,
        "emergency_fund_months": 6,
        "monte_carlo_paths": 100,
        "seed": 42,
    }
    values.update(overrides)
    return SimulationParams(**values)


class AllocationTests(unittest.TestCase):
    def test_shares_sum_to_one_and_match_capital(self) -> None:
        result = run_simulation(make_params())
        items = result["allocation"]

        self.assertTrue(items)
        self.assertAlmostEqual(sum(item["share"] for item in items), 1.0, places=3)
        self.assertAlmostEqual(
            sum(item["initial_amount"] for item in items),
            result["summary"]["investable_initial"],
            delta=1.0,
        )
        self.assertTrue(all(item["share"] > 0 for item in items))

    def test_short_horizon_excludes_risky_assets(self) -> None:
        result = run_simulation(
            make_params(
                initial_capital=100_000,
                monthly_contribution=10_000,
                horizon_months=6,
                monthly_expenses=0,
            )
        )
        keys = {item["key"] for item in result["allocation"]}

        self.assertTrue(keys)
        self.assertLessEqual(keys, {"cash", "deposit", "ofz"})

    def test_long_aggressive_horizon_includes_growth_assets(self) -> None:
        result = run_simulation(
            make_params(
                initial_capital=2_000_000,
                monthly_contribution=50_000,
                horizon_months=120,
                risk_profile="aggressive",
                monthly_expenses=0,
                include_crypto=True,
            )
        )
        keys = {item["key"] for item in result["allocation"]}
        crypto = next(
            item for item in result["allocation"] if item["key"] == "crypto"
        )

        self.assertIn("stocks", keys)
        self.assertIn("crypto", keys)
        self.assertLessEqual(crypto["share"], 0.08 + 1e-6)

    def test_bond_ladder_stays_inside_horizon(self) -> None:
        result = run_simulation(make_params())
        ladder = result["bond_ladder"]

        self.assertTrue(ladder)
        self.assertTrue(
            all(0 < row["maturity_months"] <= 60 for row in ladder)
        )
        self.assertTrue(
            all(row["instrument"] in {"ofz", "corporate_bonds"} for row in ladder)
        )
        self.assertLessEqual(
            len(ladder),
            4 * 2,
            "Не больше четырёх ступеней на каждый облигационный инструмент.",
        )


class RiskTests(unittest.TestCase):
    def test_risk_factors_raise_volatility(self) -> None:
        low = {key: 0.0 for key in DEFAULT_RISK_FACTORS}
        high = {key: 1.0 for key in DEFAULT_RISK_FACTORS}

        for key in ("corporate_bonds", "stocks", "gold"):
            with self.subTest(instrument=key):
                low_vol = effective_volatility(INSTRUMENTS[key], low)
                high_vol = effective_volatility(INSTRUMENTS[key], high)
                self.assertGreater(high_vol, low_vol)

    def test_asset_override_raises_risk_and_volatility(self) -> None:
        base_risk = effective_risk(
            INSTRUMENTS["stocks"], DEFAULT_RISK_FACTORS
        )
        base_vol = effective_volatility(
            INSTRUMENTS["stocks"], DEFAULT_RISK_FACTORS
        )
        override_risk = effective_risk(
            INSTRUMENTS["stocks"], DEFAULT_RISK_FACTORS, override=0.95
        )
        override_vol = effective_volatility(
            INSTRUMENTS["stocks"], DEFAULT_RISK_FACTORS, override=0.95
        )

        self.assertGreater(override_risk, base_risk)
        self.assertGreater(override_vol, base_vol)
        self.assertEqual(
            effective_risk(INSTRUMENTS["stocks"], DEFAULT_RISK_FACTORS, 2.0),
            1.0,
        )

    def test_high_risk_allocation_is_not_less_volatile(self) -> None:
        low = {key: 0.0 for key in DEFAULT_RISK_FACTORS}
        high = {key: 1.0 for key in DEFAULT_RISK_FACTORS}
        low_alloc = build_allocation(
            make_params(risk_factors=low), 500_000
        )
        high_alloc = build_allocation(
            make_params(risk_factors=high), 500_000
        )

        self.assertGreaterEqual(
            high_alloc["volatility"], low_alloc["volatility"]
        )
        self.assertGreaterEqual(high_alloc["risk"], low_alloc["risk"])


class BondTests(unittest.TestCase):
    def test_par_bond_yield_equals_coupon(self) -> None:
        result = analyze_bond(1000, 1000, 0.12, 2, 5)

        self.assertAlmostEqual(result["ytm"], 0.12, places=3)
        self.assertAlmostEqual(result["current_yield"], 0.12, places=3)
        self.assertEqual(result["annual_coupon_income"], 120.0)
        self.assertEqual(result["total_coupons"], 600.0)

    def test_discount_and_premium_bonds(self) -> None:
        discount = analyze_bond(1000, 900, 0.10, 2, 5)
        premium = analyze_bond(1000, 1100, 0.10, 2, 5)

        self.assertGreater(discount["ytm"], 0.10)
        self.assertLess(premium["ytm"], 0.10)
        self.assertGreater(discount["profit"], premium["profit"])

    def test_duration_is_positive_and_below_maturity(self) -> None:
        result = analyze_bond(1000, 950, 0.12, 2, 5)

        self.assertGreater(result["macaulay_duration_years"], 0)
        self.assertLessEqual(result["macaulay_duration_years"], 5)
        self.assertLess(
            result["modified_duration"],
            result["macaulay_duration_years"],
        )
        self.assertAlmostEqual(
            result["modified_duration"],
            result["macaulay_duration_years"] / (1 + result["ytm"] / 2),
            places=3,
        )

    def test_reinvestment_increases_future_value(self) -> None:
        without = analyze_bond(1000, 950, 0.12, 2, 5, reinvest_rate=0.0)
        with_reinvest = analyze_bond(1000, 950, 0.12, 2, 5, reinvest_rate=0.08)

        self.assertAlmostEqual(
            without["future_value_reinvested"],
            without["total_payments"],
            places=2,
        )
        self.assertGreater(
            with_reinvest["future_value_reinvested"],
            without["future_value_reinvested"],
        )
        self.assertGreater(
            with_reinvest["profit_reinvested"],
            with_reinvest["profit"],
        )

    def test_invalid_bond_inputs_raise(self) -> None:
        with self.assertRaises(ValueError):
            analyze_bond(0, 1000, 0.12, 2, 5)
        with self.assertRaises(ValueError):
            analyze_bond(1000, 1000, -0.01, 2, 5)
        with self.assertRaises(ValueError):
            analyze_bond(1000, 1000, 0.12, 0, 5)
        with self.assertRaises(ValueError):
            analyze_bond(1000, 1000, 0.12, 2, 0)


class MonteCarloTests(unittest.TestCase):
    def test_percentiles_are_ordered(self) -> None:
        result = run_simulation(make_params(horizon_months=24))
        projection = result["projection"]

        self.assertLessEqual(
            projection["terminal_p10"], projection["terminal_p50"]
        )
        self.assertLessEqual(
            projection["terminal_p50"], projection["terminal_p90"]
        )
        self.assertGreaterEqual(projection["terminal_p10"], 0.0)
        self.assertGreaterEqual(projection["probability_loss"], 0.0)
        self.assertLessEqual(projection["probability_loss"], 1.0)

    def test_contributions_match_inputs(self) -> None:
        result = run_simulation(
            make_params(
                initial_capital=300_000,
                monthly_contribution=20_000,
                horizon_months=24,
                monthly_expenses=0,
            )
        )

        self.assertEqual(
            result["projection"]["total_contributions"],
            300_000 + 20_000 * 24,
        )
        self.assertEqual(len(result["projection"]["series"]), 25)

    def test_same_seed_is_reproducible(self) -> None:
        first = run_simulation(make_params(horizon_months=24))
        second = run_simulation(make_params(horizon_months=24))

        self.assertEqual(
            first["projection"]["terminal_p50"],
            second["projection"]["terminal_p50"],
        )
        self.assertEqual(
            first["projection"]["terminal_p10"],
            second["projection"]["terminal_p10"],
        )

    def test_goal_probability_is_reported(self) -> None:
        result = run_simulation(
            make_params(horizon_months=24, goal_amount=1_000_000)
        )

        probability = result["projection"]["probability_goal"]
        self.assertIsNotNone(probability)
        self.assertGreaterEqual(probability, 0.0)
        self.assertLessEqual(probability, 1.0)


class PlanTests(unittest.TestCase):
    def test_high_rate_debt_is_paid_before_investing(self) -> None:
        result = run_simulation(
            make_params(
                debts=[Debt("Карта", 400_000, 0.25, 20_000)],
            )
        )
        summary = result["summary"]

        self.assertEqual(summary["debt_payoff"], 400_000)
        self.assertEqual(summary["investable_initial"], 0.0)
        self.assertEqual(summary["reserve_initial"], 100_000)
        self.assertEqual(summary["reserve_months"], 7)
        self.assertGreater(summary["saved_interest"], 0)

        titles = [stage["title"] for stage in result["sequence"]]
        self.assertIn("Стартовый резерв", titles)
        self.assertIn("Погашение дорогих долгов", titles)
        self.assertIn("Пополнение резерва", titles)
        self.assertLess(
            titles.index("Стартовый резерв"),
            titles.index("Погашение дорогих долгов"),
        )
        self.assertLess(
            titles.index("Погашение дорогих долгов"),
            titles.index("Пополнение резерва"),
        )

        by_title = {stage["title"]: stage for stage in result["sequence"]}
        self.assertEqual(by_title["Стартовый резерв"]["amount"], 100_000)
        self.assertEqual(by_title["Пополнение резерва"]["amount"], 200_000)

    def test_low_rate_debt_is_not_paid_early(self) -> None:
        result = run_simulation(
            make_params(
                debts=[Debt("Ипотека", 400_000, 0.05, 20_000)],
            )
        )
        summary = result["summary"]

        self.assertEqual(summary["debt_payoff"], 0.0)
        self.assertEqual(summary["reserve_initial"], 300_000)
        self.assertEqual(summary["reserve_months"], 0)
        self.assertEqual(summary["investable_initial"], 200_000)

    def test_debt_payoff_prioritizes_highest_rate(self) -> None:
        params = make_params(
            debts=[
                Debt("Первый", 100_000, 0.30, 10_000),
                Debt("Второй", 100_000, 0.20, 10_000),
            ]
        )
        advice = build_debt_advice(
            params=params,
            high_debts=params.debts,
            payoff=150_000,
            threshold=0.17,
        )
        first, second = advice["items"]

        self.assertEqual(first["payoff_from_capital"], 100_000)
        self.assertEqual(second["payoff_from_capital"], 50_000)
        self.assertGreater(advice["saved_interest"], 0)

    def test_reserve_is_zero_without_monthly_expenses(self) -> None:
        result = run_simulation(
            make_params(monthly_expenses=0, initial_capital=200_000)
        )

        self.assertEqual(result["reserve"]["target"], 0.0)
        self.assertEqual(result["reserve"]["months_to_fill"], 0)
        self.assertEqual(result["summary"]["investable_initial"], 200_000)

    def test_sequence_always_ends_with_result(self) -> None:
        result = run_simulation(make_params(horizon_months=24))
        sequence = result["sequence"]

        self.assertGreaterEqual(len(sequence), 1)
        self.assertEqual(sequence[-1]["title"], "Результат")
        self.assertEqual(
            [stage["step"] for stage in sequence],
            list(range(1, len(sequence) + 1)),
        )

    def test_invalid_horizon_and_profile_raise(self) -> None:
        with self.assertRaises(ValueError):
            run_simulation(make_params(horizon_months=0))
        with self.assertRaises(ValueError):
            run_simulation(make_params(risk_profile="unknown"))


if __name__ == "__main__":
    unittest.main()
