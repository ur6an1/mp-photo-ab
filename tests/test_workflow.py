"""Seller-visible workflow and invalid-inference regression tests."""
import copy
import csv
from datetime import date, timedelta
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from data_io import InputError, validate_hypotheses
from experiment import analyze_data, build_plan

SKILL = Path(__file__).resolve().parents[1]


def hypotheses():
    return validate_hypotheses([
        {"id": name, "variable": variable, "change": "Изменить только фон" if name == "B" else "Проверить одну переменную",
         "rationale": "Учебная гипотеза; данные конкурентов отсутствуют", "target_metric": "ctr",
         "ice": {"impact": 3, "confidence": 2, "ease": 4},
         "risks": ["Искажение товара", "Правила площадки"], "selected": name == "B"}
        for name, variable in zip("BCDE", ("background", "composition", "light", "badge"))])


def settings():
    return {"mode": "randomized", "daily_impressions": 10000, "allocation": [.5, .5],
            "mde_ctr": .3, "mde_orders": .5, "stability_confirmed": True,
            "non_promo_confirmed": True, "product_review_confirmed": True,
            "metrics_contract_confirmed": True, "independent_units_confirmed": True,
            "srm_assignment_units_confirmed": True,
            "native_test_confirmed": True, "native_test_evidence": "Синтетический тест, не реальный кабинет"}


def baseline_brief():
    return {"marketplace": "Wildberries", "baseline": {"days": 14, "impressions": 140000,
            "clicks": 14000, "cart": 5000, "orders": 1400}}


