from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime, timezone
import uuid

from services.evidence_extractor import (
    extract_from_github,
    extract_from_pdf,
    extract_from_ipynb,
    MAX_CHARS_FOR_LLM,
)
from services.validators import is_institutional_email

router = APIRouter(prefix="/api/v1/projects", tags=["Módulo 3.2 - Proyectos y Evidencias"])

# Almacenamiento en memoria temporal mientras Demian y Bryan conectan Supabase
MOCK_PROJECTS_DB = {}


class ProjectCreateRequest(BaseModel):
    title: str
    course_name: str
    cycle: str
    semester: str = "2026-2"
    student_email: EmailStr
    teacher_email: EmailStr


@router.post("/", status_code=201)
def create_project_draft(payload: ProjectCreateRequest):
    """
    HU03: Como estudiante, quiero registrar un proyecto asociado a un curso y docente
    para incorporarlo a mi portafolio académico en estado 'Borrador'.
    """
    institutional_emails = (
        is_institutional_email(str(payload.student_email)),
        is_institutional_email(str(payload.teacher_email)),
    )
    if not all(institutional_emails):
        raise HTTPException(
            status_code=400,
            detail="Tanto el correo del estudiante como el del docente deben pertenecer al dominio @unmsm.edu.pe"
        )

    project_id = str(uuid.uuid4())
    new_project = {
        "id": project_id,
        "title": payload.title,
        "course_name": payload.course_name,
        "cycle": payload.cycle,
        "semester": payload.semester,
        "student_email": payload.student_email,
        "teacher_email": payload.teacher_email,
        "status": "Borrador",  # Estado inicial exigido por HU03
        "github_url": None,
        "extracted_evidence_text": None,
        "evidence_char_count": 0,
        "tech_stack": [],
        "professional_summary": None,
        "consent_law_29733": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    MOCK_PROJECTS_DB[project_id] = new_project
    return {
        "message": "Proyecto registrado exitosamente en estado Borrador (HU03).",
        "project": new_project,
    }


@router.post("/{project_id}/evidences")
async def upload_project_evidences(
    project_id: str,
    github_url: str = Form(..., description="URL pública del repositorio de GitHub"),
    evidence_file: Optional[UploadFile] = File(None, description="Reporte PDF o Notebook .ipynb opcional"),
):
    """
    HU04: Adjunta evidencias al proyecto (GitHub, .ipynb o .pdf), verifica accesibilidad pública
    y trunca el texto extraído para enviarlo al componente LLM (Módulo 3.3).
    """
    if project_id not in MOCK_PROJECTS_DB:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado.")

    # 1. Extraer texto desde el repositorio público de GitHub
    github_text = extract_from_github(github_url)
    combined_evidence = [github_text]

    # 2. Si el alumno adjuntó un PDF o Notebook (.ipynb), extraer también su contenido
    if evidence_file and evidence_file.filename:
        filename_lower = evidence_file.filename.lower()
        file_bytes = await evidence_file.read()

        if filename_lower.endswith(".pdf"):
            pdf_text = extract_from_pdf(file_bytes)
            combined_evidence.append(f"\n=== CONTENIDO REPORTE PDF ({evidence_file.filename}) ===\n{pdf_text}")
        elif filename_lower.endswith(".ipynb"):
            ipynb_text = extract_from_ipynb(file_bytes)
            combined_evidence.append(f"\n=== CONTENIDO NOTEBOOK ({evidence_file.filename}) ===\n{ipynb_text}")
        else:
            raise HTTPException(
                status_code=400,
                detail="Formato de archivo no soportado. Solo se admiten archivos .pdf o .ipynb"
            )

    # 3. Aplicar truncado inteligente para proteger la cuota de tokens del LLM (R03)
    final_clean_text = "\n".join(combined_evidence)[:MAX_CHARS_FOR_LLM]

    # 4. Guardar evidencia en el proyecto lista para que el módulo 3.3 (Erick) la procese con IA
    project = MOCK_PROJECTS_DB[project_id]
    project["github_url"] = github_url
    project["extracted_evidence_text"] = final_clean_text
    project["evidence_char_count"] = len(final_clean_text)

    return {
        "message": "Evidencias validadas y preprocesadas correctamente (HU04).",
        "project_id": project_id,
        "github_url": github_url,
        "characters_extracted": len(final_clean_text),
        "max_characters_allowed": MAX_CHARS_FOR_LLM,
        "preview_for_llm": final_clean_text[:500] + "...",
    }


@router.get("/")
def list_projects():
    """Lista todos los proyectos registrados para pruebas de integración."""
    return list(MOCK_PROJECTS_DB.values())
