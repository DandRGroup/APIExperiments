import unittest
from unittest.mock import patch

from monthly_usage import estimate_monthly_usage


class TestMonthlyUsage(unittest.TestCase):
    def test_estimate_monthly_usage_filters_adjustments_and_aggregates(self) -> None:
        page_one = {
            "result": {
                "items": [
                    {
                        "date": "10/01/2026 10:00",
                        "quantity": 5,
                        "direction": "Out",
                        "label": "Sales Order SO-100",
                    },
                    {
                        "date": "15/01/2026 09:30",
                        "quantity": 3,
                        "direction": "Out",
                        "label": "Stock Adjustment - Count Correction",
                    },
                    {
                        "date": "02/02/2026 11:00",
                        "quantity": 8,
                        "direction": "Out",
                        "description": "Job Issue",
                    },
                    {
                        "date": "20/02/2026 11:00",
                        "quantity": 100,
                        "direction": "In",
                        "label": "Supplier Receipt",
                    },
                ]
            }
        }
        page_two = {
            "result": {
                "items": [
                    {
                        "date": "05/03/2026 08:10",
                        "quantity": 4,
                        "direction": "Out",
                        "reason": "stock adjustment manual fix",
                    },
                    {
                        "date": "07/03/2026 13:20",
                        "quantity": 7,
                        "direction": "Out",
                        "reference": "SO-200",
                    },
                ]
            }
        }
        page_three = {"result": {"items": []}}

        with patch(
            "monthly_usage.endpoints.get_stock_movements",
            side_effect=[page_one, page_two, page_three],
        ):
            result = estimate_monthly_usage("CP", 123)

        self.assertEqual(result.total_movements_scanned, 6)
        self.assertEqual(result.included_movements, 3)
        self.assertEqual(result.excluded_adjustments, 2)
        self.assertEqual(
            result.monthly_usage,
            {
                "2026-01": 5.0,
                "2026-02": 8.0,
                "2026-03": 7.0,
            },
        )
        self.assertAlmostEqual(result.avg_monthly_usage_full_span, 20.0 / 3.0, places=6)

    def test_estimate_monthly_usage_uses_full_calendar_span(self) -> None:
        page_one = {
            "result": {
                "items": [
                    {
                        "date": "01/01/2026 00:01",
                        "quantity": 10,
                        "direction": "Out",
                        "label": "SO-1",
                    },
                    {
                        "date": "20/03/2026 13:00",
                        "quantity": 20,
                        "direction": "Out",
                        "label": "SO-2",
                    },
                ]
            }
        }
        page_two = {"result": {"items": []}}

        with patch(
            "monthly_usage.endpoints.get_stock_movements",
            side_effect=[page_one, page_two],
        ):
            result = estimate_monthly_usage("DR", 999)

        self.assertEqual(result.monthly_usage, {"2026-01": 10.0, "2026-03": 20.0})
        # Jan to Mar inclusive = 3 months, so average should be 30 / 3.
        self.assertAlmostEqual(result.avg_monthly_usage_full_span, 10.0, places=6)


if __name__ == "__main__":
    unittest.main()
