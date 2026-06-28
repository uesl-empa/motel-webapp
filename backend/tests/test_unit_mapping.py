import unittest
from unittest.mock import patch

import pandas as pd

from backend.src.utils.technology_attributes import get_attribute_value


class UnitMappingTests(unittest.TestCase):
    def test_maps_unit_label_and_currency_in_exported_value(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "attr_type": "https://example.org/SomeAttribute",
                    "value": 25,
                    "unit_label": "KiloW",
                    "att_currency": "https://example.org/currency/EUR",
                }
            ]
        )

        result = get_attribute_value(df, "SomeAttribute")

        self.assertEqual(result, "25 CHF/kW")

    def test_maps_standalone_unit_label_in_exported_value(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "attr_type": "https://example.org/SomeAttribute",
                    "value": 30,
                    "unit_label": "YR",
                    "att_currency": pd.NA,
                }
            ]
        )

        result = get_attribute_value(df, "SomeAttribute")

        self.assertEqual(result, "30 a")

    def test_maps_currency_and_unit_before_concatenation(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "attr_type": "https://example.org/SomeAttribute",
                    "value": 12,
                    "unit_label": "KiloW-HR",
                    "att_currency": "https://example.org/currency/EUR",
                }
            ]
        )

        with patch.dict(
            "backend.src.utils.technology_attributes.UNIT_MAPPING",
            {"EUR": "CHF", "KiloW-HR": "kWh"},
            clear=True,
        ):
            result = get_attribute_value(df, "SomeAttribute")

        self.assertEqual(result, "12 CHF/kWh")


if __name__ == "__main__":
    unittest.main()
