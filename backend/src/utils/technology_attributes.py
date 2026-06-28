from typing import Any

import pandas as pd

from backend.src.constants.technology_attributes import get_attribute_names_for_field
from backend.src.constants.unit_mapping import UNIT_MAPPING
from backend.src.utils.iri import local_name


def get_first_valid_value(dataframe: pd.DataFrame, column_name: str) -> Any:
    if column_name not in dataframe.columns:
        raise KeyError(f"Missing required column '{column_name}'")

    non_null_values = dataframe[column_name].dropna()
    if non_null_values.empty:
        return None

    return non_null_values.iloc[0]


def build_attribute_lookup(tech_result: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if "attr_type" not in tech_result.columns:
        raise KeyError("Missing required column 'attr_type'")

    normalized_attr_types = tech_result["attr_type"].astype(str).map(local_name)
    return {
        str(attr_name): group
        for attr_name, group in tech_result.groupby(normalized_attr_types, sort=False)
    }


def _map_unit_string(unit_text: Any) -> str | None:
    if unit_text is None or pd.isna(unit_text):
        return None

    normalized_text = str(unit_text)
    return UNIT_MAPPING.get(normalized_text, normalized_text)


def get_attribute_value(
    tech_result: pd.DataFrame,
    attribute_type: str,
    attribute_lookup: dict[str, pd.DataFrame] | None = None,
):
    if "attr_type" not in tech_result.columns:
        raise KeyError("Missing required column 'attr_type'")
    if "value" not in tech_result.columns:
        raise KeyError("Missing required column 'value'")

    if attribute_lookup is None:
        normalized_attr_types = tech_result["attr_type"].astype(str).map(local_name)
        matching_rows = tech_result[normalized_attr_types == attribute_type]
    else:
        matching_rows = attribute_lookup.get(attribute_type)

    if matching_rows is None or matching_rows.empty:
        return None

    value = get_first_valid_value(matching_rows, "value")

    unit_label = get_first_valid_value(matching_rows, "unit_label")
    currency_value = get_first_valid_value(matching_rows, "att_currency")
    currency = local_name(currency_value) if pd.notna(currency_value) else None

    mapped_unit = _map_unit_string(unit_label)
    mapped_currency = _map_unit_string(currency)

    if mapped_unit and mapped_currency:
        return f"{value} {mapped_currency}/{mapped_unit}"
    if mapped_currency:
        return f"{value} {mapped_currency}"
    if mapped_unit:
        return f"{value} {mapped_unit}"
    return value


def get_attribute_value_for_field(
    tech_result: pd.DataFrame,
    field_key: str,
    attribute_lookup: dict[str, pd.DataFrame] | None = None,
):
    for attribute_name in get_attribute_names_for_field(field_key):
        value = get_attribute_value(
            tech_result,
            attribute_name,
            attribute_lookup,
        )
        if value is not None:
            return value

    return None
