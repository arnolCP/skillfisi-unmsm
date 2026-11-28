"""Contrato de aceptación HU12-HU13 para integrar el backend del Sprint 4."""

from copy import deepcopy
from importlib.util import find_spec
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from main import app
from routers import auth_profiles, projects


ANALYTICS = "/api/v1/analytics"
AUTHORITY = "autoridad.qa@unmsm.edu.pe"

# Valores esperados calculados de forma independiente del servicio analítico.
PROJECT_CASES = [
    {
        "id": "validado-web-8",
        "course_name": "Ingeniería de Software",
        "cycle": "8",
        "semester": "2026-2",
        "status": "Validado",
        "tech_stack": ["Python", "FastAPI", "Python"],
        "active_review_seconds": 120,
        "consent_law_29733": True,
    },
    {
        "id": "validado-web-9",
        "course_name": "Ingeniería de Software",
        "cycle": "9",
        "semester": "2026-2",
        "status": "Validado",
        "tech_stack": ["Python", "PostgreSQL"],
        "active_review_seconds": 240,
        "consent_law_29733": False,
    },
    {
        "id": "validado-ia-8",
        "course_name": "Inteligencia Artificial",
        "cycle": "8",
        "semester": "2026-2",
        "status": "Validado",
        "tech_stack": ["Python", "pandas"],
        "active_review_seconds": 300,
        "consent_law_29733": True,
    },
    {
        "id": "validado-web-2026-1",
        "course_name": "Ingeniería de Software",
        "cycle": "8",
        "semester": "2026-1",
        "status": "Validado",
        "tech_stack": ["Java", "Spring Boot"],
        "active_review_seconds": 60,
        "consent_law_29733": True,
    },
    {
        "id": "borrador",
        "course_name": "Ingeniería de Software",
        "cycle": "8",
        "semester": "2026-2",
        "status": "Borrador",
        "tech_stack": ["Tecnología sin validar"],
        "active_review_seconds": None,
        "consent_law_29733": False,
    },
    {
        "id": "en-revision",
        "course_name": "Ingeniería de Software",
        "cycle": "8",
        "semester": "2026-2",
        "status": "En Revisión",
        "tech_stack": ["Tecnología sin validar"],
        "active_review_seconds": None,
        "consent_law_29733": True,
    },
    {
        "id": "observado",
        "course_name": "Inteligencia Artificial",
        "cycle": "8",
        "semester": "2026-2",
        "status": "Observado",
        "tech_stack": ["Tecnología sin validar"],
        "active_review_seconds": 900,
        "consent_law_29733": True,
    },
]


@pytest.fixture
def client(monkeypatch):
    if find_spec("routers.analytics_dashboard") is None:
        pytest.skip("Sprint 4 pendiente: falta routers/analytics_dashboard.py.")
    store = {case["id"]: deepcopy(case) for case in PROJECT_CASES}
    authority = auth_profiles.CurrentUser(id="autoridad-qa", email=AUTHORITY)
    monkeypatch.setitem(app.dependency_overrides, auth_profiles.get_current_user, lambda: authority)
    monkeypatch.setattr(auth_profiles, "_fetch_role", lambda user_id: "Autoridad")
    # Mantiene las referencias de los routers que importan PROJECTS_DB directamente.
    with patch.dict(projects.PROJECTS_DB, store, clear=True), TestClient(app) as http:
        yield http


def get_dashboard(client, **filters):
    response = client.get(f"{ANALYTICS}/dashboard", params=filters)
    assert response.status_code == 200, response.text
    return response.json()


def test_health_reports_all_six_modules(client):
    response = client.get("/")
    assert response.status_code == 200
    for module in range(1, 7):
        assert response.json()[f"module_3_{module}"] == "active"


def test_dashboard_counts_every_validated_project(client):
    dashboard = get_dashboard(client)
    assert dashboard["total_projects"] == 7
    assert dashboard["total_validated_projects"] == 4
    assert dashboard["validation_rate_percent"] == pytest.approx(400 / 7, abs=0.01)
    assert dashboard["avg_review_seconds"] == pytest.approx(180)


def test_ranking_counts_projects_and_excludes_nonvalidated_stack(client):
    dashboard = get_dashboard(client)
    ranking = {row["technology"]: row for row in dashboard["top_technologies"]}
    assert {name: row["project_count"] for name, row in ranking.items()} == {
        "Python": 3, "FastAPI": 1, "PostgreSQL": 1,
        "pandas": 1, "Java": 1, "Spring Boot": 1,
    }
    assert ranking["Python"]["percentage"] == pytest.approx(75)


@pytest.mark.parametrize(
    ("filters", "registered", "validated", "average"),
    [
        ({"course_name": "Ingeniería de Software"}, 5, 3, 140),
        ({"cycle": "8"}, 6, 3, 160),
        ({"semester": "2026-2"}, 6, 3, 220),
        ({"course_name": "Ingeniería de Software", "cycle": "8"}, 4, 2, 90),
        ({"course_name": "Ingeniería de Software", "semester": "2026-2"}, 4, 2, 180),
        ({"cycle": "8", "semester": "2026-2"}, 5, 2, 210),
        ({"course_name": "Ingeniería de Software", "cycle": "8", "semester": "2026-2"}, 3, 1, 120),
    ],
)
def test_combined_filters_return_exact_counts(client, filters, registered, validated, average):
    dashboard = get_dashboard(client, **filters)
    assert dashboard["total_projects"] == registered
    assert dashboard["total_validated_projects"] == validated
    assert dashboard["avg_review_seconds"] == pytest.approx(average)
    assert dashboard["validation_rate_percent"] == pytest.approx(100 * validated / registered, abs=0.01)


def test_unknown_course_returns_empty_aggregates(client):
    dashboard = get_dashboard(client, course_name="Curso sin proyectos")
    assert dashboard["total_projects"] == dashboard["total_validated_projects"] == 0
    assert dashboard["avg_review_seconds"] is None
    assert dashboard["validation_rate_percent"] == 0
    assert dashboard["top_technologies"] == []


def test_validated_projects_without_public_consent_remain_in_internal_metrics(client):
    dashboard = get_dashboard(client, cycle="9")
    assert dashboard["total_validated_projects"] == 1
    assert dashboard["public_portfolio_percent"] == 0


def test_syllabus_report_uses_the_same_curricular_filters(client):
    response = client.get(f"{ANALYTICS}/syllabus-report", params={
        "course_name": "Ingeniería de Software", "cycle": "8", "semester": "2026-2",
    })
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["total_validated_projects"] == 1
    course, = report["courses"]
    assert course["course_name"] == "Ingeniería de Software"
    assert course["total_validated_projects"] == 1
    assert {row["technology"] for row in course["top_technologies"]} == {"Python", "FastAPI"}
