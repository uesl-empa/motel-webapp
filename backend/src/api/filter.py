import math
from urllib.parse import unquote
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from app.client.GraphDBClient import GraphDBClient
from backend.src.config import get_backend_settings
from backend.src.repositories.node_repository import GraphDBNodeRepository
from backend.src.services.filter_service import get_component_hierarchy
from backend.src.services.filter_service import get_available_carrier_iris
from backend.src.services.filter_service import get_available_location_iris
from backend.src.services.filter_service import get_filterable_attribute_names_for_type
from backend.src.utils.iri import local_name
from backend.src.utils.sparql_filters import build_carrier_filter_fragment
from backend.src.utils.sparql_filters import build_location_filter_fragment
from backend.src.utils.sparql_filters import build_range_filter_fragment


router = APIRouter(prefix="/api/filter", tags=["filter"])
settings = get_backend_settings()
DATA_DIR = Path(__file__).resolve().parents[3] / "app" / "data"
PRIMARY_TTL_PATH = DATA_DIR / "01_classes_and_attributes" / "cls_atr_motel.ttl"


def _build_node_repository() -> GraphDBNodeRepository:
    client = GraphDBClient(
        repository=settings.graphdb_repository,
        host=settings.graphdb_url,
    )
    return GraphDBNodeRepository(client)


def _read_generated_at(ttl_path: Path) -> str | None:
    if not ttl_path.exists():
        return None

    try:
        with ttl_path.open(encoding="utf-8") as handle:
            for _ in range(5):
                line = handle.readline()
                if not line:
                    break
                if line.startswith("# Generated at:"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        return None

    return None


def _build_ttl_status(ttl_path: Path) -> dict:
    exists = ttl_path.exists()
    modified_at = None
    size_bytes = None
    if exists:
        stat = ttl_path.stat()
        modified_at = stat.st_mtime
        size_bytes = stat.st_size

    return {
        "path": str(ttl_path),
        "exists": exists,
        "generated_at": _read_generated_at(ttl_path),
        "modified_at_unix": modified_at,
        "size_bytes": size_bytes,
    }


class AttributeRangeFilter(BaseModel):
    lower: float | None = None
    upper: float | None = None

    @model_validator(mode="after")
    def validate_bounds(self):
        if self.lower is not None and not math.isfinite(self.lower):
            raise ValueError("Lower bound must be a finite number")
        if self.upper is not None and not math.isfinite(self.upper):
            raise ValueError("Upper bound must be a finite number")
        if self.lower is not None and self.upper is not None and self.lower > self.upper:
            raise ValueError("Lower bound cannot be greater than upper bound")
        return self


class InstancesFilterRequest(BaseModel):
    type_label: str
    attribute_ranges: dict[str, AttributeRangeFilter] = Field(default_factory=dict)
    location_iris: list[str] = Field(default_factory=list)
    carrier_iris: list[str] = Field(default_factory=list)


@router.get("/data-status")
async def data_status() -> dict:
    """Return TTL file status visible to the running backend container."""
    try:
        node_repository = _build_node_repository()
        repository_size = node_repository.client.get_repository_size()
        return {
            "status": "success",
            "graphdb_repository": settings.graphdb_repository,
            "graphdb_url": settings.graphdb_url,
            "repository_size": repository_size,
            "ttl_file": _build_ttl_status(PRIMARY_TTL_PATH),
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving data status: {str(e)}",
        )

@router.get("/components")
async def all_components() -> dict:
    """
    Retrieve instance-bearing components from the MOTEL repository.
    
    Returns:
        dict with list of hierarchical component nodes
    """
    try:
        node_repository = _build_node_repository()
        components = get_component_hierarchy(node_repository)
        return {"status": "success", "components": components}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving components: {str(e)}",
        )


