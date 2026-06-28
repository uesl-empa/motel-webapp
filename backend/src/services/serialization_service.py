from __future__ import annotations

import csv
import io
import json
from typing import Any, Iterable

from pydantic import BaseModel

from backend.src.schemas.ehubx_file_structure import BaseTechnology, TechsConfig


class TechsConfigSerializationService:
    """Serialize TechsConfig models into target-agnostic Python structures."""

    _ROOT_COLUMNS = ("tech_id", "type")
    _DROPPED_CONTAINER_KEYS = {"tech_params", "costs", "emissions", "ecs"}

    def to_dict(
        self,
        config: TechsConfig | Iterable[BaseTechnology],
        *,
        exclude_none: bool = True,
    ) -> dict[str, Any]:
        """
        Convert a TechsConfig object (or iterable of technologies) into a dict.

        Args:
            config: A TechsConfig instance or iterable of technology models.
            exclude_none: If true, fields set to None are omitted.
        """
        if isinstance(config, TechsConfig):
            return self._model_to_dict(config, exclude_none=exclude_none)

        technologies = list(config)
        return {
            "techs": [
                self._model_to_dict(technology, exclude_none=exclude_none)
                for technology in technologies
            ]
        }

    def to_csv(
        self,
        config: TechsConfig | Iterable[BaseTechnology],
        *,
        exclude_none: bool = True,
    ) -> str:
        """Convert a TechsConfig object (or iterable of technologies) into CSV text."""
        payload = self.to_dict(config, exclude_none=exclude_none)
        techs = payload.get("techs", [])

        if not techs:
            return ""

        rows = [
            self._flatten_dict_for_csv(technology)
            for technology in techs
            if isinstance(technology, dict)
        ]

        if not rows:
            return ""

        fieldnames = self._build_csv_fieldnames(rows)

        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

        return buffer.getvalue()

    def to_excel_csv(
        self,
        config: TechsConfig | Iterable[BaseTechnology],
        *,
        exclude_none: bool = True,
    ) -> str:
        """Convert configuration into an Excel-friendly CSV string."""
        csv_content = self.to_csv(config, exclude_none=exclude_none)
        if not csv_content:
            return ""

        return f"\ufeffsep=,\r\n{csv_content}"

    @staticmethod
    def _model_to_dict(model: BaseModel, *, exclude_none: bool) -> dict[str, Any]:
        return model.model_dump(exclude_none=exclude_none)

    @staticmethod
    def _build_csv_fieldnames(rows: list[dict[str, str | int | float | bool]]) -> list[str]:
        discovered = list(dict.fromkeys(key for row in rows for key in row.keys()))
        root_columns = [key for key in TechsConfigSerializationService._ROOT_COLUMNS if key in discovered]
        remaining = sorted(key for key in discovered if key not in TechsConfigSerializationService._ROOT_COLUMNS)
        return [*root_columns, *remaining]

    @staticmethod
    def _should_drop_container_key(key: str) -> bool:
        return key in TechsConfigSerializationService._DROPPED_CONTAINER_KEYS or key.endswith("_params")

    @staticmethod
    def _serialize_keyed_records(
        records: list[dict[str, Any]],
        *,
        key_field: str,
    ) -> str:
        keyed_records = {
            str(record[key_field]): {
                nested_key: nested_value
                for nested_key, nested_value in record.items()
                if nested_key != key_field
            }
            for record in records
            if isinstance(record, dict) and key_field in record
        }
        return json.dumps(keyed_records, ensure_ascii=False)

    @staticmethod
    def _serialize_list_value(key: str, value: list[Any]) -> str:
        key_field_by_column = {
            "in_ecs": "in_id",
            "out_ecs": "ec_id",
        }
        key_field = key_field_by_column.get(key)
        if key_field and all(isinstance(item, dict) and key_field in item for item in value):
            return TechsConfigSerializationService._serialize_keyed_records(value, key_field=key_field)

        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _flatten_dict_for_csv(
        data: dict[str, Any],
        parent_key: str = "",
        separator: str = ".",
    ) -> dict[str, str | int | float | bool]:
        flat: dict[str, str | int | float | bool] = {}

        for key, value in data.items():
            current_key = f"{parent_key}{separator}{key}" if parent_key else key

            if isinstance(value, dict):
                next_parent_key = parent_key if TechsConfigSerializationService._should_drop_container_key(key) else current_key
                flat.update(
                    TechsConfigSerializationService._flatten_dict_for_csv(
                        value,
                        parent_key=next_parent_key,
                        separator=separator,
                    )
                )
                continue

            if isinstance(value, list):
                flat[current_key] = TechsConfigSerializationService._serialize_list_value(key, value)
                continue

            if value is None:
                flat[current_key] = ""
                continue

            flat[current_key] = value

        return flat