import re

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from main import app
from routers import auth_profiles, projects, public_portfolio, teacher_reviews


STUDENT = "estudiante.qa@unmsm.edu.pe"
OTHER_STUDENT = "otra.persona@unmsm.edu.pe"
TEACHER = "docente.qa@unmsm.edu.pe"
PORTFOLIO = "/api/v1/portfolio"
PROJECTS = "/api/v1/projects"
REVIEWS = "/api/v1/reviews"
FEEDBACK = "Documentar las pruebas del módulo de inventario."
SUBMISSION = {
    "tech_stack": ["Python", "FastAPI"],
    "professional_summary": "Inventario académico con reportes de disponibilidad y una API de consultas.",
    "consent_law_29733": True,
}


@pytest.fixture
def client(monkeypatch):
    store = {}
    for module in (projects, teacher_reviews, public_portfolio):
        monkeypatch.setattr(module, "PROJECTS_DB", store)

    def test_identity(request: Request):
        email = request.headers.get("X-Test-Identity")
        if email is None:
            raise HTTPException(status_code=401)
        return auth_profiles.CurrentUser(id=email, email=email)

    monkeypatch.setitem(app.dependency_overrides, auth_profiles.get_current_user, test_identity)
    monkeypatch.setattr(
        auth_profiles, "_fetch_role", lambda user_id: "Docente" if user_id == TEACHER else "Estudiante"
    )
    with TestClient(app) as http:
        yield http


def identity(email):
    return {"X-Test-Identity": email}


def create_draft(client, student=STUDENT):
    response = client.post(f"{PROJECTS}/", json={
        "title": "Inventario académico",
        "course_name": "Ingeniería de Software",
        "cycle": "8",
        "student_email": student,
        "teacher_email": TEACHER,
    })
    assert response.status_code == 201, response.text
    return response.json()["project"]["id"]


def submit(client, project_id):
    response = client.put(f"{PROJECTS}/{project_id}/submit-review", json=SUBMISSION)
    assert response.status_code == 200, response.text


def decide(client, project_id, decision):
    review = f"{REVIEWS}/{project_id}"
    headers = identity(TEACHER)
    opened = client.post(f"{review}/open", headers=headers)
    assert opened.status_code == 200, opened.text
    response = client.post(f"{review}/decision", headers=headers, json={
        "decision": decision,
        "teacher_feedback": FEEDBACK,
        "validated_technologies": ["Python", "SQLite"],
    })
    assert response.status_code == 200, response.text
    return response.json()["project"]


def privacy(client, project_id, consent, *, actor=None, claimed_owner=None):
    body = {"consent_law_29733": consent}
    if claimed_owner is not None:
        body["student_email"] = claimed_owner
    return client.patch(
        f"{PORTFOLIO}/projects/{project_id}/privacy",
        headers=identity(actor) if actor else {},
        json=body,
    )


@pytest.mark.parametrize("status", ["Borrador", "En Revisión", "Observado"])
def test_public_portfolio_requires_validation_even_with_consent(client, status):
    project_id = create_draft(client)
    assert privacy(client, project_id, True, actor=STUDENT).status_code == 200
    if status != "Borrador":
        submit(client, project_id)
    if status == "Observado":
        decide(client, project_id, status)

    public = client.get(f"{PORTFOLIO}/{STUDENT}").json()
    assert public["total_validated_projects"] == 0
    assert public["validated_projects"] == public["consolidated_tech_stack"] == []
    assert client.get(f"{REVIEWS}/{project_id}/seal").status_code == 404


def test_validation_issues_matching_seals_and_public_portfolio(client):
    project_id = create_draft(client)
    submit(client, project_id)
    validated = decide(client, project_id, "Validado")
    code = validated["verification_code"]
    assert re.fullmatch(r"FISI-2026-[0-9A-F]{6}", code)

    verification = client.get(f"{PORTFOLIO}/verify/{code.lower()}")
    seal = client.get(f"{REVIEWS}/{project_id}/seal")
    portfolio = client.get(f"{PORTFOLIO}/{STUDENT.split('@')[0]}")
    for response in (verification, seal, portfolio):
        assert response.status_code == 200, response.text
        assert response.headers["Cache-Control"] == "no-store"

    assert verification.json()["valid_seal"] is True
    assert verification.json()["verification_code"] == code
    assert verification.json()["validated_at"] == validated["decision_at"]
    assert seal.json()["official_seal"]["verification_code"] == code
    assert seal.json()["official_seal"]["validated_by_teacher"] == TEACHER
    assert portfolio.json()["consolidated_tech_stack"] == ["Python", "SQLite"]
    published, = portfolio.json()["validated_projects"]
    assert published["project_id"] == project_id
    assert published["official_seal"]["verification_code"] == code
    assert FEEDBACK not in portfolio.text
    assert client.get(f"{PORTFOLIO}/{OTHER_STUDENT}").json()["validated_projects"] == []