@router.post("/instances")
async def instances_of_type_with_filters(request: InstancesFilterRequest) -> dict:
    """
    Retrieve instances of a specific type and optionally apply per-attribute
    range constraints directly in SPARQL.
    """
    try:
        node_repository = _build_node_repository()

        decoded_type_label = unquote(request.type_label)
        decoded_location_iris = [unquote(iri) for iri in request.location_iris]

        allowed_attributes = get_filterable_attribute_names_for_type(node_repository, decoded_type_label)
        invalid_attributes = sorted(
            attribute for attribute in request.attribute_ranges if attribute not in allowed_attributes
        )

        if invalid_attributes:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Unsupported range filter attributes for selected type: "
                    + ", ".join(invalid_attributes)
                ),
            )

        if decoded_location_iris:
            allowed_locations = get_available_location_iris(node_repository, decoded_type_label)
            invalid_locations = sorted(iri for iri in decoded_location_iris if iri not in allowed_locations)
            if invalid_locations:
                raise HTTPException(
                    status_code=400,
                    detail="Unsupported location filter IRIs: " + ", ".join(invalid_locations),
                )

        decoded_carrier_iris = [unquote(iri) for iri in request.carrier_iris]
        if decoded_carrier_iris:
            allowed_carriers = get_available_carrier_iris(node_repository, decoded_type_label)
            invalid_carriers = sorted(iri for iri in decoded_carrier_iris if iri not in allowed_carriers)
            if invalid_carriers:
                raise HTTPException(
                    status_code=400,
                    detail="Unsupported carrier filter IRIs: " + ", ".join(invalid_carriers),
                )

        range_filters = build_range_filter_fragment(
            {
                attribute_name: (bounds.lower, bounds.upper)
                for attribute_name, bounds in request.attribute_ranges.items()
            }
        )
        location_filter = build_location_filter_fragment(decoded_location_iris)
        carrier_filter = build_carrier_filter_fragment(decoded_carrier_iris)
        instances = node_repository.get_instances_with_attributes(
            tech_type=decoded_type_label,
            range_filters=range_filters,
            location_filter=location_filter,
            carrier_filter=carrier_filter,
        )
        return {"status": "success", "instances": instances.to_dict(orient="records")}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving instances of type {request.type_label}: {str(e)}",
        )


@router.get("/locations/{type_label:path}")
async def available_locations_for_type(type_label: str) -> dict:
    """Return locations for a selected component type that has `locatedIn` relations."""
    try:
        node_repository = _build_node_repository()

        decoded_type_label = unquote(type_label)
        location_iris = sorted(get_available_location_iris(node_repository, decoded_type_label))

        return {
            "status": "success",
            "type_label": decoded_type_label,
            "locations": [
                {
                    "iri": location,
                    "label": local_name(location),
                }
                for location in location_iris
            ],
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving available locations for type {type_label}: {str(e)}",
        )


@router.get("/carriers/{type_label:path}")
async def available_carriers_for_type(type_label: str) -> dict:
    """Return energy carriers reachable via flows for a selected component type."""
    try:
        node_repository = _build_node_repository()

        decoded_type_label = unquote(type_label)
        carrier_iris = sorted(get_available_carrier_iris(node_repository, decoded_type_label))

        return {
            "status": "success",
            "type_label": decoded_type_label,
            "carriers": [
                {
                    "iri": carrier,
                    "label": local_name(carrier),
                }
                for carrier in carrier_iris
            ],
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving available carriers for type {type_label}: {str(e)}",
        )


@router.get("/attributes/{type_label:path}")
async def filterable_attributes_for_type(type_label: str) -> dict:
    """Return filterable numeric attribute types discovered for a class."""
    try:
        node_repository = _build_node_repository()

        decoded_type_label = unquote(type_label)
        attribute_names = sorted(get_filterable_attribute_names_for_type(node_repository, decoded_type_label))

        return {
            "status": "success",
            "type_label": decoded_type_label,
            "attributes": attribute_names,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving filterable attributes for type {type_label}: {str(e)}",
        )

