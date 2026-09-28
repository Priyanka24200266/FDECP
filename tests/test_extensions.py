import os
import sys
import unittest
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("LAB_ALIAS", "testuser")
os.environ.setdefault("PROJECT_ENDPOINT", "https://example")
os.environ.setdefault("FOUNDRY_ENDPOINT", "https://example")
os.environ.setdefault("AOAI_ENDPOINT", "https://example")
os.environ.setdefault("SEARCH_ENDPOINT", "https://example")
os.environ.setdefault("STORAGE_ACCOUNT", "example")
sys.path.insert(0, str(Path(__file__).parents[1] / "backend"))

import analyzers
import validation
import verification
import store


class ExtensionTests(unittest.TestCase):
    def test_hire_invoice_is_classified(self):
        self.assertEqual(analyzers.classify_by_filename("hire-car-invoice.txt"), "hire_car_invoice")
        self.assertGreater(analyzers.HIRE_CAR_INVOICE["daily_rate"]["type"], "")

    def test_hire_period_before_loss_is_flagged(self):
        extracted = {
            "claim_form": {"date_of_loss": {"value": "2026-08-14"}},
            "hire_car_invoice": {
                "hire_start": {"value": "2026-08-12"},
                "hire_end": {"value": "2026-08-14"},
                "days": {"value": "3"},
            },
        }
        findings = validation.check_hire_car_period(extracted)
        self.assertEqual([item["code"] for item in findings], ["HIRE_PERIOD_BEFORE_LOSS"])

    def test_hire_period_after_repair_completion_is_flagged(self):
        extracted = {
            "hire_car_invoice": {
                "hire_start": {"value": "2026-08-15"},
                "hire_end": {"value": "2026-08-20"},
                "days": {"value": "6"},
            },
            "repair_estimate": {"repair_completion_date": {"value": "2026-08-18"}},
        }
        findings = validation.check_hire_car_period(extracted)
        self.assertEqual([item["code"] for item in findings], ["HIRE_PERIOD_AFTER_REPAIR"])

    def test_verification_only_routes_critical_low_confidence_fields(self):
        extracted = {
            "claim_form": {
                "policy_number": {"value": "P-1", "confidence": 0.4},
                "claimant_name": {"value": "A", "confidence": 0.2},
            },
            "repair_estimate": {"total_amount": {"value": "1,250.00", "confidence": 0.55}},
        }
        items = verification.build_verification_items(extracted)
        self.assertEqual([item["id"] for item in items], ["claim_form.policy_number", "repair_estimate.total_amount"])
        self.assertEqual(verification.build_verification_items({"claim_form": {"policy_number": {"value": "P-1", "confidence": 0.9}}}), [])

    def test_currency_threshold_is_decimal_exact(self):
        self.assertEqual(len(validation.check_authority_limit({"repair_estimate": {"total_amount": {"value": "5000.00"}}})), 0)
        self.assertEqual(len(validation.check_authority_limit({"repair_estimate": {"total_amount": {"value": "5000.01"}}})), 1)
        self.assertIsInstance(validation._as_decimal("$1,250.00"), Decimal)

    def test_duplicate_identity_requires_all_strong_fields(self):
        extracted = {
            "claim_form": {
                "policy_number": {"value": "CIP-MTR-884213"},
                "vin": {"value": "4T1C11AK8NU123456"},
                "date_of_loss": {"value": "2026-08-14"},
            }
        }
        self.assertEqual(
            store.duplicate_identity(extracted),
            ("cipmtr884213", "4t1c11ak8nu123456", "20260814"),
        )
        self.assertIsNone(store.duplicate_identity({"claim_form": {"vin": {"value": "VIN"}}}))


if __name__ == "__main__":
    unittest.main()
