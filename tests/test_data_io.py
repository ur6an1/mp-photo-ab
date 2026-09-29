"""Behavioral validation of experiment imports."""
import csv
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from data_io import InputError, read_daily, validate_brief, validate_counts


class InputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.row = {"date": "2026-09-01", "variant": "control", "impressions": 100,
                    "clicks": 10, "cart": 3, "orders": 2, "advertising_changed": "false",
                    "out_of_stock": "false", "price_changed": "false"}

    def csv(self, rows):
        path = self.root / "daily.csv"
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=self.row)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_csv_xlsx_same_contract(self):
        from openpyxl import Workbook
        csv_rows = read_daily(self.csv([self.row]))
        workbook = Workbook()
        workbook.active.append(list(self.row))
        workbook.active.append(list(self.row.values()))
        path = self.root / "daily.xlsx"
        workbook.save(path)
        self.assertEqual(csv_rows, read_daily(path))

    def test_invalid_counts_and_missing_flags_not_zero_filled(self):
        for field, value in (("orders", -1), ("impressions", "NaN"), ("clicks", 101),
                             ("orders", 11), ("cart", ""), ("orders", 1.2), ("price_changed", "")):
            with self.subTest(field=field, value=value), self.assertRaises(InputError):
                read_daily(self.csv([{**self.row, field: value}]))

    def test_duplicates_and_empty_rejected(self):
        for rows in ([], [self.row, self.row]):
            with self.assertRaises(InputError):
                read_daily(self.csv(rows))

    def test_csv_duplicate_headers_and_extra_cells_rejected(self):
        path = self.root / "ambiguous.csv"
        for text in (
            ",".join([*self.row, "orders"]) + "\n" + ",".join([*map(str, self.row.values()), "9"]),
            ",".join(self.row) + "\n" + ",".join([*map(str, self.row.values()), "9"]),
        ):
            path.write_text(text)
            with self.assertRaises(InputError):
                read_daily(path)

    def test_order_need_not_go_through_cart(self):
        self.assertEqual(validate_counts({"impressions": 100, "clicks": 10, "cart": 0, "orders": 2})["orders"], 2)

    def test_xlsx_formula_not_silently_cached_or_executed(self):
        from openpyxl import Workbook
        workbook = Workbook()
        workbook.active.append(list(self.row))
        values = list(self.row.values())
        values[2] = "=10*10"
        workbook.active.append(values)
        path = self.root / "formula.xlsx"
        workbook.save(path)
        with self.assertRaises(InputError):
            read_daily(path)

    def test_missing_reference_and_path_traversal(self):
        brief = {"sku": "../escape", "marketplace": "Wildberries", "category": "Техника",
                 "audience": "Покупатели", "price_segment": "Средний", "usps": ["Факт"]}
        with self.assertRaises(InputError):
            validate_brief(brief, self.root)
        brief["sku"] = "SAFE"
        with self.assertRaises(InputError):
            validate_brief(brief, self.root)


if __name__ == "__main__":
    unittest.main()