@router.get("/conversion-params/{tech_iri:path}")
async def conversion_params_for_technology(tech_iri: str) -> dict:
    """
    Return input/output energy carrier flows with all their attributes for a
    specific technology IRI.
    """
    try:
        node_repository = _build_node_repository()
        decoded_iri = unquote(tech_iri)
        df = node_repository.get_energy_carriers(decoded_iri)

        if df.empty:
            return {"status": "success", "flows": []}

        flows_dict: dict = {}

        for _, row in df.iterrows():
            flow_raw = row.get("flow", "")
            flow_iri = str(flow_raw) if flow_raw and str(flow_raw) != "nan" else ""
            if not flow_iri:
                continue

            direction = str(row.get("direction", ""))
            carrier_raw = row.get("carrier", "")
            carrier = str(carrier_raw) if carrier_raw and str(carrier_raw) != "nan" else ""

            if flow_iri not in flows_dict:
                flows_dict[flow_iri] = {
                    "flow_iri": flow_iri,
                    "direction": direction,
                    "carrier": carrier,
                    "attributes": [],
                }

            att_raw = row.get("att", "")
            att = str(att_raw) if att_raw and str(att_raw) != "nan" else ""
            if not att:
                continue

            att_cat_raw = row.get("att_category", "")
            att_cat = str(att_cat_raw) if att_cat_raw and str(att_cat_raw) != "nan" else ""
            att_val_raw = row.get("att_val", "")
            att_val = str(att_val_raw) if att_val_raw and str(att_val_raw) != "nan" else ""
            att_unit_raw = row.get("att_unit", "")
            att_unit = str(att_unit_raw) if att_unit_raw and str(att_unit_raw) != "nan" else ""
            unit_label_raw = row.get("unit_label", "")
            unit_label = str(unit_label_raw) if unit_label_raw and str(unit_label_raw) != "nan" else ""
            att_currency_raw = row.get("att_currency", "")
            att_currency = str(att_currency_raw) if att_currency_raw and str(att_currency_raw) != "nan" else ""

            flows_dict[flow_iri]["attributes"].append({
                "att": att,
                "att_category": att_cat,
                "att_val": att_val,
                "att_unit": att_unit,
                "unit_label": unit_label,
                "att_currency": att_currency,
            })

        # Sort: Input first, then alphabetically by flow IRI
        flows = sorted(flows_dict.values(), key=lambda f: (0 if f["direction"] == "Input" else 1, f["flow_iri"]))

        return {"status": "success", "flows": flows}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving conversion params for {tech_iri}: {str(e)}",
        )


@router.get("/embedded-carbon/{tech_iri:path}")
async def embedded_carbon_for_technology(tech_iri: str) -> dict:
    """
    Return embedded carbon instances (LCA_unit, ssp2_NDC, ssp2_PkBudg1000) for a technology IRI.
    """
    try:
        node_repository = _build_node_repository()
        decoded_iri = unquote(tech_iri)
        df = node_repository.get_embedded_carbon(decoded_iri)

        if df.empty:
            return {"status": "success", "embedded_carbon": []}

        embedded_carbon = []
        for _, row in df.iterrows():
            def _s(key: str) -> str:
                v = row.get(key, "")
                return str(v) if v and str(v) != "nan" else ""

            ec_iri = _s("ec_iri")
            if not ec_iri:
                continue

            embedded_carbon.append({
                "ec_iri": ec_iri,
                "lca_activity": _s("lca_activity"),
                "lca_ref_product": _s("lca_ref_product"),
                "period": _s("period"),
                "location": _s("location"),
                "lca_unit": _s("lca_unit"),
                "ssp2_ndc": _s("ssp2_ndc"),
                "ssp2_pkbudg1000": _s("ssp2_pkbudg1000"),
            })

        return {"status": "success", "embedded_carbon": embedded_carbon}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving embedded carbon for {tech_iri}: {str(e)}",
        )


@router.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}
