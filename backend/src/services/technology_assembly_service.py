import pandas as pd
import json
import sqlite3
import time
from pathlib import Path
from uuid import uuid4

import yaml

from app.client.GraphDBClient import GraphDBClient
from backend.src.constants.technology_attributes import (
    FIELD_CAPEX,
    FIELD_CAPEX_PER_CAP,
    FIELD_CO2_CAP,
    FIELD_INTEREST_RATE,
    FIELD_INTRODUCED,
    FIELD_LIFETIME,
    FIELD_OPEX,
    FIELD_OPEX_CAP,
    FIELD_OPEX_ENERGY,
    FIELD_TRL,
)
from backend.src.constants.unit_mapping import UNIT_MAPPING
from backend.src.repositories.node_repository import NodeRepository
from backend.src.repositories.node_repository import GraphDBNodeRepository
from backend.src.schemas.ehubx_file_structure import (
    BaseTechnology,
    ConversionInput,
    ConversionOutput,
    ConversionParams,
    ConversionTechnology,
    CostParams,
    EmissionParams,
    StorageTechnology,
    TechParams,
    TechsConfig,
)
from backend.src.services.serialization_service import TechsConfigSerializationService
from backend.src.utils.iri import local_name
from backend.src.utils.technology_attributes import build_attribute_lookup
from backend.src.utils.technology_attributes import get_attribute_value_for_field
from backend.src.utils.technology_attributes import get_first_valid_value
from backend.src.utils.technology import parse_type


class DraftNotFoundError(ValueError):
    pass


class DuplicateTechnologyError(ValueError):
    pass


class TechnologyNotFoundError(ValueError):
    pass


