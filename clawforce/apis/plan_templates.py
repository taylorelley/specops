"""API endpoints for the plan templates marketplace (curated catalog + user-managed custom entries)."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from clawforce.auth import get_current_user
from clawlib.registry import get_plan_template_registry

logger = logging.getLogger(__name__)

router = APIRouter(tags=["plan-templates"])


class PlanTemplateColumnModel(BaseModel):
    title: str
    position: int | None = None


class PlanTemplateTaskModel(BaseModel):
    title: str
    description: str = ""
    column: str = ""


class AddPlanTemplateRequest(BaseModel):
    """Request body for adding or updating a plan template entry."""

    id: str = Field(..., description="Unique slug identifier, e.g. my-plan")
    name: str
    description: str = ""
    author: str = ""
    categories: list[str] = []
    columns: list[PlanTemplateColumnModel] = []
    tasks: list[PlanTemplateTaskModel] = []


@router.get("/api/plan-templates")
async def list_plan_templates(
    _: dict = Depends(get_current_user),
):
    """Return the full plan template catalog (bundled + custom merged)."""
    return get_plan_template_registry().list_entries()


@router.get("/api/plan-templates/custom")
async def list_custom_plan_templates(
    _: dict = Depends(get_current_user),
):
    """Return user-managed custom plan templates only."""
    return get_plan_template_registry().list_custom_entries()


@router.get("/api/plan-templates/{template_id:path}")
async def get_plan_template(
    template_id: str,
    _: dict = Depends(get_current_user),
):
    """Return a single plan template by id."""
    entry = get_plan_template_registry().get_entry(template_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Plan template not found"
        )
    return entry


@router.post("/api/plan-templates", status_code=status.HTTP_201_CREATED)
async def add_custom_plan_template(
    body: AddPlanTemplateRequest,
    _: dict = Depends(get_current_user),
):
    """Add a user-managed custom plan template."""
    registry = get_plan_template_registry()
    if registry.get_entry(body.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Plan template id '{body.id}' already exists in the catalog",
        )
    entry = body.model_dump(exclude_none=True)
    registry.add_custom_entry(entry)
    return entry


@router.put("/api/plan-templates/{template_id:path}")
async def update_custom_plan_template(
    template_id: str,
    body: AddPlanTemplateRequest,
    _: dict = Depends(get_current_user),
):
    """Update a custom plan template by id."""
    if body.id != template_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL id and body id must match",
        )
    entry = body.model_dump(exclude_none=True)
    entry["id"] = template_id
    updated = get_plan_template_registry().update_custom_entry(template_id, entry)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Custom plan template '{template_id}' not found",
        )
    return entry


@router.delete("/api/plan-templates/{template_id:path}")
async def delete_custom_plan_template(
    template_id: str,
    _: dict = Depends(get_current_user),
):
    """Delete a custom plan template by id."""
    removed = get_plan_template_registry().delete_custom_entry(template_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Custom plan template '{template_id}' not found",
        )
    return {"ok": True, "id": template_id}
