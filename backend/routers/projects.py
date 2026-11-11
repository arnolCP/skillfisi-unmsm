from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List, Dict
from datetime import datetime, timezone
import uuid

import services.evidence_extractor as extractor
from services.evidence_extractor import (
    extract_from_github,
    extract_from_pdf,
    extract_from_ipynb,
)

MAX_CHARS_FOR_LLM = getattr(extractor, "MAX_CHARS_FOR_LLM", 12000)

router = APIRouter(
    prefix="/api/v1/projects",
    tags=["Módulo 3.2 - Proyectos, Evidencias y Envío HITL (HU03, HU04, HU06)"],
)

# Almacenamiento en memoria compartido con el módulo de revisión docente (3.4)
PROJECTS_DB: Dict[str, dict] = {}


def consolidate_and_truncate(blocks: List[str], max_chars: int = MAX_CHARS_FOR_LLM) -> str:
    combined = "\n\n".join(b.strip() for b in blocks if b and b.strip())
    if len(combined) > max_chars:
        return combined[:max_chars]
    return combined


def _validate_unmsm_email(email: str) -> str:
    clean_email = email.strip().lower()
    if not clean_email.endswith("@unmsm.edu.pe"):
        raise ValueError("El correo debe pertenecer al dominio institucional @unmsm.edu.pe")
    return clean_email


class ProjectCreateRequest(BaseModel):
    title: str = Field(..., min_length=5, max_length=255)
    course_name: str = Field(..., min_length=3, max_length=255)
    cycle: str = Field(..., min_length=1, max_length=30)
    student_email: EmailStr
    teacher_email: EmailStr

    @field_validator("student_email", "teacher_email")
    @classmethod
    def check_institutional_domain(cls, v: str) -> str:
        return _validate_unmsm_email(v)


class ProjectSubmitReviewRequest(BaseModel):
    tech_stack: List[str] = Field(
        ...,
        min_length=1,
        description="Lista de tecnologías revisadas y editadas por el estudiante (Human-in-the-Loop)",
    )
    professional_summary: str = Field(
        ...,
        min_length=20,
        max_length=2500,
        description="Resumen ejecutivo revisado y editado por el estudiante",
    )
    consent_law_29733: bool = Field(
        ...,
        description="Consentimiento expreso de la Ley N.° 29733 de Protección de Datos Personales",
    )


@router.post("/", status_code=201, summary="HU03: Registrar proyecto en estado Borrador")
def create_project(payload: ProjectCreateRequest):
    project_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    project_record = {
        "id": project_id,
        "title": payload.title.strip(),
        "course_name": payload.course_name.strip(),
        "cycle": payload.cycle.strip(),
        "semester": "2026-2",
        "student_email": payload.student_email,
        "teacher_email": payload.teacher_email,
        "status": "Borrador",
        "github_url": None,
        "extracted_evidence_text": "",
        "evidence_char_count": 0,
        "tech_stack": [],
        "professional_summary": "",
        "consent_law_29733": False,
        "consent_timestamp": None,
        "submitted_at": None,
        "opened_by_teacher_at": None,
        "decision_at": None,
        "active_review_seconds": None,
        "teacher_feedback": None,
        "created_at": now_iso,
    }
    PROJECTS_DB[project_id] = project_record
    return {
        "message": "Proyecto creado exitosamente en estado Borrador",
        "project": project_record,
    }


@router.post(
    "/{project_id}/evidences",
    summary="HU04: Adjuntar URL de GitHub y/o archivos PDF/IPYNB y truncar texto",
)
async def upload_project_evidences(
    project_id: str,
    github_url: Optional[str] = Form(None),
    evidence_file: Optional[UploadFile] = File(None),
):
    if project_id not in PROJECTS_DB:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado.")

    if not github_url and not evidence_file:
        raise HTTPException(
            status_code=400,
            detail="Debes proporcionar al menos un enlace público de GitHub o un archivo (.pdf / .ipynb).",
        )

    extracted_blocks: List[str] = []

    if github_url and github_url.strip():
        gh_text = extract_from_github(github_url.strip())
        extracted_blocks.append(gh_text)
        PROJECTS_DB[project_id]["github_url"] = github_url.strip()

    if evidence_file:
        filename = (evidence_file.filename or "").lower()
        file_bytes = await evidence_file.read()

        if filename.endswith(".pdf"):
            pdf_text = extract_from_pdf(file_bytes)
            extracted_blocks.append(f"ARCHIVO PDF ({evidence_file.filename}):\n{pdf_text}")
        elif filename.endswith(".ipynb"):
            nb_text = extract_from_ipynb(file_bytes)
            extracted_blocks.append(f"JUPYTER NOTEBOOK ({evidence_file.filename}):\n{nb_text}")
        else:
            raise HTTPException(
                status_code=400,
                detail="Formato de archivo no soportado. Solo se admiten archivos .pdf o .ipynb.",
            )

    final_text = consolidate_and_truncate(extracted_blocks, max_chars=MAX_CHARS_FOR_LLM)
    PROJECTS_DB[project_id]["extracted_evidence_text"] = final_text
    PROJECTS_DB[project_id]["evidence_char_count"] = len(final_text)

    return {
        "message": "Evidencias procesadas y truncadas exitosamente",
        "project_id": project_id,
        "char_count": len(final_text),
        "max_allowed_chars": MAX_CHARS_FOR_LLM,
        "extracted_text_preview": final_text[:600],
        "extracted_evidence_text": final_text,
    }


@router.put(
    "/{project_id}/submit-review",
    summary="HU06: Guardar edición Human-in-the-Loop, validar Ley N.° 29733 y enviar a Revisión Docente",
)
def submit_project_for_teacher_review(project_id: str, payload: ProjectSubmitReviewRequest):
    if project_id not in PROJECTS_DB:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado.")

    if not payload.consent_law_29733:
        raise HTTPException(
            status_code=400,
            detail="Cumplimiento legal obligatorio: Debes aceptar el consentimiento de la Ley N.° 29733 para enviar el proyecto a revisión.",
        )

    clean_stack = [tech.strip() for tech in payload.tech_stack if tech.strip()]
    if not clean_stack:
        raise HTTPException(
            status_code=400,
            detail="El proyecto debe incluir al menos una tecnología validada por el estudiante.",
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    project = PROJECTS_DB[project_id]

    project["tech_stack"] = clean_stack
    project["professional_summary"] = payload.professional_summary.strip()
    project["consent_law_29733"] = True
    project["consent_timestamp"] = now_iso
    project["status"] = "En Revisión"
    project["submitted_at"] = now_iso

    return {
        "message": "Proyecto enviado exitosamente a la bandeja del docente titular (Estado: En Revisión).",
        "project": project,
    }


@router.get(
    "/student/{student_email}",
    summary="Listar proyectos registrados por un estudiante",
)
def list_student_projects(student_email: str):
    clean_email = student_email.strip().lower()
    if not clean_email.endswith("@unmsm.edu.pe"):
        raise HTTPException(
            status_code=400,
            detail="El correo consultado debe pertenecer al dominio @unmsm.edu.pe",
        )

    projects = [
        p for p in PROJECTS_DB.values() if p["student_email"].lower() == clean_email
    ]
    return {
        "student_email": clean_email,
        "total": len(projects),
        "projects": projects,
    }


@router.get("/{project_id}", summary="Obtener detalle completo de un proyecto por ID")
def get_project_detail(project_id: str):
    if project_id not in PROJECTS_DB:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado.")
    return PROJECTS_DB[project_id]