def build_energy_carriers(repository: NodeRepository, energy_conv_id: str):
    energy_carriers_result = repository.get_energy_carriers(energy_conv_id)
    if energy_carriers_result.empty:
        return None

    def _to_optional_float(value: object) -> float | None:
        if value is None or pd.isna(value):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _to_bool(value: object) -> bool:
        if value is None or pd.isna(value):
            return False
        return str(value).strip().lower() in {"true", "1", "yes"}

    # Legacy format with pre-pivoted in/out columns.
    legacy_columns = {"in_flow", "in_carrier", "in_value", "out_flow", "out_carrier", "out_value"}
    if legacy_columns.issubset(set(energy_carriers_result.columns)):
        main_in_carrier = None
        if "main_in_carrier" in energy_carriers_result.columns:
            main_in_carrier_series = energy_carriers_result["main_in_carrier"].dropna()
            if not main_in_carrier_series.empty:
                main_in_carrier = local_name(str(main_in_carrier_series.iloc[0]))

        main_out_carrier = None
        if "main_out_carrier" in energy_carriers_result.columns:
            main_out_carrier_series = energy_carriers_result["main_out_carrier"].dropna()
            if not main_out_carrier_series.empty:
                main_out_carrier = local_name(str(main_out_carrier_series.iloc[0]))

        inputs = []
        outputs = []

        for _, row in energy_carriers_result.iterrows():
            in_flow = row.get("in_flow")
            in_carrier = row.get("in_carrier")
            if pd.notna(in_flow):
                if pd.isna(in_carrier):
                    raise ValueError("Missing 'in_carrier' for conversion input flow")
                inputs.append(ConversionInput(in_id=local_name(str(in_carrier)), in_part=float(row["in_value"])))

            out_flow = row.get("out_flow")
            out_carrier = row.get("out_carrier")
            if pd.notna(out_flow):
                if pd.isna(out_carrier):
                    raise ValueError("Missing 'out_carrier' for conversion output flow")
                outputs.append(ConversionOutput(ec_id=local_name(str(out_carrier)), out_eff=float(row["out_value"])))

        return ConversionParams(
            in_ecs=inputs,
            main_in_ec=main_in_carrier,
            out_ecs=outputs,
            main_out_ec=main_out_carrier,
        )

    # New format with one row per flow attribute.
    expected_row_columns = {"flow", "direction", "carrier", "att", "att_val"}
    if not expected_row_columns.issubset(set(energy_carriers_result.columns)):
        return ConversionParams(in_ecs=[], main_in_ec=None, out_ecs=[], main_out_ec=None)

    flows_by_iri: dict[str, dict[str, object]] = {}
    main_in_carrier: str | None = None
    main_out_carrier: str | None = None

    for _, row in energy_carriers_result.iterrows():
        flow_raw = row.get("flow")
        if flow_raw is None or pd.isna(flow_raw):
            continue

        flow_iri = str(flow_raw)
        direction = str(row.get("direction", "")).strip().lower()
        carrier_raw = row.get("carrier")
        carrier_name = None if carrier_raw is None or pd.isna(carrier_raw) else local_name(str(carrier_raw))

        flow_state = flows_by_iri.setdefault(
            flow_iri,
            {
                "direction": direction,
                "carrier": carrier_name,
                "conversion_factor": None,
                "conversion_unit": None,
            },
        )
        if carrier_name:
            flow_state["carrier"] = carrier_name
        if direction:
            flow_state["direction"] = direction

        att_raw = row.get("att")
        if att_raw is None or pd.isna(att_raw):
            continue

        att_local = local_name(str(att_raw))
        att_value = row.get("att_val")

        if att_local in {"EnergyConversionFactor", "MaterialConversionFactor", "ConversionFactor"}:
            parsed_value = _to_optional_float(att_value)
            if parsed_value is not None:
                flow_state["conversion_factor"] = parsed_value
            unit_label_raw = row.get("unit_label")
            if unit_label_raw is not None and not pd.isna(unit_label_raw):
                flow_state["conversion_unit"] = UNIT_MAPPING.get(str(unit_label_raw), str(unit_label_raw))
            continue

        if att_local == "IsMainInput" and _to_bool(att_value) and carrier_name:
            main_in_carrier = carrier_name
            continue

        if att_local == "IsMainOutput" and _to_bool(att_value) and carrier_name:
            main_out_carrier = carrier_name

    inputs: list[ConversionInput] = []
    outputs: list[ConversionOutput] = []

    for flow_state in flows_by_iri.values():
        direction = str(flow_state.get("direction", "")).strip().lower()
        carrier_name = flow_state.get("carrier")
        conversion_factor = flow_state.get("conversion_factor")
        conversion_unit = flow_state.get("conversion_unit")
        if not carrier_name or conversion_factor is None:
            continue

        factor_value: str | float = (
            f"{conversion_factor} {conversion_unit}" if conversion_unit else float(conversion_factor)
        )

        if direction == "input":
            inputs.append(ConversionInput(in_id=str(carrier_name), in_part=factor_value))
        elif direction == "output":
            outputs.append(ConversionOutput(ec_id=str(carrier_name), out_eff=factor_value))

    conversion_params = ConversionParams(
        in_ecs=inputs,
        main_in_ec=main_in_carrier,
        out_ecs=outputs,
        main_out_ec=main_out_carrier,
    )
    return conversion_params
    