def daily(plan, orders_b=100, days=None):
    rows = []
    for day in range(days or plan["days"]):
        for variant in plan["variants"]:
            rows.append({"date": (date.fromisoformat(plan["start"]) + timedelta(days=day)).isoformat(),
                         "variant": variant, "impressions": 5000, "clicks": 500, "cart": 200,
                         "orders": 50 if variant == "control" else orders_b,
                         "advertising_changed": False, "out_of_stock": False, "price_changed": False})
    return rows


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.plan = build_plan(baseline_brief(), hypotheses(), settings(), date(2026, 9, 1))
        self.as_of = date.fromisoformat(self.plan["end"]) + timedelta(days=1)

    def test_primary_orders_not_ctr_selects_winner(self):
        rows = daily(self.plan, orders_b=20)
        for row in rows:
            if row["variant"] == "B":
                row["clicks"] = 800
        result = analyze_data(self.plan, rows, self.as_of)
        self.assertEqual(result["winner"], "control")
        self.assertEqual(result["decision"], "откатить")

    def test_winner_equivalence_and_insufficient(self):
        self.assertEqual(analyze_data(self.plan, daily(self.plan), self.as_of)["winner"], "B")
        self.assertEqual(analyze_data(self.plan, daily(self.plan, orders_b=50), self.as_of)["verdict_type"], "equivalent")
        early = analyze_data(self.plan, daily(self.plan, days=3), date(2026, 9, 4))
        self.assertEqual(early["verdict_type"], "insufficient")
        self.assertIsNone(early["winner"])
        self.assertEqual(len(early["novelty"]), 6)

    def test_srm_and_anomaly_block_large_uplift(self):
        for kind in ("srm", "out_of_stock", "advertising_changed", "price_changed"):
            rows = daily(self.plan)
            if kind == "srm":
                for row in rows:
                    if row["variant"] == "B":
                        row["impressions"] = 7000
            else:
                rows[0][kind] = True
            result = analyze_data(self.plan, rows, self.as_of)
            self.assertEqual(result["verdict_type"], "insufficient")
            self.assertTrue(result["blockers"])
            self.assertIsNone(result["remaining_days"])

    def test_missing_future_days_not_accepted(self):
        with self.assertRaises(InputError):
            analyze_data(self.plan, daily(self.plan)[1:], self.as_of)
        with self.assertRaises(InputError):
            analyze_data(self.plan, daily(self.plan), date(2026, 9, 3))

    def test_wb_third_arm_and_unknown_confirmations_rejected(self):
        variants = hypotheses()
        variants[1]["selected"] = True
        with self.assertRaises(InputError):
            build_plan(baseline_brief(), variants, settings(), date(2026, 9, 1))
        config = settings()
        config["independent_units_confirmed"] = False
        with self.assertRaises(InputError):
            build_plan(baseline_brief(), hypotheses(), config, date(2026, 9, 1))

    def test_closed_underpowered_test_needs_full_new_sample(self):
        plan = copy.deepcopy(self.plan)
        plan["per_arm_target"] = [1000000, 1000000]
        result = analyze_data(plan, daily(plan), self.as_of)
        self.assertIsNone(result["remaining_impressions"])
        self.assertIsNone(result["remaining_days"])
        self.assertIn("полной", result["verdict"])

    def test_huge_sample_horizon_fails_before_date_arithmetic(self):
        config = {**settings(), "daily_impressions": 1, "mde_ctr": .0001, "mde_orders": .0001}
        with self.assertRaisesRegex(InputError, "10 лет"):
            build_plan(baseline_brief(), hypotheses(), config, date(2026, 9, 1))

    def test_sequential_does_not_claim_causality(self):
        config = {**settings(), "mode": "sequential"}
        plan = build_plan(baseline_brief(), hypotheses(), config, date(2026, 9, 1))
        rows = [row for row in daily(plan) if row["variant"] == plan["variants"][((date.fromisoformat(row["date"]) - date(2026, 9, 1)).days // 7) % 2]]
        result = analyze_data(plan, rows, date.fromisoformat(plan["end"]) + timedelta(days=1))
        self.assertIsNone(result["srm"])
        self.assertEqual(result["verdict_type"], "insufficient")

    def test_complete_local_cli_without_generation_expense(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("control.jpg", "reference.jpg", "candidate.jpg"):
                Image.new("RGB", (900, 1200), (220, 220, 220)).save(root / name)
            brief = json.loads((SKILL / "assets/samples/brief.json").read_text())
            (root / "brief-input.json").write_text(json.dumps(brief))
            (root / "hypotheses.json").write_text(json.dumps(hypotheses()))
            (root / "settings.json").write_text(json.dumps(settings()))
            exp = root / "experiments/DEMO-001/2026-09-01"

            def run(script, *arguments, expected=0):
                output = subprocess.run([sys.executable, str(SKILL / "scripts" / script), *map(str, arguments)],
                                        capture_output=True, text=True)
                self.assertEqual(output.returncode, expected, output.stdout + output.stderr)
                return output

            run("experiment.py", "brief", "--input", root / "brief-input.json", "--root", root / "experiments", "--date", "2026-09-01")
            run("experiment.py", "hypotheses", "--experiment", exp, "--input", root / "hypotheses.json")
            output = run("generate.py", "--experiment", exp, "--dry-run")
            self.assertIn("Режим без расходов", output.stdout)
            self.assertFalse((exp / "generation.json").exists())
            run("thumbnail_preview.py", "--control", root / "control.jpg", "--variants", root / "candidate.jpg", "--output", exp / "thumbnail-preview.jpg")
            run("experiment.py", "plan", "--experiment", exp, "--settings", root / "settings.json", "--start", "2026-09-01")
            plan = json.loads((exp / "plan.json").read_text())
            interim_rows = daily(plan, days=3)
            with (root / "interim.csv").open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=interim_rows[0])
                writer.writeheader()
                writer.writerows(interim_rows)
            run("experiment.py", "analyze", "--experiment", exp, "--input", root / "interim.csv", "--as-of", "2026-09-04", "--output", exp / "interim.json")
            self.assertFalse((exp / "daily-metrics.csv").exists())
            rows = daily(plan)
            with (root / "daily.csv").open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=rows[0])
                writer.writeheader()
                writer.writerows(rows)
            run("experiment.py", "analyze", "--experiment", exp, "--input", root / "daily.csv", "--as-of", date.fromisoformat(plan["end"]) + timedelta(days=1))
            run("experiment.py", "report", "--experiment", exp, "--next-test", "Проверить масштаб товара, не меняя фон")
            self.assertIn("победитель B", (exp / "report.md").read_text())
            self.assertIn("Товары для дома", (root / "experiments/learnings.md").read_text())
            with (exp / "daily-metrics.csv").open() as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), len(rows))
            snapshot = exp / "analysis-data.csv"
            snapshot.write_text(snapshot.read_text().replace(",5000,500,200,50,", ",5000,500,200,49,", 1))
            rejected = run("experiment.py", "report", "--experiment", exp, "--output", exp / "tampered.md", "--next-test", "Тест", expected=2)
            self.assertIn("Снимок данных изменился", rejected.stderr)
            run("experiment.py", "plan", "--experiment", exp, "--settings", root / "settings.json", "--start", "2026-09-01", expected=2)


if __name__ == "__main__":
    unittest.main()
