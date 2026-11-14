from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import List, Dict, Any
from datetime import datetime, timezone

from routers.projects import PROJECTS_DB

router = APIRouter(
    prefix="/api/v1/portfolio",
    tags=["Módulo 3.5 - Portafolio Profesional Público y Ley N.° 29733 (HU11)"],
)


def _generate_seal_code(project_id: str) -> str:
    clean_id = str(project_id).replace("-", "").upper()
    return f"FISI-2026-{clean_id[:6]}"


class PortfolioPrivacyUpdateRequest(BaseModel):
    student_email: EmailStr
    consent_law_29733: bool = Field(
        ...,
        description="True para autorizar publicación en portafolio público; False para revocar y ocultar de inmediato (Ley N.° 29733).",
    )

    @field_validator("student_email")
    @classmethod
    def check_unmsm_domain(cls, v: str) -> str:
        clean = v.strip().lower()
        if not clean.endswith("@unmsm.edu.pe"):
            raise ValueError("El correo debe pertenecer al dominio institucional @unmsm.edu.pe")
        return clean


@router.get(
    "/{student_identifier}",
    summary="HU11: Consultar portafolio público verificado de un estudiante (Reclutadores / CV / LinkedIn)",
)
def get_public_student_portfolio(student_identifier: str):
    clean_id = student_identifier.strip().lower()
    if "@" not in clean_id:
        target_email = f"{clean_id}@unmsm.edu.pe"
    else:
        target_email = clean_id

    if not target_email.endswith("@unmsm.edu.pe"):
        raise HTTPException(
            status_code=400,
            detail="El identificador consultado debe corresponder a una cuenta institucional @unmsm.edu.pe.",
        )

    # Doble filtro estricto (Privacy by Design): Validado por Docente + Consentimiento Ley N.° 29733 activo
    public_projects: List[Dict[str, Any]] = []
    consolidated_skills = set()

    for proj in PROJECTS_DB.values():
        if proj.get("student_email", "").lower() != target_email:
            continue

        is_validated = proj.get("status") == "Validado"
        has_consent = bool(proj.get("consent_law_29733")) is True

        if is_validated and has_consent:
            seal_code = proj.get("verification_code") or _generate_seal_code(proj["id"])
            proj["verification_code"] = seal_code

            for tech in proj.get("tech_stack", []):
                if tech and str(tech).strip():
                    consolidated_skills.add(str(tech).strip())

            public_projects.append(
                {
                    "project_id": proj.get("id"),
                    "title": proj.get("title"),
                    "course_name": proj.get("course_name"),
                    "cycle": proj.get("cycle"),
                    "semester": proj.get("semester", "2026-2"),
                    "github_url": proj.get("github_url"),
                    "tech_stack": proj.get("tech_stack", []),
                    "professional_summary": proj.get("professional_summary", ""),
                    "official_seal": {
                        "badge": "Validado por Docente - FISI UNMSM",
                        "verification_code": seal_code,
                        "validated_by_teacher": proj.get("teacher_email"),
                        "validated_at": proj.get("decision_at"),
                        "teacher_feedback": proj.get("teacher_feedback"),
                    },
                }
            )

    student_alias = target_email.split("@")[0]

    return {
        "institution": "Universidad Nacional Mayor de San Marcos - FISI",
        "student_email": target_email,
        "public_portfolio_slug": f"/portafolio/{student_alias}",
        "law_29733_compliant": True,
        "total_validated_projects": len(public_projects),
        "consolidated_tech_stack": sorted(list(consolidated_skills)),
        "validated_projects": public_projects,
    }


@router.patch(
    "/projects/{project_id}/privacy",
    summary="HU11 / R06: Activar o revocar consentimiento Ley N.° 29733 para ocultar/mostrar proyecto en portafolio público",
)
def update_project_privacy_consent(
    project_id: str, payload: PortfolioPrivacyUpdateRequest
):
    if project_id not in PROJECTS_DB:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado.")

    project = PROJECTS_DB[project_id]
    owner_email = project.get("student_email", "").lower()

    if owner_email and owner_email != payload.student_email:
        raise HTTPException(
            status_code=403,
            detail="Solo el estudiante titular del proyecto puede modificar su consentimiento de privacidad (Ley N.° 29733).",
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    project["consent_law_29733"] = payload.consent_law_29733
    project["consent_timestamp"] = now_iso

    is_publicly_visible = (
        project.get("status") == "Validado" and bool(project["consent_law_29733"]) is True
    )

    action_text = (
        "Consentimiento Ley N.° 29733 activado."
        if payload.consent_law_29733
        else "Consentimiento Ley N.° 29733 revocado: el proyecto ha sido ocultado del portafolio público de forma inmediata."
    )

    return {
        "message": action_text,
        "project_id": project_id,
        "consent_law_29733": project["consent_law_29733"],
        "updated_at": now_iso,
        "is_publicly_visible": is_publicly_visible,
    }


@router.get(
    "/verify/{verification_code}",
    summary="HU10 / HU11: Verificar autenticidad de un código de sello docente (FISI-2026-XXXXXX)",
)
def verify_official_teacher_seal(verification_code: str):
    clean_code = verification_code.strip().upper()

    for proj in PROJECTS_DB.values():
        proj_code = (proj.get("verification_code") or _generate_seal_code(proj["id"])).upper()
        if (
            proj_code == clean_code
            and proj.get("status") == "Validado"
            and bool(proj.get("consent_law_29733")) is True
        ):
            return {
                "valid_seal": True,
                "verification_code": proj_code,
                "badge": "Validado por Docente - FISI UNMSM",
                "project_title": proj.get("title"),
                "course_name": proj.get("course_name"),
                "student_email": proj.get("student_email"),
                "validated_by_teacher": proj.get("teacher_email"),
                "validated_at": proj.get("decision_at"),
                "tech_stack": proj.get("tech_stack", []),
            }

    raise HTTPException(
        status_code=404,
        detail="Código de verificación no encontrado o el proyecto no cuenta con publicación pública autorizada.",
    )