def build_base_technology(
    repository: NodeRepository,
    technology_iri: str,
    supported_component_roots: list[str],
) -> BaseTechnology:
    tech_result = repository.get_tech_params(
        technology_iri,
        supported_component_roots=supported_component_roots,
    )
    if tech_result.empty:
        raise ValueError(f"No technology parameters found for component '{technology_iri}'")

    attribute_lookup = build_attribute_lookup(tech_result)

    # tech_params
    lifetime = get_attribute_value_for_field(tech_result, FIELD_LIFETIME, attribute_lookup)
    trl = get_attribute_value_for_field(tech_result, FIELD_TRL, attribute_lookup)
    introduced = get_attribute_value_for_field(tech_result, FIELD_INTRODUCED, attribute_lookup)

    # cost_params
    interest_rate = get_attribute_value_for_field(tech_result, FIELD_INTEREST_RATE, attribute_lookup)
    capex = get_attribute_value_for_field(tech_result, FIELD_CAPEX, attribute_lookup)
    capex_per_cap = get_attribute_value_for_field(
        tech_result,
        FIELD_CAPEX_PER_CAP,
        attribute_lookup,
    )
    opex = get_attribute_value_for_field(tech_result, FIELD_OPEX, attribute_lookup)
    opex_cap = get_attribute_value_for_field(tech_result, FIELD_OPEX_CAP, attribute_lookup)
    opex_energy = get_attribute_value_for_field(tech_result, FIELD_OPEX_ENERGY, attribute_lookup)

    # emission_params
    co2_cap = get_attribute_value_for_field(tech_result, FIELD_CO2_CAP, attribute_lookup)

    # embedded carbon params
    ec_df = repository.get_embedded_carbon(technology_iri)
    ssp2_ndc = None
    ssp2_pkbudg1000 = None
    if not ec_df.empty:
        ec_row = ec_df.iloc[0]
        lca_unit_raw = ec_row.get("lca_unit")
        lca_unit = None if lca_unit_raw is None or pd.isna(lca_unit_raw) else str(lca_unit_raw)
        ndc_raw = ec_row.get("ssp2_ndc")
        if ndc_raw is not None and not pd.isna(ndc_raw):
            ndc_val = float(ndc_raw)
            ssp2_ndc = f"{ndc_val} {lca_unit}" if lca_unit else ndc_val
        pkb_raw = ec_row.get("ssp2_pkbudg1000")
        if pkb_raw is not None and not pd.isna(pkb_raw):
            pkb_val = float(pkb_raw)
            ssp2_pkbudg1000 = f"{pkb_val} {lca_unit}" if lca_unit else pkb_val

    if lifetime is None:
        raise ValueError("Technology lifetime is missing")

    def _to_int(v):
        try:
            return int(float(str(v))) if v is not None else None
        except (ValueError, TypeError):
            return v

    tech_params = TechParams(
        lifetime=lifetime,
        introduced=_to_int(introduced),
        trl=_to_int(trl),
    )

    cost_params = CostParams(
        interest_rate=interest_rate,
        one_time_capex=capex,
        capex_per_cap=capex_per_cap,
        one_time_opex=opex,
        opex_per_cap=opex_cap,
        opex_per_energy=opex_energy,
    )

    emission_params = EmissionParams(
        co2_per_cap=co2_cap,
        ssp2_ndc=ssp2_ndc,
        ssp2_pkbudg1000=ssp2_pkbudg1000,
    )

    tech_id = get_first_valid_value(tech_result, "tech_id")
    assembly_root_raw = get_first_valid_value(tech_result, "assembly_root")

    if tech_id is None:
        raise ValueError("Technology ID is missing")
    if assembly_root_raw is None:
        raise ValueError("Technology type is not supported for assembly")

    parsed_type = parse_type(local_name(str(assembly_root_raw)))
    if parsed_type is None:
        raise ValueError(f"Unsupported assembly root: {assembly_root_raw}")

    base_technology = BaseTechnology(
        tech_id=local_name(str(tech_id)),
        type=parsed_type,
        tech_params=tech_params,
        costs=cost_params,
        emissions=emission_params,
    )

    return base_technology

def build_conversion_technology(
    base_technology: BaseTechnology,
    repository: NodeRepository,
    technology_iri: str,
) -> ConversionTechnology:
    conversion_params = build_energy_carriers(repository, technology_iri)
    if conversion_params is None:
        raise ValueError(f"No energy carriers found for technology '{technology_iri}'")

    return ConversionTechnology(
        **base_technology.model_dump(),
        conversion_params=conversion_params,
    )