def test_only_authenticated_owner_can_change_consent(client):
    project_id = create_draft(client)
    submit(client, project_id)
    decide(client, project_id, "Validado")

    assert privacy(client, project_id, False, claimed_owner=STUDENT).status_code == 401
    assert privacy(
        client, project_id, False, actor=OTHER_STUDENT, claimed_owner=STUDENT
    ).status_code == 403
    assert privacy(
        client, project_id, False, actor=STUDENT, claimed_owner=OTHER_STUDENT
    ).status_code == 403
    assert privacy(client, project_id, "false", actor=STUDENT).status_code == 422
    assert client.get(f"{PORTFOLIO}/{STUDENT}").json()["total_validated_projects"] == 1


def test_revocation_hides_project_and_both_seal_routes_immediately(client):
    project_id = create_draft(client)
    submit(client, project_id)
    code = decide(client, project_id, "Validado")["verification_code"]
    seal_paths = (f"{PORTFOLIO}/verify/{code}", f"{REVIEWS}/{project_id}/seal")
    assert all(client.get(path).status_code == 200 for path in seal_paths)

    revoked = privacy(client, project_id, False, actor=STUDENT)
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["is_publicly_visible"] is False
    assert client.get(f"{PORTFOLIO}/{STUDENT}").json()["validated_projects"] == []
    for path in seal_paths:
        hidden = client.get(path)
        assert hidden.status_code == 404
        assert hidden.headers["Cache-Control"] == "no-store"
    detail = f"{PROJECTS}/{project_id}"
    listing = f"{PROJECTS}/student/{STUDENT}"
    for private_path in (detail, listing):
        assert client.get(private_path).status_code == 401
        assert client.get(private_path, headers=identity(STUDENT)).status_code == 200
    assert client.get(detail, headers=identity(OTHER_STUDENT)).status_code == 404
    assert client.get(listing, headers=identity(OTHER_STUDENT)).status_code == 403

    restored = privacy(client, project_id, True, actor=STUDENT)
    assert restored.json()["is_publicly_visible"] is True
    assert client.get(seal_paths[0]).json()["verification_code"] == code


def test_resubmission_preserves_feedback_and_restarts_review(client):
    project_id = create_draft(client)
    path = f"{PROJECTS}/{project_id}/resubmit"
    owner = identity(STUDENT)
    assert client.put(path, json=SUBMISSION, headers=owner).status_code == 409
    submit(client, project_id)
    observed = decide(client, project_id, "Observado")
    assert observed["teacher_feedback"] == FEEDBACK
    assert observed["verification_code"] is None
    edited = {
        **SUBMISSION,
        "tech_stack": ["Python", "pytest"],
        "professional_summary": "Inventario actualizado con pruebas de disponibilidad de extremo a extremo.",
    }
    assert client.put(path, json=edited).status_code == 401
    assert client.put(path, json=edited, headers=identity(OTHER_STUDENT)).status_code == 403
    rejected = client.put(path, json={**edited, "consent_law_29733": False}, headers=owner)
    assert rejected.status_code == 400

    response = client.put(path, json=edited, headers=owner)
    assert response.status_code == 200, response.text
    project = response.json()["project"]
    assert project["status"] == "En Revisión"
    assert project["tech_stack"] == edited["tech_stack"]
    assert project["professional_summary"] == edited["professional_summary"]
    assert project["previous_teacher_feedback"] == FEEDBACK
    assert project["submitted_at"] >= observed["decision_at"]
    for field in ("teacher_feedback", "opened_by_teacher_at", "decision_at", "active_review_seconds"):
        assert project[field] is None

    pending = client.get(f"{REVIEWS}/pending", headers=identity(TEACHER)).json()
    assert [item["id"] for item in pending["projects"]] == [project_id]
    assert client.put(path, json=edited, headers=owner).status_code == 409
    assert decide(client, project_id, "Validado")["previous_teacher_feedback"] == FEEDBACK
