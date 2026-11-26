from typing import Any, Dict, List, Optional
from services.llm_service import TAXONOMY_MAP

CURRICULAR_CATEGORIES: List[str] = [
    "Lenguajes de Programación",
    "Frameworks y Librerías",
    "Bases de Datos",
    "Cloud y DevOps",
    "Ciencia de Datos / IA",
]


class AnalyticsEngineService:
    """
    Motor de agregación estadística BI (Paquete 3.6 / HU12 - HU13).
    Cruza proyectos en estado 'Validado' con el diccionario taxonómico TAXONOMY_MAP
    del Módulo 3.3 sin invocar llamadas externas al LLM (costo de tokens S/ 0.00).
    """

    def classify_technology(self, tech_name: str) -> str:
        clean_tech = tech_name.strip()
        key = clean_tech.lower()

        if key in TAXONOMY_MAP:
            return TAXONOMY_MAP[key]

        for map_key, map_cat in TAXONOMY_MAP.items():
            if map_key in key:
                return map_cat

        return "Frameworks y Librerías"

    def filter_validated_projects(
        self,
        projects: List[Dict[str, Any]],
        course_name: Optional[str] = None,
        cycle: Optional[str] = None,
        semester: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Filtra exclusivamente proyectos con status == 'Validado' y filtros curriculares opcionales."""
        filtered: List[Dict[str, Any]] = []

        for proj in projects:
            status = str(proj.get("status", "")).strip()
            if status != "Validado":
                continue

            if course_name and str(proj.get("course_name", "")).strip().lower() != course_name.strip().lower():
                continue

            if cycle and str(proj.get("cycle", "")).strip().lower() != cycle.strip().lower():
                continue

            if semester and str(proj.get("semester", "")).strip().lower() != semester.strip().lower():
                continue

            filtered.append(proj)

        return filtered

    def _extract_unique_project_stack(self, project: Dict[str, Any]) -> List[str]:
        """
        Obtiene las tecnologías únicas de un proyecto evitando doble conteo
        de etiquetas repetidas dentro del mismo registro.
        """
        raw_stack = project.get("stack_tecnologico") or project.get("technologies") or []
        if isinstance(raw_stack, str):
            raw_stack = [item.strip() for item in raw_stack.split(",") if item.strip()]

        seen_lower = set()
        unique_stack: List[str] = []
        for tech in raw_stack:
            clean = str(tech).strip()
            if clean and clean.lower() not in seen_lower:
                seen_lower.add(clean.lower())
                unique_stack.append(clean)

        return unique_stack

    def calculate_law_29733_compliance(
        self, validated_projects: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Calcula métricas de cumplimiento normativo de la Ley N.° 29733 sobre proyectos validados."""
        total_validated = len(validated_projects)
        public_authorized = 0

        for proj in validated_projects:
            has_consent = bool(
                proj.get("consent_law_29733", False) or proj.get("is_public", False)
            )
            if has_consent:
                public_authorized += 1

        private_restricted = total_validated - public_authorized
        public_percentage = (
            round((public_authorized / total_validated) * 100, 2)
            if total_validated > 0
            else 0.0
        )

        return {
            "total_validated_projects": total_validated,
            "public_authorized_count": public_authorized,
            "private_restricted_count": private_restricted,
            "public_authorization_percent": public_percentage,
        }

    def compute_category_and_tech_metrics(
        self,
        projects: List[Dict[str, Any]],
        course_name: Optional[str] = None,
        cycle: Optional[str] = None,
        semester: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Calcula frecuencias absolutas, porcentajes de adopción sobre el total de proyectos
        validados, ranking tecnológico y cumplimiento de Ley N.° 29733.
        """
        validated = self.filter_validated_projects(
            projects, course_name=course_name, cycle=cycle, semester=semester
        )
        total_validated = len(validated)

        tech_counts: Dict[str, int] = {}
        tech_category_map: Dict[str, str] = {}
        category_project_sets: Dict[str, set] = {cat: set() for cat in CURRICULAR_CATEGORIES}
        category_tag_counts: Dict[str, int] = {cat: 0 for cat in CURRICULAR_CATEGORIES}

        for idx, proj in enumerate(validated):
            proj_key = proj.get("id") or f"proj_{idx}"
            unique_stack = self._extract_unique_project_stack(proj)

            for tech in unique_stack:
                category = self.classify_technology(tech)
                tech_counts[tech] = tech_counts.get(tech, 0) + 1
                tech_category_map[tech] = category
                category_tag_counts[category] += 1
                category_project_sets[category].add(proj_key)

        # Ranking de tecnologías ordenado por frecuencia descendente
        technology_ranking = [
            {
                "technology": tech,
                "category": tech_category_map[tech],
                "absolute_frequency": count,
                "adoption_percent": round((count / total_validated) * 100, 2)
                if total_validated > 0
                else 0.0,
            }
            for tech, count in sorted(
                tech_counts.items(), key=lambda item: (-item[1], item[0].lower())
            )
        ]

        # Consolidado por las 5 dimensiones curriculares
        categories_summary = []
        for cat in CURRICULAR_CATEGORIES:
            projects_with_cat = len(category_project_sets[cat])
            categories_summary.append(
                {
                    "category": cat,
                    "projects_count": projects_with_cat,
                    "total_mentions": category_tag_counts[cat],
                    "participation_percent": round(
                        (projects_with_cat / total_validated) * 100, 2
                    )
                    if total_validated > 0
                    else 0.0,
                }
            )

        law_29733_metrics = self.calculate_law_29733_compliance(validated)

        return {
            "filters_applied": {
                "course_name": course_name,
                "cycle": cycle,
                "semester": semester,
            },
            "total_validated_projects": total_validated,
            "categories_distribution": categories_summary,
            "technology_ranking": technology_ranking,
            "law_29733_compliance": law_29733_metrics,
        }

    def build_syllabus_gap_report(
        self, projects: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Genera el agregado curricular agrupado por asignatura y ciclo
        para el endpoint GET /api/v1/analytics/syllabus-report (HU13).
        """
        validated = self.filter_validated_projects(projects)
        grouped: Dict[tuple, List[Dict[str, Any]]] = {}

        for proj in validated:
            course = str(proj.get("course_name") or "Sin Asignatura").strip()
            cycle = str(proj.get("cycle") or "General").strip()
            grouped.setdefault((course, cycle), []).append(proj)

        report: List[Dict[str, Any]] = []
        for (course, cycle), course_projects in sorted(grouped.items()):
            metrics = self.compute_category_and_tech_metrics(course_projects)
            report.append(
                {
                    "course_name": course,
                    "cycle": cycle,
                    "validated_projects_count": len(course_projects),
                    "categories_distribution": metrics["categories_distribution"],
                    "top_technologies": metrics["technology_ranking"][:5],
                }
            )

        return report


analytics_service = AnalyticsEngineService()


def get_bi_category_analytics(
    projects: List[Dict[str, Any]],
    course_name: Optional[str] = None,
    cycle: Optional[str] = None,
    semester: Optional[str] = None,
) -> Dict[str, Any]:
    """Función auxiliar reutilizable para backend/routers/analytics_dashboard.py."""
    return analytics_service.compute_category_and_tech_metrics(
        projects=projects,
        course_name=course_name,
        cycle=cycle,
        semester=semester,
    )


def get_syllabus_category_report(
    projects: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Función auxiliar reutilizable para GET /api/v1/analytics/syllabus-report."""
    return analytics_service.build_syllabus_gap_report(projects=projects)