def build_storage_technology(
    base_technology: BaseTechnology,
    repository: NodeRepository,
    technology_iri: str,
) -> StorageTechnology:
    raise NotImplementedError("Storage technology assembly is not implemented yet")


class TechnologyAssemblyService:
    def __init__(
        self,
        repository_name: str = "MOTEL",
        graphdb_host: str | None = None,
        drafts_db_path: str | Path | None = None,
        supported_component_roots: list[str] | None = None,
        draft_ttl_days: int = 30,
        cleanup_interval_seconds: int = 3600,
    ) -> None:
        self.repository_name = repository_name
        self.graphdb_host = graphdb_host
        self._drafts_db_path = Path(drafts_db_path) if drafts_db_path else self._default_drafts_db_path()
        self._draft_ttl_days = max(0, draft_ttl_days)
        self._supported_component_roots = [
            root.strip() for root in (supported_component_roots or []) if root.strip()
        ]
        self._cleanup_interval_seconds = max(1, cleanup_interval_seconds)
        self._last_cleanup_monotonic = 0.0
        self._serialization_service = TechsConfigSerializationService()
        self._initialize_storage()
        self._run_cleanup_if_due(force=True)

    @staticmethod
    def _default_drafts_db_path() -> Path:
        return Path(__file__).resolve().parents[3] / "backend" / "output" / "drafts.sqlite"

    def _initialize_storage(self) -> None:
        self._drafts_db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._drafts_db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS technology_drafts (
                    config_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_technology_drafts_updated_at
                ON technology_drafts(updated_at)
                """
            )

    def _run_cleanup_if_due(self, force: bool = False) -> None:
        if self._draft_ttl_days <= 0:
            return

        now = time.monotonic()
        if not force and (now - self._last_cleanup_monotonic) < self._cleanup_interval_seconds:
            return

        self.cleanup_expired_drafts()
        self._last_cleanup_monotonic = now

    def cleanup_expired_drafts(self) -> int:
        if self._draft_ttl_days <= 0:
            return 0

        cutoff = f"-{self._draft_ttl_days} days"
        with sqlite3.connect(self._drafts_db_path) as conn:
            cursor = conn.execute(
                """
                DELETE FROM technology_drafts
                WHERE datetime(updated_at) < datetime('now', ?)
                """,
                (cutoff,),
            )
            deleted_count = cursor.rowcount

        return deleted_count if deleted_count and deleted_count > 0 else 0

    def _serialize_draft(self, draft: TechsConfig) -> str:
        return json.dumps(draft.model_dump(mode="json"), ensure_ascii=False)

    def _deserialize_draft(self, payload: str) -> TechsConfig:
        return TechsConfig.model_validate(json.loads(payload))

    def _write_draft(self, config_id: str, draft: TechsConfig) -> None:
        payload = self._serialize_draft(draft)
        with sqlite3.connect(self._drafts_db_path) as conn:
            conn.execute(
                """
                INSERT INTO technology_drafts (config_id, payload)
                VALUES (?, ?)
                ON CONFLICT(config_id) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (config_id, payload),
            )

    def _read_draft(self, config_id: str) -> TechsConfig | None:
        with sqlite3.connect(self._drafts_db_path) as conn:
            cursor = conn.execute(
                "SELECT payload FROM technology_drafts WHERE config_id = ?",
                (config_id,),
            )
            row = cursor.fetchone()

        if row is None:
            return None

        return self._deserialize_draft(row[0])

    def create_draft(self) -> str:
        self._run_cleanup_if_due()
        config_id = str(uuid4())
        self._write_draft(config_id, TechsConfig(techs=[]))
        return config_id

    def create_draft_with_config(self, draft: TechsConfig) -> str:
        self._run_cleanup_if_due()
        config_id = str(uuid4())
        self._write_draft(config_id, draft)
        return config_id

    def get_draft(self, config_id: str) -> TechsConfig:
        self._run_cleanup_if_due()
        draft = self._read_draft(config_id)
        if draft is None:
            raise DraftNotFoundError(f"Draft config '{config_id}' not found")
        return draft

    @staticmethod
    def _contains_technology_iri(draft: TechsConfig, technology_iri: str) -> bool:
        return TechnologyAssemblyService._find_technology_index(draft, technology_iri) is not None

    @staticmethod
    def _find_technology_index(draft: TechsConfig, technology_iri: str) -> int | None:
        normalized_iri = technology_iri.strip()
        if not normalized_iri:
            return None

        normalized_local_name = local_name(normalized_iri)

        for idx, technology in enumerate(draft.techs):
            tech_id = getattr(technology, "tech_id", None)
            if tech_id and local_name(str(tech_id)) == normalized_local_name:
                return idx

        return None

    def append_technology_to_draft(self, config_id: str, technology_iri: str) -> ConversionTechnology:
        draft = self.get_draft(config_id)
        normalized_iri = technology_iri.strip()

        if not normalized_iri:
            raise ValueError("Technology IRI cannot be empty")

        if self._contains_technology_iri(draft, normalized_iri):
            raise DuplicateTechnologyError(
                f"Technology '{normalized_iri}' is already present in draft '{config_id}'"
            )

        node_repository = self._build_repository()

        if not node_repository.is_technology_supported_for_assembly(
            normalized_iri,
            self._supported_component_roots,
        ):
            raise ValueError(
                f"Technology '{normalized_iri}' is not supported for technology assembly"
            )

        base_technology = build_base_technology(
            node_repository,
            normalized_iri,
            supported_component_roots=self._supported_component_roots,
        )
        if base_technology.type == "conversion":
            specific_technology = build_conversion_technology(
                base_technology=base_technology,
                repository=node_repository,
                technology_iri=normalized_iri,
            )
        elif base_technology.type == "storage":
            specific_technology = build_storage_technology(
                base_technology=base_technology,
                repository=node_repository,
                technology_iri=normalized_iri,
            )
        else:
            raise ValueError(
                f"Technology '{normalized_iri}' has unsupported assembled type '{base_technology.type}'"
            )

        draft.techs.append(specific_technology)
        self._write_draft(config_id, draft)
        return specific_technology

    def remove_technology_from_draft(self, config_id: str, technology_iri: str) -> BaseTechnology:
        draft = self.get_draft(config_id)
        normalized_iri = technology_iri.strip()

        if not normalized_iri:
            raise ValueError("Technology IRI cannot be empty")

        technology_index = self._find_technology_index(draft, normalized_iri)
        if technology_index is None:
            raise TechnologyNotFoundError(
                f"Technology '{normalized_iri}' is not present in draft '{config_id}'"
            )

        removed_technology = draft.techs.pop(technology_index)
        self._write_draft(config_id, draft)
        return removed_technology

    def preview_draft_yaml(self, config_id: str) -> str:
        draft = self.get_draft(config_id)
        payload = self._serialization_service.to_dict(draft)
        return yaml.safe_dump(
            payload,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )

    def export_draft_csv(self, config_id: str) -> str:
        draft = self.get_draft(config_id)
        return self._serialization_service.to_excel_csv(draft)

    def _build_repository(self) -> GraphDBNodeRepository:
        if self.graphdb_host:
            client = GraphDBClient(repository=self.repository_name, host=self.graphdb_host)
        else:
            client = GraphDBClient(repository=self.repository_name)
        return GraphDBNodeRepository(client)

    def get_supported_component_local_names(self) -> list[str]:
        if not self._supported_component_roots:
            return []

        repository = self._build_repository()
        supported_components = repository.get_supported_assembly_component_types(
            self._supported_component_roots,
        )
        if supported_components.empty or "component" not in supported_components.columns:
            return []

        local_names = {
            local_name(str(component)).strip().lower()
            for component in supported_components["component"].dropna().tolist()
        }
        return sorted(name for name in local_names if name)