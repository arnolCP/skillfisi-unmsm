from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Annotated, Optional, List, Literal
from datetime import datetime, timezone
from math import ceil

from routers.auth_profiles import AuthorizedUser, require_role
from routers.projects import PROJECTS_DB
from services.quality_metrics import MAX_TEACHER_ACTIVE_SECONDS, teacher_active_time_seconds

router = APIRouter(
    prefix="/api/v1/reviews",
    tags=["Módulo 3.4 - Validación Docente SLA <= 5 min (HU07)"],
)

TeacherUser = Annotated[AuthorizedUser, Depends(require_role("Docente"))]


class TeacherDecisionRequest(BaseModel):
    decision: Literal["Validado", "Observado"]
    teacher_feedback: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Observación o comentario académico del docente titular",
    )
    validated_technologies: Optional[List[str]] = Field(
        default=None,
        description="Lista final de tecnologías acreditadas por el docente",
    )

def _assigned_project(project_id: str, teacher: AuthorizedUser) -> dict:
    project = PROJECTS_DB.get(project_id)
    if project is None or project["teacher_email"].casefold() != teacher.email.casefold():
        raise HTTPException(status_code=404, detail="Proyecto no encontrado.")
    return project


@router.get(
    "/pending",
    summary="HU07: Listar proyectos pendientes en la bandeja del docente ('En Revisión')",
)
def get_pending_reviews(teacher: TeacherUser):
    pending = [
        p for p in PROJECTS_DB.values()
        if p["status"] == "En Revisión"
        and p["teacher_email"].casefold() == teacher.email.casefold()
    ]

    return {
        "total_pending": len(pending),
        "sla_target_seconds": MAX_TEACHER_ACTIVE_SECONDS,
        "projects": pending,
    }


@router.post(
    "/{project_id}/open",
    summary="HU07 Telemetría: Registrar inicio de revisión activa en pantalla (opened_by_teacher_at)",
)
def mark_project_opened_by_teacher(project_id: str, teacher: TeacherUser):
    project = _assigned_project(project_id, teacher)
    if project["status"] != "En Revisión":
        raise HTTPException(
            status_code=400,
            detail=f"El proyecto debe estar 'En Revisión' para iniciar evaluación (estado actual: {project['status']}).",
        )

    if project["opened_by_teacher_at"] is None:
        project["opened_by_teacher_at"] = datetime.now(timezone.utc).isoformat()

    return {
        "message": "Inicio de revisión docente registrado para telemetría SLA.",
        "project_id": project_id,
        "opened_by_teacher_at": project["opened_by_teacher_at"],
        "sla_limit_seconds": MAX_TEACHER_ACTIVE_SECONDS,
    }


@router.post(
    "/{project_id}/decision",
    summary="HU07: Emitir veredicto docente ('Validado' u 'Observado') y calcular SLA <= 300s",
)
def submit_teacher_decision(project_id: str, payload: TeacherDecisionRequest, teacher: TeacherUser):
    project = _assigned_project(project_id, teacher)
    if project["status"] != "En Revisión":
        raise HTTPException(
            status_code=400,
            detail=f"Solo se pueden evaluar proyectos en estado 'En Revisión' (estado actual: {project['status']}).",
        )

    if payload.decision == "Observado" and (
        not payload.teacher_feedback or len(payload.teacher_feedback.strip()) < 5
    ):
        raise HTTPException(
            status_code=400,
            detail="Al observar un proyecto es obligatorio detallar la retroalimentación para el estudiante.",
        )

    now_dt = datetime.now(timezone.utc)
    decision_at_iso = now_dt.isoformat()

    if project["opened_by_teacher_at"] is None:
        raise HTTPException(status_code=409, detail="Abre el proyecto antes de emitir una decisión.")
    opened_dt = datetime.fromisoformat(project["opened_by_teacher_at"])
    elapsed_seconds = ceil(teacher_active_time_seconds(opened_dt, now_dt))

    if payload.validated_technologies is not None:
        clean_techs = [t.strip() for t in payload.validated_technologies if t.strip()]
        if clean_techs:
            project["tech_stack"] = clean_techs

    project["status"] = payload.decision
    project["decision_at"] = decision_at_iso
    project["active_review_seconds"] = elapsed_seconds
    project["teacher_feedback"] = (
        payload.teacher_feedback.strip() if payload.teacher_feedback else "Acreditación conforme."
    )

    sla_compliant = elapsed_seconds <= MAX_TEACHER_ACTIVE_SECONDS

    return {
        "message": f"Proyecto '{payload.decision}' exitosamente por el docente.",
        "project_id": project_id,
        "new_status": payload.decision,
        "telemetry": {
            "submitted_at": project.get("submitted_at"),
            "opened_by_teacher_at": project.get("opened_by_teacher_at"),
            "decision_at": decision_at_iso,
            "active_review_seconds": elapsed_seconds,
            "sla_max_seconds": MAX_TEACHER_ACTIVE_SECONDS,
            "sla_compliant": sla_compliant,
        },
        "project": project,
    }
