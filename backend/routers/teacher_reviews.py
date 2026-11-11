from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List, Literal
from datetime import datetime, timezone

from routers.projects import PROJECTS_DB

router = APIRouter(
    prefix="/api/v1/reviews",
    tags=["Módulo 3.4 - Validación Docente SLA <= 5 min (HU07)"],
)

SLA_MAX_REVIEW_SECONDS = 300  # 5 minutos (300 segundos)


class TeacherDecisionRequest(BaseModel):
    teacher_email: EmailStr
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

    @field_validator("teacher_email")
    @classmethod
    def check_teacher_domain(cls, v: str) -> str:
        clean = v.strip().lower()
        if not clean.endswith("@unmsm.edu.pe"):
            raise ValueError("El docente debe utilizar su correo institucional @unmsm.edu.pe")
        return clean


@router.get(
    "/pending",
    summary="HU07: Listar proyectos pendientes en la bandeja del docente ('En Revisión')",
)
def get_pending_reviews(
    teacher_email: Optional[str] = Query(
        default=None,
        description="Filtrar por correo institucional del docente (@unmsm.edu.pe)",
    )
):
    pending = [
        p for p in PROJECTS_DB.values() if p.get("status") == "En Revisión"
    ]

    if teacher_email:
        clean_teacher = teacher_email.strip().lower()
        if not clean_teacher.endswith("@unmsm.edu.pe"):
            raise HTTPException(
                status_code=400,
                detail="El correo del docente debe pertenecer al dominio @unmsm.edu.pe",
            )
        pending = [
            p for p in pending if p.get("teacher_email", "").lower() == clean_teacher
        ]

    return {
        "total_pending": len(pending),
        "sla_target_seconds": SLA_MAX_REVIEW_SECONDS,
        "projects": pending,
    }


@router.post(
    "/{project_id}/open",
    summary="HU07 Telemetría: Registrar inicio de revisión activa en pantalla (opened_by_teacher_at)",
)
def mark_project_opened_by_teacher(project_id: str):
    if project_id not in PROJECTS_DB:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado.")

    project = PROJECTS_DB[project_id]
    if project["status"] != "En Revisión":
        raise HTTPException(
            status_code=400,
            detail=f"El proyecto debe estar 'En Revisión' para iniciar evaluación (estado actual: {project['status']}).",
        )

    opened_at_iso = datetime.now(timezone.utc).isoformat()
    project["opened_by_teacher_at"] = opened_at_iso

    return {
        "message": "Inicio de revisión docente registrado para telemetría SLA.",
        "project_id": project_id,
        "opened_by_teacher_at": opened_at_iso,
        "sla_limit_seconds": SLA_MAX_REVIEW_SECONDS,
    }


@router.post(
    "/{project_id}/decision",
    summary="HU07: Emitir veredicto docente ('Validado' u 'Observado') y calcular SLA <= 300s",
)
def submit_teacher_decision(project_id: str, payload: TeacherDecisionRequest):
    if project_id not in PROJECTS_DB:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado.")

    project = PROJECTS_DB[project_id]
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

    # Si no se llamó antes a /open, tomamos una apertura por defecto para calcular la telemetría
    if project.get("opened_by_teacher_at"):
        opened_dt = datetime.fromisoformat(project["opened_by_teacher_at"])
        elapsed_seconds = max(1, int((now_dt - opened_dt).total_seconds()))
    else:
        project["opened_by_teacher_at"] = decision_at_iso
        elapsed_seconds = 1

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

    sla_compliant = elapsed_seconds <= SLA_MAX_REVIEW_SECONDS

    return {
        "message": f"Proyecto '{payload.decision}' exitosamente por el docente.",
        "project_id": project_id,
        "new_status": payload.decision,
        "telemetry": {
            "submitted_at": project.get("submitted_at"),
            "opened_by_teacher_at": project.get("opened_by_teacher_at"),
            "decision_at": decision_at_iso,
            "active_review_seconds": elapsed_seconds,
            "sla_max_seconds": SLA_MAX_REVIEW_SECONDS,
            "sla_compliant": sla_compliant,
        },
        "project": project,
    }