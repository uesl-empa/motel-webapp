"""
API routes for technology assembly and export.
"""

from fastapi import APIRouter, File, HTTPException, Response, UploadFile
from pydantic import BaseModel

from backend.src.config import get_backend_settings
from backend.src.services.techs_config_import_service import TechsConfigImportService
from backend.src.services.techs_config_import_service import TechsConfigValidationError
from backend.src.services.techs_config_import_service import TechsConfigYamlParseError
from backend.src.services.technology_assembly_service import DraftNotFoundError
from backend.src.services.technology_assembly_service import DuplicateTechnologyError
from backend.src.services.technology_assembly_service import TechnologyNotFoundError
from backend.src.services.technology_assembly_service import TechnologyAssemblyService


class AppendTechnologyRequest(BaseModel):
    """Request body for appending a technology to a draft config."""
    technology_iri: str


class RemoveTechnologyRequest(BaseModel):
    """Request body for removing a technology from a draft config."""
    technology_iri: str

router = APIRouter(prefix="/api/technologies", tags=["technologies"])
settings = get_backend_settings()

technology_assembly_service = TechnologyAssemblyService(
    repository_name=settings.graphdb_repository,
    graphdb_host=settings.graphdb_url,
    drafts_db_path=settings.drafts_db_path,
    supported_component_roots=settings.supported_assembly_component_roots,
)
techs_config_import_service = TechsConfigImportService()


@router.post("/drafts")
async def create_techs_config_draft() -> dict:
    """Create an empty draft TechsConfig for incremental technology assembly."""
    config_id = technology_assembly_service.create_draft()

    return {
        "status": "success",
        "config_id": config_id,
    }


@router.get("/supported-components")
async def get_supported_assembly_components() -> dict:
    """Return local names of component types supported for technology assembly."""
    try:
        supported_local_names = technology_assembly_service.get_supported_component_local_names()
        return {
            "status": "success",
            "supported_components": supported_local_names,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving supported assembly component types: {str(e)}",
        )


@router.post("/drafts/import")
async def import_techs_config_draft(file: UploadFile = File(...)) -> dict:
    """Import a TechsConfig YAML file and persist it as a new draft."""
    filename = (file.filename or "").strip()
    if filename and not filename.lower().endswith((".yaml", ".yml")):
        raise HTTPException(status_code=400, detail="Only .yaml or .yml files are supported")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        yaml_content = content.decode("utf-8")
    except UnicodeDecodeError as e:
        raise HTTPException(status_code=400, detail=f"File must be UTF-8 encoded text: {str(e)}")

    try:
        techs_config = techs_config_import_service.parse_yaml(yaml_content)
        config_id = technology_assembly_service.create_draft_with_config(techs_config)

        return {
            "status": "success",
            "config_id": config_id,
            "techs_config": techs_config.model_dump(),
            "imported_technology_count": len(techs_config.techs),
        }
    except TechsConfigYamlParseError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except TechsConfigValidationError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "message": str(e),
                "validation_errors": e.validation_errors,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error importing TechsConfig YAML: {str(e)}",
        )


@router.get("/drafts/{config_id}")
async def get_techs_config_draft(config_id: str) -> dict:
    """Get current draft TechsConfig for a config id."""
    try:
        techs_config = technology_assembly_service.get_draft(config_id)
        return {
            "status": "success",
            "config_id": config_id,
            "techs_config": techs_config.model_dump(),
        }
    except DraftNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/drafts/{config_id}/append-technology")
async def append_technology_to_draft(config_id: str, request: AppendTechnologyRequest) -> dict:
    """Build one technology and append it to an existing draft TechsConfig."""
    try:
        technology = technology_assembly_service.append_technology_to_draft(
            config_id=config_id,
            technology_iri=request.technology_iri,
        )
        techs_config = technology_assembly_service.get_draft(config_id)

        return {
            "status": "success",
            "config_id": config_id,
            "technology": technology.model_dump(),
            "techs_config": techs_config.model_dump(),
        }
    except DraftNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DuplicateTechnologyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except IndexError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid query results or missing data: {str(e)}",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error appending technology: {str(e)}",
        )


@router.post("/drafts/{config_id}/remove-technology")
async def remove_technology_from_draft(config_id: str, request: RemoveTechnologyRequest) -> dict:
    """Remove one technology from an existing draft TechsConfig."""
    try:
        removed_technology = technology_assembly_service.remove_technology_from_draft(
            config_id=config_id,
            technology_iri=request.technology_iri,
        )
        techs_config = technology_assembly_service.get_draft(config_id)

        return {
            "status": "success",
            "config_id": config_id,
            "removed_technology": removed_technology.model_dump(),
            "techs_config": techs_config.model_dump(),
        }
    except DraftNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TechnologyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error removing technology: {str(e)}",
        )


@router.get("/drafts/{config_id}/yaml")
async def preview_draft_yaml(config_id: str) -> dict:
    """Preview draft TechsConfig as YAML text without writing a file."""
    try:
        techs_config = technology_assembly_service.get_draft(config_id)
        yaml_content = technology_assembly_service.preview_draft_yaml(config_id)

        return {
            "status": "success",
            "config_id": config_id,
            "yaml": yaml_content,
            "techs_config": techs_config.model_dump(),
        }
    except DraftNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating YAML preview: {str(e)}",
        )


@router.post("/drafts/{config_id}/export")
async def export_draft_to_yaml(config_id: str) -> Response:
    """Return draft TechsConfig as downloadable YAML file."""
    try:
        yaml_content = technology_assembly_service.preview_draft_yaml(config_id)
        safe_config_id = "".join(
            character if character.isalnum() or character in {"-", "_"} else "_"
            for character in config_id
        )
        filename = f"techs-{safe_config_id}.yaml"

        return Response(
            content=yaml_content,
            media_type="application/x-yaml",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except DraftNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error exporting draft techs config: {str(e)}",
        )


@router.post("/drafts/{config_id}/export-csv")
async def export_draft_to_csv(config_id: str) -> Response:
    """Return draft TechsConfig as downloadable CSV file."""
    try:
        csv_content = technology_assembly_service.export_draft_csv(config_id)
        safe_config_id = "".join(
            character if character.isalnum() or character in {"-", "_"} else "_"
            for character in config_id
        )
        filename = f"techs-{safe_config_id}.csv"

        return Response(
            content=csv_content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except DraftNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error exporting draft techs CSV: {str(e)}",
        )
    
    
@router.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}
