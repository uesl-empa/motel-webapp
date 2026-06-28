"""YAML import and validation service for TechsConfig drafts."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError
import yaml
from yaml import YAMLError

from backend.src.schemas.ehubx_file_structure import TechsConfig


class TechsConfigImportError(ValueError):
    """Base error type for TechsConfig import failures."""


class TechsConfigYamlParseError(TechsConfigImportError):
    """Raised when raw YAML content cannot be parsed."""


class TechsConfigValidationError(TechsConfigImportError):
    """Raised when parsed YAML does not satisfy the TechsConfig schema."""

    def __init__(self, message: str, *, validation_errors: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.validation_errors = validation_errors or []


class TechsConfigImportService:
    """Convert YAML text into validated TechsConfig models."""

    def parse_yaml(self, yaml_content: str) -> TechsConfig:
        normalized_content = yaml_content.strip()
        if not normalized_content:
            raise TechsConfigYamlParseError("YAML content is empty")

        try:
            payload = yaml.safe_load(normalized_content)
        except YAMLError as exc:
            raise TechsConfigYamlParseError(f"Invalid YAML format: {str(exc)}") from exc

        if payload is None:
            raise TechsConfigYamlParseError("YAML content is empty")

        if not isinstance(payload, dict):
            raise TechsConfigYamlParseError("YAML root must be an object with a 'techs' field")
        
        # Guard: filter to only conversion type technologies before validation
        # TODO: remove this once we support all technology types in the YAML import
        if isinstance(payload.get("techs"), list):
            payload["techs"] = [
                tech for tech in payload["techs"]
                if isinstance(tech, dict) and tech.get("type") == "conversion"
            ]
        
        try:
            return TechsConfig.model_validate(payload)
        except ValidationError as exc:
            raise TechsConfigValidationError(
                "YAML does not match TechsConfig schema",
                validation_errors=exc.errors(),
            ) from exc
