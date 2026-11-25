from fastapi import APIRouter, Query
from typing import Any, Dict, List, Optional

from routers.projects import PROJECTS_DB

router = APIRouter(
    prefix="/api/v1/analytics",
    tags=["Módulo 3.6 - Panel Analítico y Gerencial para Autoridades FISI (HU12, HU13)"],
)

SLA_TARGET_SECONDS = 300


def _matches_filter(value: Any, expected: Optional[str]) -> bool:
    if expected is None or not expected.strip():
        return True
    if value is None:
        return False
    return str(value).strip().casefold() == expected.strip().casefold()


def _filter_projects(
    course_name: Optional[str] = None,
    cycle: Optional[str] = None,
    semester: Optional[str] = None,
) -> List[Dict[str, Any]]:
    matched: List[Dict[str, Any]] = []
    for proj in PROJECTS_DB.values():
        if not _matches_filter(proj.get("course_name"), course_name):
            continue
        if not _matches_filter(proj.get("cycle"), cycle):
            continue
        if not _matches_filter(proj.get("semester", "2026-2"), semester):
            continue
        matched.append(proj)
    return matched


def _build_top_technologies(validated_projects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    total_validated = len(validated_projects)
    if total_validated == 0:
        return []

    tech_counts: Dict[str, int] = {}
    for proj in validated_projects:
        unique_project_techs = {
            str(tech).strip()
            for tech in (proj.get("tech_stack") or [])
            if tech is not None and str(tech).strip()
        }
        for tech in unique_project_techs:
            tech_counts[tech] = tech_counts.get(tech, 0) + 1

    ranking = [
        {
            "technology": tech,
            "project_count": count,
            "percentage": round((count / total_validated) * 100, 2),
        }
        for tech, count in tech_counts.items()
    ]
    ranking.sort(key=lambda item: (-item["project_count"], item["technology"].casefold()))
    return ranking


def _compute_avg_review_seconds(validated_projects: List[Dict[str, Any]]) -> Optional[float]:
    review_times = [
        float(sec)
        for proj in validated_projects
        for sec in [proj.get("active_review_seconds")]
        if isinstance(sec, (int, float)) and not isinstance(sec, bool)
    ]
    if not review_times:
        return None
    return round(sum(review_times) / len(review_times), 2)


def _build_course_breakdown(filtered_projects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped_all: Dict[str, List[Dict[str, Any]]] = {}
    grouped_validated: Dict[str, List[Dict[str, Any]]] = {}

    for proj in filtered_projects:
        course = str(proj.get("course_name") or "Sin asignatura").strip()
        grouped_all.setdefault(course, []).append(proj)
        if proj.get("status") == "Validado":
            grouped_validated.setdefault(course, []).append(proj)

    courses_report: List[Dict[str, Any]] = []
    for course_name, validated_list in grouped_validated.items():
        all_list = grouped_all.get(course_name, validated_list)
        total_course_projects = len(all_list)
        total_course_validated = len(validated_list)
        avg_seconds = _compute_avg_review_seconds(validated_list)
        public_count = sum(1 for p in validated_list if bool(p.get("consent_law_29733")))

        courses_report.append(
            {
                "course_name": course_name,
                "total_projects": total_course_projects,
                "total_validated_projects": total_course_validated,
                "validation_rate_percent": round(
                    (total_course_validated / total_course_projects) * 100, 2
                )
                if total_course_projects > 0
                else 0.0,
                "avg_review_seconds": avg_seconds,
                "sla_compliant": (avg_seconds <= SLA_TARGET_SECONDS)
                if avg_seconds is not None
                else None,
                "public_portfolio_percent": round(
                    (public_count / total_course_validated) * 100, 2
                )
                if total_course_validated > 0
                else 0.0,
                "cycles": sorted(
                    {
                        str(p.get("cycle")).strip()
                        for p in validated_list
                        if p.get("cycle") is not None and str(p.get("cycle")).strip()
                    }
                ),
                "semesters": sorted(
                    {
                        str(p.get("semester", "2026-2")).strip()
                        for p in validated_list
                        if p.get("semester", "2026-2")
                    }
                ),
                "top_technologies": _build_top_technologies(validated_list),
            }
        )

    courses_report.sort(
        key=lambda item: (-item["total_validated_projects"], item["course_name"].casefold())
    )
    return courses_report


@router.get(
    "/dashboard",
    summary="HU12 / HU13: Consolidar KPIs curriculares, SLA docente y ranking de tecnologías validadas",
)
def get_analytics_dashboard(
    course_name: Optional[str] = Query(
        default=None, description="Filtrar métricas por nombre exacto de la asignatura (HU13)."
    ),
    cycle: Optional[str] = Query(
        default=None, description="Filtrar métricas por ciclo académico (ej. '8', '9')."
    ),
    semester: Optional[str] = Query(
        default=None, description="Filtrar métricas por semestre académico (ej. '2026-2')."
    ),
):
    filtered_projects = _filter_projects(
        course_name=course_name, cycle=cycle, semester=semester
    )
    validated_projects = [
        proj for proj in filtered_projects if proj.get("status") == "Validado"
    ]

    total_projects = len(filtered_projects)
    total_validated = len(validated_projects)

    validation_rate_percent = (
        round((total_validated / total_projects) * 100, 2) if total_projects > 0 else 0.0
    )
    avg_review_seconds = _compute_avg_review_seconds(validated_projects)
    public_count = sum(
        1 for proj in validated_projects if bool(proj.get("consent_law_29733"))
    )
    public_portfolio_percent = (
        round((public_count / total_validated) * 100, 2) if total_validated > 0 else 0.0
    )

    return {
        "institution": "Universidad Nacional Mayor de San Marcos - FISI",
        "filters_applied": {
            "course_name": course_name,
            "cycle": cycle,
            "semester": semester,
        },
        "total_projects": total_projects,
        "total_validated_projects": total_validated,
        "validation_rate_percent": validation_rate_percent,
        "avg_review_seconds": avg_review_seconds,
        "sla_target_seconds": SLA_TARGET_SECONDS,
        "sla_compliant": (avg_review_seconds <= SLA_TARGET_SECONDS)
        if avg_review_seconds is not None
        else None,
        "public_portfolio_count": public_count,
        "public_portfolio_percent": public_portfolio_percent,
        "top_technologies": _build_top_technologies(validated_projects),
        "courses_summary": _build_course_breakdown(filtered_projects),
    }


@router.get(
    "/syllabus-report",
    summary="HU13: Reporte curricular consolidado por asignatura para actualización de sílabos FISI",
)
def get_syllabus_report(
    course_name: Optional[str] = Query(
        default=None, description="Filtrar reporte curricular por asignatura."
    ),
    cycle: Optional[str] = Query(
        default=None, description="Filtrar reporte curricular por ciclo académico."
    ),
    semester: Optional[str] = Query(
        default=None, description="Filtrar reporte curricular por semestre académico."
    ),
):
    filtered_projects = _filter_projects(
        course_name=course_name, cycle=cycle, semester=semester
    )
    validated_projects = [
        proj for proj in filtered_projects if proj.get("status") == "Validado"
    ]
    courses_report = _build_course_breakdown(filtered_projects)

    return {
        "institution": "Universidad Nacional Mayor de San Marcos - FISI",
        "report_type": "Reporte Curricular de Adopción Tecnológica para Sílabos (I-02)",
        "filters_applied": {
            "course_name": course_name,
            "cycle": cycle,
            "semester": semester,
        },
        "total_projects": len(filtered_projects),
        "total_validated_projects": len(validated_projects),
        "total_courses_with_validated_projects": len(courses_report),
        "courses": courses_report,
    }