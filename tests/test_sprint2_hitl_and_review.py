import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean

import pytest
from fastapi.testclient import TestClient

from main import app
from routers import auth_profiles, llm_extraction, projects, teacher_reviews
from services.llm_service import AIExtractionSchema, LLMAdapterService
from services.quality_metrics import (
    MINIMUM_PRECISION,
    MINIMUM_RECALL,
    calculate_precision,
    calculate_recall,
)


STUDENT = "estudiante.qa@unmsm.edu.pe"
TEACHER = "docente.qa@unmsm.edu.pe"
OTHER_TEACHER = "otro.docente@unmsm.edu.pe"
SUMMARY = "Solución académica de inventario con persistencia y un panel de consultas."
GOLDEN_DATASET = Path(__file__).with_name("golden_dataset.json")


@pytest.fixture
def client(monkeypatch):
    store = {}
    monkeypatch.setattr(projects, "PROJECTS_DB", store)
    monkeypatch.setattr(teacher_reviews, "PROJECTS_DB", store)
    with TestClient(app) as http:
        yield http


@pytest.fixture
def teacher(monkeypatch):
    identity = auth_profiles.CurrentUser(id="docente-qa", email=TEACHER)
    monkeypatch.setitem(app.dependency_overrides, auth_profiles.get_current_user, lambda: identity)
    monkeypatch.setattr(auth_profiles, "_fetch_role", lambda user_id: "Docente")
    return identity


def create_draft(client, teacher_email=TEACHER):
    response = client.post("/api/v1/projects/", json={
        "title": "Inventario académico",
        "course_name": "Ingeniería de Software",
        "cycle": "8",
        "student_email": STUDENT,
        "teacher_email": teacher_email,
    })
    assert response.status_code == 201, response.text
    assert response.json()["project"]["status"] == "Borrador"
    return response.json()["project"]["id"]


def submit_review(client, project_id, consent=True):
    return client.put(f"/api/v1/projects/{project_id}/submit-review", json={
        "tech_stack": ["Python", "FastAPI"],
        "professional_summary": SUMMARY,
        "consent_law_29733": consent,
    })


def test_rejects_submission_without_consent(client):
    project_id = create_draft(client)
    response = submit_review(client, project_id, consent=False)

    assert response.status_code == 400
    assert "29733" in response.json()["detail"]
    saved = client.get(f"/api/v1/projects/{project_id}").json()
    assert saved["status"] == "Borrador"
    assert saved["submitted_at"] is None
    assert saved["tech_stack"] == []


def test_teacher_inbox_requires_authentication_and_teacher_role(client, teacher, monkeypatch):
    monkeypatch.setattr(auth_profiles, "_fetch_role", lambda user_id: "Estudiante")
    assert client.get("/api/v1/reviews/pending").status_code == 403
    with monkeypatch.context() as patch:
        patch.delitem(app.dependency_overrides, auth_profiles.get_current_user)
        assert client.get("/api/v1/reviews/pending").status_code == 401


@pytest.mark.parametrize(
    ("decision", "seconds", "expected_seconds", "compliant"),
    [("Validado", 300, 300, True), ("Observado", 300.1, 301, False)],
)
def test_teacher_review_uses_server_clock(
    client, teacher, monkeypatch, decision, seconds, expected_seconds, compliant
):
    class ReviewClock(datetime):
        instant = datetime(2026, 11, 8, 15, tzinfo=timezone.utc)

        @classmethod
        def now(cls, tz):
            return cls.instant.astimezone(tz)

    monkeypatch.setattr(projects, "datetime", ReviewClock)
    monkeypatch.setattr(teacher_reviews, "datetime", ReviewClock)
    project_id = create_draft(client)
    other_id = create_draft(client, OTHER_TEACHER)
    assert submit_review(client, other_id).status_code == 200
    sent = submit_review(client, project_id)
    assert sent.status_code == 200, sent.text
    project = sent.json()["project"]
    assert project["status"] == "En Revisión"
    assert project["tech_stack"] == ["Python", "FastAPI"]
    assert project["professional_summary"] == SUMMARY
    assert project["consent_timestamp"] == project["submitted_at"]
    assert submit_review(client, project_id).status_code == 409

    pending = client.get("/api/v1/reviews/pending").json()
    assert [item["id"] for item in pending["projects"]] == [project_id]
    assert client.post(f"/api/v1/reviews/{other_id}/open").status_code == 404
    review = f"/api/v1/reviews/{project_id}"
    payload = {"decision": decision, "teacher_feedback": "Revisar evidencias adjuntas."}
    assert client.post(f"{review}/decision", json=payload).status_code == 409

    ReviewClock.instant += timedelta(seconds=20)
    opened_at = ReviewClock.instant.isoformat()
    opened = client.post(f"{review}/open")
    assert opened.status_code == 200, opened.text
    assert opened.json()["opened_by_teacher_at"] == opened_at
    ReviewClock.instant += timedelta(seconds=seconds)
    assert client.post(f"{review}/open").json()["opened_by_teacher_at"] == opened_at
    if decision == "Observado":
        assert client.post(f"{review}/decision", json={"decision": decision}).status_code == 400
    response = client.post(f"{review}/decision", json=payload)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["new_status"] == decision
    assert saved["telemetry"] == {
        "submitted_at": project["submitted_at"],
        "opened_by_teacher_at": opened_at,
        "decision_at": ReviewClock.instant.isoformat(),
        "active_review_seconds": expected_seconds,
        "sla_max_seconds": 300,
        "sla_compliant": compliant,
    }
    assert client.get("/api/v1/reviews/pending").json()["total_pending"] == 0
    assert client.get(f"/api/v1/projects/{project_id}").json()["status"] == decision
    if decision == "Observado":
        resubmitted = submit_review(client, project_id).json()["project"]
        assert resubmitted["status"] == "En Revisión"
        assert resubmitted["opened_by_teacher_at"] is None
        assert resubmitted["decision_at"] is None
        assert resubmitted["active_review_seconds"] is None


