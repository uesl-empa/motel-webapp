import unittest

import pandas as pd

from backend.src.services.technology_assembly_service import build_energy_carriers


class StubRepository:
    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df

    def get_energy_carriers(self, _energy_conv_id: str) -> pd.DataFrame:
        return self._df


class BuildEnergyCarriersTests(unittest.TestCase):
    def test_maps_carrier_ids_to_ehubx_fields(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "main_in_carrier": "https://digicities.info/proj/MOTEL/EC/electricity",
                    "main_out_carrier": "https://digicities.info/proj/MOTEL/EC/heat",
                    "in_flow": "https://digicities.info/proj/MOTEL/Flow/in_1",
                    "in_carrier": "https://digicities.info/proj/MOTEL/EC/electricity",
                    "in_value": 0.75,
                    "out_flow": pd.NA,
                    "out_carrier": pd.NA,
                    "out_value": pd.NA,
                },
                {
                    "main_in_carrier": "https://digicities.info/proj/MOTEL/EC/electricity",
                    "main_out_carrier": "https://digicities.info/proj/MOTEL/EC/heat",
                    "in_flow": pd.NA,
                    "in_carrier": pd.NA,
                    "in_value": pd.NA,
                    "out_flow": "https://digicities.info/proj/MOTEL/Flow/out_1",
                    "out_carrier": "https://digicities.info/proj/MOTEL/EC/heat",
                    "out_value": 0.9,
                },
            ]
        )

        repository = StubRepository(df)

        result = build_energy_carriers(repository, "dici_onto:SomeTechnology")

        self.assertIsNotNone(result)
        self.assertEqual(len(result.in_ecs), 1)
        self.assertEqual(len(result.out_ecs), 1)
        self.assertEqual(result.in_ecs[0].in_id, "electricity")
        self.assertEqual(result.in_ecs[0].in_part, 0.75)
        self.assertEqual(result.main_in_ec, "electricity")
        self.assertEqual(result.out_ecs[0].ec_id, "heat")
        self.assertEqual(result.out_ecs[0].out_eff, 0.9)
        self.assertEqual(result.main_out_ec, "heat")

    def test_raises_when_in_carrier_missing_for_input_flow(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "main_in_carrier": "https://digicities.info/proj/MOTEL/EC/electricity",
                    "main_out_carrier": pd.NA,
                    "in_flow": "https://digicities.info/proj/MOTEL/Flow/in_1",
                    "in_carrier": pd.NA,
                    "in_value": 0.5,
                    "out_flow": pd.NA,
                    "out_carrier": pd.NA,
                    "out_value": pd.NA,
                }
            ]
        )

        repository = StubRepository(df)

        with self.assertRaisesRegex(ValueError, "Missing 'in_carrier'"):
            build_energy_carriers(repository, "dici_onto:SomeTechnology")

    def test_raises_when_out_carrier_missing_for_output_flow(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "main_in_carrier": pd.NA,
                    "main_out_carrier": "https://digicities.info/proj/MOTEL/EC/heat",
                    "in_flow": pd.NA,
                    "in_carrier": pd.NA,
                    "in_value": pd.NA,
                    "out_flow": "https://digicities.info/proj/MOTEL/Flow/out_1",
                    "out_carrier": pd.NA,
                    "out_value": 0.9,
                }
            ]
        )

        repository = StubRepository(df)

        with self.assertRaisesRegex(ValueError, "Missing 'out_carrier'"):
            build_energy_carriers(repository, "dici_onto:SomeTechnology")


if __name__ == "__main__":
    unittest.main()
