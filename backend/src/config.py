"""
Environment-backed runtime settings for the backend application.
"""

from dataclasses import dataclass
import os


DEFAULT_CORS_ALLOWED_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)

DEFAULT_GRAPHDB_URL = "http://localhost:7200"
DEFAULT_GRAPHDB_REPOSITORY = "MOTEL"
DEFAULT_SUPPORTED_ASSEMBLY_COMPONENT_ROOTS = (
    "dici_onto:Converter",
    "dici_onto:EnergyConverter",
)


def _parse_csv(value: str | None, fallback: tuple[str, ...]) -> list[str]:
    if value is None:
        return list(fallback)

    return [item.strip() for item in value.split(",") if item.strip()]


def _get_port() -> int:
    raw_port = os.getenv("BACKEND_PORT")
    if raw_port is None:
        return 8000

    try:
        return int(raw_port)
    except ValueError as exc:
        raise ValueError("BACKEND_PORT must be an integer.") from exc


def _get_optional_env(var_name: str) -> str | None:
    value = os.getenv(var_name)
    if value is None:
        return None

    normalized = value.strip()
    return normalized if normalized else None


@dataclass(frozen=True)
class BackendSettings:
    host: str
    port: int
    cors_allowed_origins: list[str]
    graphdb_url: str
    graphdb_repository: str
    drafts_db_path: str | None
    supported_assembly_component_roots: list[str]


def get_backend_settings() -> BackendSettings:
    return BackendSettings(
        host=os.getenv("BACKEND_HOST", "0.0.0.0"),
        port=_get_port(),
        cors_allowed_origins=_parse_csv(
            os.getenv("BACKEND_CORS_ALLOWED_ORIGINS"),
            DEFAULT_CORS_ALLOWED_ORIGINS,
        ),
        graphdb_url=os.getenv("GRAPHDB_URL", DEFAULT_GRAPHDB_URL).rstrip("/"),
        graphdb_repository=os.getenv("GRAPHDB_REPOSITORY", DEFAULT_GRAPHDB_REPOSITORY),
        drafts_db_path=_get_optional_env("BACKEND_DRAFTS_DB_PATH"),
        supported_assembly_component_roots=_parse_csv(
            os.getenv("BACKEND_SUPPORTED_ASSEMBLY_COMPONENT_ROOTS"),
            DEFAULT_SUPPORTED_ASSEMBLY_COMPONENT_ROOTS,
        ),
    )