def test_llm_cache_calls_provider_once(client, monkeypatch):
    service = LLMAdapterService()
    service.api_key = "solo-para-pruebas"
    calls = []

    def fake_provider(evidence):
        calls.append(evidence)
        return AIExtractionSchema(stack_tecnologico=["Python"], resumen_profesional=SUMMARY)

    monkeypatch.setattr(service, "_call_gemini", fake_provider)
    monkeypatch.setattr(llm_extraction, "llm_service", service)
    project_id = create_draft(client)
    notebook = {"cells": [{"cell_type": "code", "source": ["import pandas"]}]}
    upload = client.post(f"/api/v1/projects/{project_id}/evidences", files={
        "evidence_file": ("analisis.ipynb", json.dumps(notebook), "application/json"),
    })
    assert upload.status_code == 200, upload.text
    evidence = upload.json()["extracted_evidence_text"]
    assert "import pandas" in evidence
    payload = {"project_id": project_id, "extracted_evidence_text": evidence}
    first = client.post("/api/v1/llm/extract", json=payload)
    second = client.post("/api/v1/llm/extract", json=payload)
    assert first.status_code == second.status_code == 200
    assert second.json()["project_id"] == project_id
    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert first.json()["evidence_hash"] == second.json()["evidence_hash"]
    assert first.json()["stack_tecnologico"] == second.json()["stack_tecnologico"] == ["Python"]
    assert calls == [evidence]
    assert client.get("/api/v1/llm/cache/metrics").json() == {
        "cache_size": 1, "hits": 1, "misses": 1,
        "total_requests": 2, "hit_ratio_percent": 50.0,
    }


def _technology_set(labels):
    return {label.strip().casefold() for label in labels if label.strip()}


def _evaluate_dataset(extract):
    cases = json.loads(GOLDEN_DATASET.read_text(encoding="utf-8"))
    assert len(cases) == len({case["id"] for case in cases}) == 10
    results = []
    for case in cases:
        expected = _technology_set(case["expected_technologies"])
        assert expected
        predicted = _technology_set(extract(case["evidence_text"]))
        true_positives = len(predicted & expected)
        precision = calculate_precision(true_positives, len(predicted - expected)) if predicted else 0.0
        recall = calculate_recall(true_positives, len(expected - predicted))
        print(f"{case['id']}: precisión={precision:.1%}, recall={recall:.1%}")
        results.append((precision, recall))

    precision = mean(row[0] for row in results)
    recall = mean(row[1] for row in results)
    print(f"Promedio de {len(results)} casos: precisión={precision:.1%}, recall={recall:.1%}")
    return precision, recall


def test_golden_dataset_local_baseline(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    service = LLMAdapterService()
    print("Modo local (heurística)")
    precision, recall = _evaluate_dataset(
        lambda evidence: service.extract_skills_and_summary(evidence)["data"]["stack_tecnologico"]
    )
    assert 0 <= precision <= 1
    assert 0 <= recall <= 1


def test_golden_dataset_gemini(request):
    if not request.config.getoption("--gemini-live"):
        pytest.skip("Evaluación con Gemini habilitada mediante --gemini-live.")
    service = LLMAdapterService()
    assert service.api_key.strip(), "Configura LLM_API_KEY para evaluar Gemini."
    print(f"Modelo evaluado: {service.model}")

    # Llamada directa al proveedor para que un error remoto no se mida como fallback.
    precision, recall = _evaluate_dataset(
        lambda evidence: service._call_gemini(evidence[:service.max_chars]).stack_tecnologico
    )
    assert (precision >= MINIMUM_PRECISION and recall >= MINIMUM_RECALL), (
        f"Precisión {precision:.1%} (meta {MINIMUM_PRECISION:.0%}), "
        f"recall {recall:.1%} (meta {MINIMUM_RECALL:.0%})."
    )
