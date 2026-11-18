"""Pruebas de la persistencia de proyectos (services/supabase_client.py) en modo local.

El modo local aplica las mismas restricciones que database/02_sprint2_migration.sql y
database/04_sprint3_portfolio.sql, así que estas pruebas validan las reglas del flujo
sin conectarse a Supabase.
"""

import hashlib
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from services import supabase_client as sc
from services.quality_metrics import meets_teacher_time_target, teacher_active_time_seconds

STUDENT = "alumno.qa@unmsm.edu.pe"
OTHER_STUDENT = "otro.alumno@unmsm.edu.pe"
TEACHER = "docente.qa@unmsm.edu.pe"
OTHER_TEACHER = "otro.docente@unmsm.edu.pe"
SUMMARY = "Plataforma web que organiza evidencias académicas y resume competencias técnicas."
URL = "https://example.supabase.co"
KEY = "clave-de-prueba"


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 11, 15, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture(autouse=True)
def clean_store():
    assert sc.get_persistence_mode() == "local"
    sc.reset_local_store()
    yield
    sc.reset_local_store()


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(sc, "_utcnow", fake)
    return fake


@pytest.fixture
def people():
    sc.register_local_user(email=STUDENT, full_name="Alumno QA", role="Estudiante")
    sc.register_local_user(email=OTHER_STUDENT, full_name="Otro Alumno", role="Estudiante")
    sc.register_local_user(email=TEACHER, full_name="Docente QA", role="Docente")
    sc.register_local_user(email=OTHER_TEACHER, full_name="Otro Docente", role="Docente")


def new_project(**overrides):
    data = {
        "title": "Portafolio académico SkillFISI",
        "course_name": "Gestión de Proyectos de TI",
        "cycle": "8vo Ciclo",
        "student_email": STUDENT,
        "teacher_email": TEACHER,
    }
    data.update(overrides)
    return sc.insert_project(**data)


def submit(project_id, **overrides):
    data = {"tech_stack": ["Python", "FastAPI"], "professional_summary": SUMMARY, "consent_law_29733": True}
    data.update(overrides)
    return sc.update_project_review_submission(project_id, **data)


def submitted_and_opened(clock):
    project = new_project()
    clock.advance(10)
    submit(project["id"])
    clock.advance(10)
    return sc.mark_project_opened(project["id"])


# ---------------------------------------------------------------------------
# Modo de persistencia
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({"APP_ENV": "production", "SUPABASE_URL": URL, "SUPABASE_SERVICE_ROLE_KEY": KEY}, "supabase"),
        ({"SKILLFISI_PERSISTENCE": "local", "SUPABASE_URL": URL, "SUPABASE_SERVICE_ROLE_KEY": KEY}, "local"),
        ({"SKILLFISI_PERSISTENCE": " LOCAL "}, "local"),
        ({"SUPABASE_URL": URL, "SUPABASE_SERVICE_ROLE_KEY": KEY}, "supabase"),
        ({"SUPABASE_URL": URL, "SUPABASE_SERVICE_ROLE_KEY": KEY, "CI": "true"}, "supabase"),
        ({"CI": "true"}, "local"),
    ],
)
def test_resolves_persistence_mode(env, expected):
    assert sc.resolve_persistence_mode(env) == expected


@pytest.mark.parametrize(
    "env",
    [
        {"APP_ENV": "production"},
        {"APP_ENV": "production", "CI": "true"},
        {"APP_ENV": "Production", "SKILLFISI_PERSISTENCE": "local", "SUPABASE_URL": URL, "SUPABASE_SERVICE_ROLE_KEY": KEY},
        {},
        {"SUPABASE_URL": URL, "CI": "true"},
        {"SUPABASE_SERVICE_ROLE_KEY": KEY},
        {"SKILLFISI_PERSISTENCE": "memoria"},
    ],
)
def test_rejects_unsafe_or_incomplete_configuration(env):
    with pytest.raises(sc.SupabaseConfigError):
        sc.resolve_persistence_mode(env)


def test_conftest_forces_local_mode():
    assert sc.get_persistence_mode() == "local"


def test_supabase_errors_never_fall_back_to_local(monkeypatch):
    class BrokenClient:
        def table(self, name):
            raise ConnectionError("sin red")

    monkeypatch.setattr(sc, "get_admin_client", lambda: BrokenClient())

    with pytest.raises(sc.DatabaseError) as error:
        sc._SupabaseBackend().find_user_by_email(STUDENT)

    assert error.value.http_status == 503


def test_local_only_helpers_refuse_supabase_mode(monkeypatch):
    monkeypatch.setattr(sc, "get_persistence_mode", lambda: "supabase")

    with pytest.raises(RuntimeError):
        sc.register_local_user(email=STUDENT, full_name="Alumno QA")
    with pytest.raises(RuntimeError):
        sc.reset_local_store()


@pytest.mark.parametrize(
    ("error_class", "status_code"),
    [
        (sc.ProjectValidationError, 400),
        (sc.NotAuthorizedError, 403),
        (sc.ProjectNotFoundError, 404),
        (sc.InvalidTransitionError, 409),
        (sc.ReferenceNotFoundError, 422),
        (sc.DatabaseError, 503),
    ],
)
def test_errors_document_http_status(error_class, status_code):
    assert error_class.http_status == status_code
    assert issubclass(error_class, sc.ProjectRepositoryError)


def test_validation_error_is_also_value_error():
    assert issubclass(sc.ProjectValidationError, ValueError)


# ---------------------------------------------------------------------------
# Enlace de GitHub y hash de evidencia
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  https://github.com/arnolCP/skillfisi-unmsm  ", "https://github.com/arnolCP/skillfisi-unmsm"),
        ("https://www.github.com/equipo6/proyecto.git/", "https://github.com/equipo6/proyecto"),
        ("https://GitHub.com/Equipo6/Proyecto", "https://github.com/Equipo6/Proyecto"),
    ],
)
def test_normalizes_github_url(raw, expected):
    assert sc.normalize_github_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "http://github.com/equipo6/proyecto",
        "https://gitlab.com/equipo6/proyecto",
        "https://github.com/equipo6",
        "https://github.com/equipo6/proyecto/tree/main",
        "https://github.com/equipo6/mi proyecto",
        "https://github.com/equipo6/proyecto?tab=readme",
        "https://github.com:443/equipo6/proyecto",
        "javascript:alert(1)//github.com/a/b",
        "",
        None,
    ],
)
def test_rejects_invalid_github_url_with_value_error(raw):
    with pytest.raises(ValueError):
        sc.normalize_github_url(raw)


def test_evidence_hash_is_sha256_of_trimmed_text():
    expected = hashlib.sha256("README con FastAPI".encode("utf-8")).hexdigest()

    assert sc.compute_evidence_hash("  README con FastAPI \n") == expected
    assert len(expected) == 64


# ---------------------------------------------------------------------------
# HU03: creación del proyecto
# ---------------------------------------------------------------------------
def test_insert_returns_draft_with_projects_db_keys_plus_sprint3_fields(people):
    from routers.projects import ProjectCreateRequest, create_project

    legacy = create_project(
        ProjectCreateRequest(
            title="Proyecto de referencia",
            course_name="Gestión de Proyectos de TI",
            cycle="8vo Ciclo",
            student_email=STUDENT,
            teacher_email=TEACHER,
        )
    )["project"]

    project = new_project(student_email="  ALUMNO.QA@unmsm.edu.pe ")

    assert set(project) == set(legacy) | {"verification_code", "consent_revoked_at"}
    assert project["verification_code"] is None
    assert project["consent_revoked_at"] is None
    assert project["status"] == "Borrador"
    assert project["student_email"] == STUDENT
    assert project["teacher_email"] == TEACHER
    assert project["course_name"] == "Gestión de Proyectos de TI"
    assert project["cycle"] == "8"
    assert project["tech_stack"] == []
    assert project["consent_law_29733"] is False
    assert project["submitted_at"] is None


def test_insert_reuses_course_of_same_teacher_ignoring_case(people):
    first = new_project()
    second = new_project(course_name="  gestión de proyectos de ti ", student_email=OTHER_STUDENT)
    third = new_project(teacher_email=OTHER_TEACHER)

    assert len(sc._local_backend.courses) == 2
    assert second["course_name"] == first["course_name"] == "Gestión de Proyectos de TI"
    assert third["teacher_email"] == OTHER_TEACHER


@pytest.mark.parametrize(
    "overrides",
    [
        {"student_email": "nadie@unmsm.edu.pe"},
        {"student_email": TEACHER},
        {"teacher_email": "nadie@unmsm.edu.pe"},
        {"teacher_email": STUDENT},
    ],
)
def test_insert_requires_registered_student_and_teacher(people, overrides):
    with pytest.raises(sc.ReferenceNotFoundError):
        new_project(**overrides)
    assert sc._local_backend.projects == {}


@pytest.mark.parametrize(
    "overrides",
    [
        {"student_email": "alumno@gmail.com"},
        {"teacher_email": "docente@fisi.unmsm.edu.pe"},
        {"cycle": "Ciclo final"},
        {"cycle": "12vo Ciclo"},
        {"title": "Web"},
        {"course_name": "  "},
    ],
)
def test_insert_validates_input(people, overrides):
    with pytest.raises(sc.ProjectValidationError):
        new_project(**overrides)


# ---------------------------------------------------------------------------
# HU04: evidencia
# ---------------------------------------------------------------------------
def test_save_evidence_stores_normalized_url_and_hash_only(people):
    project = new_project()

    saved = sc.save_project_evidence(
        project["id"], github_url="https://www.github.com/equipo6/proyecto.git", evidence_text="README del proyecto"
    )

    assert saved["github_url"] == "https://github.com/equipo6/proyecto"
    stored = sc._local_backend.projects[project["id"]]
    assert stored["evidence_hash"] == sc.compute_evidence_hash("README del proyecto")
    assert saved["extracted_evidence_text"] == ""


def test_save_evidence_rejects_invalid_url_without_changes(people):
    project = new_project()

    with pytest.raises(ValueError):
        sc.save_project_evidence(project["id"], github_url="https://gitlab.com/equipo6/proyecto")

    assert sc.get_project(project["id"])["github_url"] is None


def test_save_evidence_requires_some_data(people):
    project = new_project()

    with pytest.raises(sc.ProjectValidationError):
        sc.save_project_evidence(project["id"])


def test_save_evidence_only_in_editable_states(people, clock):
    project = new_project()
    submit(project["id"])

    with pytest.raises(sc.InvalidTransitionError) as error:
        sc.save_project_evidence(project["id"], github_url="https://github.com/equipo6/otro")

    assert error.value.current_status == "En Revisión"


# ---------------------------------------------------------------------------
# HU06: envío a revisión
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("consent", [False, None, "true"])
def test_submit_requires_consent_law_29733(people, consent):
    project = new_project()

    with pytest.raises(sc.ProjectValidationError, match="29733"):
        submit(project["id"], consent_law_29733=consent)

    assert sc.get_project(project["id"])["status"] == "Borrador"
    assert sc._local_backend.technologies == []


@pytest.mark.parametrize("stack", [[], ["  ", ""]])
def test_submit_requires_at_least_one_technology(people, stack):
    project = new_project()

    with pytest.raises(sc.ProjectValidationError):
        submit(project["id"], tech_stack=stack)


def test_submit_records_timestamps_and_cleans_technologies(people, clock):
    project = new_project()
    clock.advance(30)

    sent = submit(project["id"], tech_stack=[" Python ", "FastAPI", "python", "", "PostgreSQL"])

    assert sent["status"] == "En Revisión"
    assert sent["tech_stack"] == ["Python", "FastAPI", "PostgreSQL"]
    assert sent["consent_law_29733"] is True
    assert sent["consent_timestamp"] == sent["submitted_at"] == clock.now.isoformat()
    assert sent["professional_summary"] == SUMMARY
    assert sc.get_project(project["id"])["tech_stack"] == ["Python", "FastAPI", "PostgreSQL"]


def test_submit_only_from_draft_or_observed(people, clock):
    project = new_project()
    submit(project["id"])

    with pytest.raises(sc.InvalidTransitionError) as error:
        submit(project["id"])

    assert error.value.current_status == "En Revisión"
    assert error.value.http_status == 409


def test_submit_rejects_other_student(people):
    project = new_project()

    with pytest.raises(sc.NotAuthorizedError):
        submit(project["id"], student_email=OTHER_STUDENT)

    assert submit(project["id"], student_email=STUDENT)["status"] == "En Revisión"


@pytest.mark.parametrize("project_id", [str(uuid.uuid4()), "no-es-un-uuid"])
def test_unknown_project_raises_not_found(people, project_id):
    operations = [
        lambda: sc.get_project(project_id),
        lambda: sc.save_project_evidence(project_id, evidence_text="texto"),
        lambda: submit(project_id),
        lambda: sc.mark_project_opened(project_id),
        lambda: sc.register_teacher_decision(project_id, teacher_email=TEACHER, decision="Validado"),
    ]
    for operation in operations:
        with pytest.raises(sc.ProjectNotFoundError):
            operation()


# ---------------------------------------------------------------------------
# HU07: apertura y decisión docente
# ---------------------------------------------------------------------------
def test_open_requires_project_in_review(people):
    project = new_project()

    with pytest.raises(sc.InvalidTransitionError):
        sc.mark_project_opened(project["id"])


def test_open_does_not_restart_timer(people, clock):
    opened = submitted_and_opened(clock)
    clock.advance(120)

    reopened = sc.mark_project_opened(opened["id"], teacher_email=TEACHER)

    assert reopened["opened_by_teacher_at"] == opened["opened_by_teacher_at"]


def test_open_rejects_other_teacher(people, clock):
    project = new_project()
    submit(project["id"])

    with pytest.raises(sc.NotAuthorizedError):
        sc.mark_project_opened(project["id"], teacher_email=OTHER_TEACHER)

    assert sc.get_project(project["id"])["opened_by_teacher_at"] is None


def test_decision_requires_previous_opening(people, clock):
    project = new_project()
    submit(project["id"])

    with pytest.raises(sc.InvalidTransitionError):
        sc.register_teacher_decision(project["id"], teacher_email=TEACHER, decision="Validado")

    stored = sc.get_project(project["id"])
    assert stored["status"] == "En Revisión"
    assert stored["decision_at"] is None
    assert stored["active_review_seconds"] is None


def test_active_review_seconds_uses_quality_metrics(people, clock):
    opened = submitted_and_opened(clock)
    opened_at = clock.now
    clock.advance(270)

    decided = sc.register_teacher_decision(opened["id"], teacher_email=TEACHER, decision="Validado")

    assert decided["active_review_seconds"] == teacher_active_time_seconds(opened_at, clock.now) == 270
    assert decided["decision_at"] == clock.now.isoformat()


@pytest.mark.parametrize(("elapsed", "expected", "within_target"), [(300, 300, True), (300.4, 301, False)])
def test_active_review_seconds_rounds_up_like_sla_target(people, clock, elapsed, expected, within_target):
    opened = submitted_and_opened(clock)
    opened_at = clock.now
    clock.advance(elapsed)

    decided = sc.register_teacher_decision(opened["id"], teacher_email=TEACHER, decision="Validado")

    assert decided["active_review_seconds"] == expected
    assert (decided["active_review_seconds"] <= 300) is within_target
    assert meets_teacher_time_target(opened_at, clock.now) is within_target


@pytest.mark.parametrize("feedback", [None, "", "  ok  "])
def test_observed_requires_feedback(people, clock, feedback):
    opened = submitted_and_opened(clock)

    with pytest.raises(sc.ProjectValidationError):
        sc.register_teacher_decision(opened["id"], teacher_email=TEACHER, decision="Observado", teacher_feedback=feedback)

    assert sc.get_project(opened["id"])["status"] == "En Revisión"


def test_validated_without_feedback_uses_default_comment(people, clock):
    opened = submitted_and_opened(clock)

    decided = sc.register_teacher_decision(opened["id"], teacher_email=TEACHER, decision="Validado")

    assert decided["teacher_feedback"] == "Acreditación conforme."


def test_decision_is_registered_only_once(people, clock):
    opened = submitted_and_opened(clock)
    sc.register_teacher_decision(opened["id"], teacher_email=TEACHER, decision="Validado")

    with pytest.raises(sc.InvalidTransitionError) as error:
        sc.register_teacher_decision(
            opened["id"], teacher_email=TEACHER, decision="Observado", teacher_feedback="Cambio de opinión"
        )

    assert error.value.current_status == "Validado"
    assert sc.get_project(opened["id"])["status"] == "Validado"


def test_decision_rejects_other_teacher_and_invalid_verdict(people, clock):
    opened = submitted_and_opened(clock)

    with pytest.raises(sc.NotAuthorizedError):
        sc.register_teacher_decision(opened["id"], teacher_email=OTHER_TEACHER, decision="Validado")
    with pytest.raises(sc.ProjectValidationError):
        sc.register_teacher_decision(opened["id"], teacher_email=TEACHER, decision="Aprobado")


def test_validated_technologies_replace_stack_and_are_marked(people, clock):
    opened = submitted_and_opened(clock)

    decided = sc.register_teacher_decision(
        opened["id"], teacher_email=TEACHER, decision="Validado", validated_technologies=["Python", " PostgreSQL "]
    )

    assert decided["tech_stack"] == ["Python", "PostgreSQL"]
    rows = [tech for tech in sc._local_backend.technologies if tech["project_id"] == opened["id"]]
    assert {tech["technology_name"] for tech in rows} == {"Python", "PostgreSQL"}
    assert all(tech["validated_by_teacher"] for tech in rows)


def test_observed_technologies_are_not_marked_as_validated(people, clock):
    opened = submitted_and_opened(clock)

    sc.register_teacher_decision(
        opened["id"], teacher_email=TEACHER, decision="Observado", teacher_feedback="Falta documentar las pruebas."
    )

    rows = [tech for tech in sc._local_backend.technologies if tech["project_id"] == opened["id"]]
    assert rows and not any(tech["validated_by_teacher"] for tech in rows)


# ---------------------------------------------------------------------------
# Flujo completo y listados
# ---------------------------------------------------------------------------
def test_full_flow_from_draft_to_validated(people, clock):
    project = new_project()
    sc.save_project_evidence(project["id"], github_url="https://github.com/equipo6/proyecto", evidence_text="README")

    clock.advance(60)
    first_submission = submit(project["id"])
    clock.advance(30)
    sc.mark_project_opened(project["id"], teacher_email=TEACHER)
    clock.advance(90)
    observed = sc.register_teacher_decision(
        project["id"], teacher_email=TEACHER, decision="Observado", teacher_feedback="Agrega pruebas unitarias."
    )
    assert observed["status"] == "Observado"
    assert observed["active_review_seconds"] == 90

    clock.advance(600)
    sc.save_project_evidence(project["id"], evidence_text="README con pruebas")
    resubmitted = submit(project["id"], tech_stack=["Python", "FastAPI", "Pytest"])
    assert resubmitted["status"] == "En Revisión"
    assert resubmitted["submitted_at"] != first_submission["submitted_at"]
    assert resubmitted["opened_by_teacher_at"] is None
    assert resubmitted["decision_at"] is None
    assert resubmitted["active_review_seconds"] is None
    assert resubmitted["teacher_feedback"] == "Agrega pruebas unitarias."

    clock.advance(20)
    sc.mark_project_opened(project["id"], teacher_email=TEACHER)
    clock.advance(45)
    validated = sc.register_teacher_decision(project["id"], teacher_email=TEACHER, decision="Validado")

    assert validated["status"] == "Validado"
    assert validated["active_review_seconds"] == 45
    assert validated["teacher_feedback"] == "Acreditación conforme."
    assert validated["tech_stack"] == ["Python", "FastAPI", "Pytest"]
    assert validated["github_url"] == "https://github.com/equipo6/proyecto"
    assert sc.get_project(project["id"]) == validated


def test_list_projects_by_student_returns_only_own(people):
    mine = new_project()
    new_project(student_email=OTHER_STUDENT)

    listed = sc.list_projects_by_student("ALUMNO.QA@unmsm.edu.pe")

    assert [project["id"] for project in listed] == [mine["id"]]
    assert sc.list_projects_by_student("sin.cuenta@unmsm.edu.pe") == []
    with pytest.raises(sc.ProjectValidationError):
        sc.list_projects_by_student("alumno@gmail.com")


def test_list_pending_reviews_by_teacher_and_all(people, clock):
    draft = new_project(title="Proyecto en borrador")
    mine = new_project(title="Proyecto del docente")
    clock.advance(5)
    other = new_project(title="Proyecto de otro docente", teacher_email=OTHER_TEACHER)
    submit(mine["id"])
    clock.advance(5)
    submit(other["id"])

    assert [p["id"] for p in sc.list_pending_reviews(TEACHER)] == [mine["id"]]
    assert [p["id"] for p in sc.list_pending_reviews()] == [mine["id"], other["id"]]
    assert sc.list_pending_reviews("sin.cuenta@unmsm.edu.pe") == []
    assert draft["id"] not in {p["id"] for p in sc.list_pending_reviews()}


# ---------------------------------------------------------------------------
# El modo local aplica las mismas restricciones que la base
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("changes", "constraint"),
    [
        (lambda t: {"status": "Aprobado"}, "projects_status_check"),
        (lambda t: {"consent_at": None}, "projects_consent_check"),
        (lambda t: {"professional_summary": None}, "projects_submission_check"),
        (lambda t: {"opened_by_teacher_at": t["submitted"] - timedelta(seconds=1)}, "projects_opened_check"),
        (
            lambda t: {"status": "Validado", "decision_at": t["opened"] - timedelta(seconds=1), "active_review_seconds": 1},
            "projects_decision_check",
        ),
        (lambda t: {"status": "Validado"}, "projects_decision_status_check"),
        (lambda t: {"active_review_seconds": 5}, "projects_review_seconds_check"),
        (
            lambda t: {"status": "Observado", "decision_at": t["opened"], "active_review_seconds": 0, "teacher_feedback": " ok "},
            "projects_observed_feedback_check",
        ),
        (lambda t: {"evidence_hash": "ABC123"}, "projects_evidence_hash_check"),
        (lambda t: {"github_url": "javascript:alert(1)"}, "projects_github_url_check"),
        # 04: fuera de 'Validado' rigen las reglas de consentimiento de la 02 y no hay sello
        (lambda t: {"consent_law_29733": False}, "projects_consent_check"),
        (lambda t: {"consent_revoked_at": t["submitted"] - timedelta(seconds=1)}, "projects_consent_revoked_check"),
        (lambda t: {"verification_code": "fisi-2026-abc234"}, "projects_verification_code_check"),
        (lambda t: {"verification_code": "FISI-2026-ABC234"}, "projects_verification_code_status_check"),
    ],
)
def test_local_store_enforces_database_check_constraints(people, clock, changes, constraint):
    project = new_project()
    submit(project["id"])
    submitted_at = clock.now
    clock.advance(10)
    sc.mark_project_opened(project["id"])
    times = {"submitted": submitted_at, "opened": clock.now}
    before = dict(sc._local_backend.projects[project["id"]])

    with pytest.raises(sc.DatabaseError) as error:
        sc._local_backend.update_project(project["id"], changes(times))

    assert error.value.code == "23514"
    assert error.value.constraint == constraint
    assert sc._local_backend.projects[project["id"]] == before


def test_local_store_enforces_unique_and_foreign_keys(people):
    project = new_project()
    course_id = sc._local_backend.projects[project["id"]]["course_id"]
    teacher_id = sc._local_backend.courses[course_id]["teacher_id"]

    with pytest.raises(sc.DatabaseError) as duplicated_email:
        sc.register_local_user(email=STUDENT, full_name="Duplicado")
    with pytest.raises(sc.DatabaseError) as duplicated_course:
        sc._local_backend.insert_course(
            {"code": "AUTO-DUP", "name": "GESTIÓN DE PROYECTOS DE TI", "cycle": 8, "teacher_id": teacher_id}
        )
    with pytest.raises(sc.DatabaseError) as missing_student:
        sc._local_backend.insert_project({"title": "Sin dueño", "course_id": course_id, "student_id": str(uuid.uuid4())})

    assert (duplicated_email.value.code, duplicated_email.value.constraint) == ("23505", "users_email_key")
    assert (duplicated_course.value.code, duplicated_course.value.constraint) == ("23505", "courses_teacher_name_key")
    assert (missing_student.value.code, missing_student.value.constraint) == ("23503", "projects_student_id_fkey")


# ---------------------------------------------------------------------------
# Sprint 3 - HU10: código de verificación del sello docente
# ---------------------------------------------------------------------------
CODE_PATTERN = re.compile(r"FISI-2026-[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{6}")
MIGRATION_04 = Path(__file__).resolve().parents[1] / "database" / "04_sprint3_portfolio.sql"


def validated_project(clock, **overrides):
    project = new_project(**overrides)
    clock.advance(10)
    submit(project["id"])
    clock.advance(10)
    sc.mark_project_opened(project["id"])
    clock.advance(60)
    teacher = overrides.get("teacher_email", TEACHER)
    return sc.register_teacher_decision(project["id"], teacher_email=teacher, decision="Validado")


def public_ids(identifier=STUDENT):
    return [project["project_id"] for project in sc.get_public_portfolio_projects(identifier)["projects"]]


def test_generated_verification_codes_follow_format():
    codes = {sc.generate_verification_code() for _ in range(300)}

    assert all(CODE_PATTERN.fullmatch(code) for code in codes)
    assert len(codes) > 290


def test_validation_generates_code_and_observation_does_not(people, clock):
    validated = validated_project(clock)
    opened = submitted_and_opened(clock)
    observed = sc.register_teacher_decision(
        opened["id"], teacher_email=TEACHER, decision="Observado", teacher_feedback="Falta documentar las pruebas."
    )

    assert CODE_PATTERN.fullmatch(validated["verification_code"])
    assert sc.get_project(validated["id"])["verification_code"] == validated["verification_code"]
    assert observed["verification_code"] is None


def test_verification_code_retries_when_code_already_exists(people, clock, monkeypatch):
    first = validated_project(clock)
    candidates = iter([first["verification_code"], "FISI-2026-NEW234"])
    generated = []

    def next_code():
        generated.append(next(candidates))
        return generated[-1]

    monkeypatch.setattr(sc, "generate_verification_code", next_code)
    second = validated_project(clock, student_email=OTHER_STUDENT)

    assert second["verification_code"] == "FISI-2026-NEW234"
    assert generated == [first["verification_code"], "FISI-2026-NEW234"]


def test_verification_code_gives_up_after_max_attempts_without_changes(people, clock, monkeypatch):
    first = validated_project(clock)
    opened = submitted_and_opened(clock)
    original_generator = sc.generate_verification_code
    attempts = []
    monkeypatch.setattr(sc, "generate_verification_code", lambda: attempts.append(1) or first["verification_code"])

    with pytest.raises(sc.DatabaseError) as error:
        sc.register_teacher_decision(opened["id"], teacher_email=TEACHER, decision="Validado")

    assert error.value.http_status == 503
    assert len(attempts) == sc.MAX_VERIFICATION_CODE_ATTEMPTS
    stored = sc.get_project(opened["id"])
    assert (stored["status"], stored["verification_code"]) == ("En Revisión", None)

    monkeypatch.setattr(sc, "generate_verification_code", original_generator)
    retried = sc.register_teacher_decision(opened["id"], teacher_email=TEACHER, decision="Validado")
    assert CODE_PATTERN.fullmatch(retried["verification_code"])


# ---------------------------------------------------------------------------
# Sprint 3 - HU11 / R06: consentimiento de publicación (Ley N.° 29733)
# ---------------------------------------------------------------------------
def test_revoking_consent_hides_project_immediately(people, clock):
    validated = validated_project(clock)
    assert public_ids() == [validated["id"]]
    clock.advance(3600)

    revoked = sc.update_project_privacy_consent(validated["id"], False, student_email="  ALUMNO.QA@unmsm.edu.pe ")

    assert revoked["consent_law_29733"] is False
    assert revoked["consent_revoked_at"] == clock.now.isoformat()
    assert revoked["consent_timestamp"] == validated["consent_timestamp"]
    assert revoked["status"] == "Validado"
    assert revoked["verification_code"] == validated["verification_code"]
    assert sc.get_project(validated["id"]) == revoked
    with pytest.raises(sc.PortfolioNotFoundError):
        sc.get_public_portfolio_projects(STUDENT)


def test_consent_can_be_reactivated_and_keeps_last_revocation(people, clock):
    validated = validated_project(clock)
    clock.advance(60)
    revoked = sc.update_project_privacy_consent(validated["id"], False)
    clock.advance(60)

    with pytest.raises(sc.DatabaseError) as without_new_date:
        sc._local_backend.update_project(validated["id"], {"consent_law_29733": True})
    active = sc.update_project_privacy_consent(validated["id"], True, student_email=STUDENT)

    assert without_new_date.value.constraint == "projects_consent_check"
    assert active["consent_law_29733"] is True
    assert active["consent_timestamp"] == clock.now.isoformat()
    assert active["consent_revoked_at"] == revoked["consent_revoked_at"]
    assert public_ids() == [validated["id"]]


def test_privacy_consent_with_same_value_changes_nothing(people, clock):
    validated = validated_project(clock)
    clock.advance(60)
    assert sc.update_project_privacy_consent(validated["id"], True) == validated

    revoked = sc.update_project_privacy_consent(validated["id"], False)
    clock.advance(60)
    assert sc.update_project_privacy_consent(validated["id"], False) == revoked


@pytest.mark.parametrize("status", ["Borrador", "En Revisión", "Observado"])
def test_privacy_consent_only_for_validated_projects(people, clock, status):
    project = new_project()
    if status != "Borrador":
        submit(project["id"])
    if status == "Observado":
        sc.mark_project_opened(project["id"])
        sc.register_teacher_decision(
            project["id"], teacher_email=TEACHER, decision="Observado", teacher_feedback="Falta documentar las pruebas."
        )
    before = sc.get_project(project["id"])

    with pytest.raises(sc.InvalidTransitionError) as error:
        sc.update_project_privacy_consent(project["id"], False)

    assert (error.value.current_status, error.value.http_status) == (status, 409)
    assert sc.get_project(project["id"]) == before


def test_privacy_consent_rejects_other_student_and_invalid_input(people, clock):
    validated = validated_project(clock)

    with pytest.raises(sc.NotAuthorizedError) as other_student:
        sc.update_project_privacy_consent(validated["id"], False, student_email=OTHER_STUDENT)
    for value in (None, "false", 0):
        with pytest.raises(sc.ProjectValidationError):
            sc.update_project_privacy_consent(validated["id"], value)
    with pytest.raises(sc.ProjectNotFoundError):
        sc.update_project_privacy_consent(str(uuid.uuid4()), False)

    assert other_student.value.http_status == 403
    assert sc.get_project(validated["id"]) == validated


# ---------------------------------------------------------------------------
# Sprint 3 - HU11: portafolio público
# ---------------------------------------------------------------------------
def test_public_portfolio_shows_only_validated_projects_with_active_consent(people, clock):
    new_project(title="Proyecto en borrador")
    submit(new_project(title="Proyecto en revisión")["id"])
    observed = submitted_and_opened(clock)
    sc.register_teacher_decision(
        observed["id"], teacher_email=TEACHER, decision="Observado", teacher_feedback="Falta documentar las pruebas."
    )
    revoked = validated_project(clock, title="Proyecto validado y revocado")
    sc.update_project_privacy_consent(revoked["id"], False)
    visible = validated_project(clock, title="Proyecto validado visible")
    validated_project(clock, student_email=OTHER_STUDENT)

    assert public_ids() == [visible["id"]]


def test_public_portfolio_returns_only_public_data_without_emails(people, clock):
    graduate = sc.register_local_user(
        email="egresada.qa@unmsm.edu.pe",
        full_name="Egresada QA",
        school="Ingeniería de Software",
        current_cycle=9,
        linkedin_url="https://www.linkedin.com/in/egresada-qa",
        github_url="https://github.com/egresada-qa",
    )
    project = new_project(student_email="egresada.qa@unmsm.edu.pe")
    submit(project["id"], tech_stack=["Python", "FastAPI"])
    sc.mark_project_opened(project["id"])
    clock.advance(60)
    validated = sc.register_teacher_decision(
        project["id"], teacher_email=TEACHER, decision="Validado", validated_technologies=["Python", "PostgreSQL"]
    )

    portfolio = sc.get_public_portfolio_projects(graduate["id"])

    assert portfolio == {
        "student": {
            "id": graduate["id"],
            "full_name": "Egresada QA",
            "school": "Ingeniería de Software",
            "current_cycle": 9,
            "linkedin_url": "https://www.linkedin.com/in/egresada-qa",
            "github_url": "https://github.com/egresada-qa",
        },
        "projects": [
            {
                "project_id": project["id"],
                "title": "Portafolio académico SkillFISI",
                "course_name": "Gestión de Proyectos de TI",
                "professional_summary": SUMMARY,
                "validated_technologies": ["Python", "PostgreSQL"],
                "verification_code": validated["verification_code"],
                "decision_at": clock.now.isoformat(),
                "teacher_full_name": "Docente QA",
            }
        ],
    }
    assert "@" not in repr(portfolio)


def test_public_portfolio_accepts_id_or_email_and_orders_by_validation(people, clock):
    older = validated_project(clock, title="Proyecto validado primero")
    newer = validated_project(clock, title="Proyecto validado después")
    student_id = sc._local_backend.find_user_by_email(STUDENT)["id"]

    by_email = sc.get_public_portfolio_projects("  ALUMNO.QA@unmsm.edu.pe ")
    by_id = sc.get_public_portfolio_projects(student_id.upper())

    assert by_email == by_id
    assert [project["project_id"] for project in by_id["projects"]] == [newer["id"], older["id"]]


def test_public_portfolio_not_found_is_the_same_for_every_case(people, clock):
    validated_project(clock)
    new_project(student_email=OTHER_STUDENT)
    teacher_id = sc._local_backend.find_user_by_email(TEACHER)["id"]

    for identifier in (str(uuid.uuid4()), "sin.cuenta@unmsm.edu.pe", TEACHER, teacher_id, OTHER_STUDENT):
        with pytest.raises(sc.PortfolioNotFoundError) as error:
            sc.get_public_portfolio_projects(identifier)
        assert (error.value.http_status, str(error.value)) == (404, sc.PORTFOLIO_NOT_FOUND_DETAIL)
    assert issubclass(sc.PortfolioNotFoundError, sc.ProjectNotFoundError)


@pytest.mark.parametrize("identifier", ["", "   ", None, "alumno@gmail.com", "no-es-un-id", "alumno.qa"])
def test_public_portfolio_rejects_invalid_identifier(people, identifier):
    with pytest.raises(sc.ProjectValidationError):
        sc.get_public_portfolio_projects(identifier)


# ---------------------------------------------------------------------------
# Sprint 3 - el modo local aplica las restricciones de la 04
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("changes", "constraint"),
    [
        (lambda p: {"consent_law_29733": False}, "projects_consent_check"),
        (
            lambda p: {"consent_law_29733": False, "consent_revoked_at": p["consent_at"] - timedelta(seconds=1)},
            "projects_consent_check",
        ),
        (
            lambda p: {"consent_law_29733": False, "consent_at": None, "consent_revoked_at": p["decision_at"]},
            "projects_consent_revoked_check",
        ),
        (lambda p: {"verification_code": None}, "projects_verification_code_status_check"),
        (lambda p: {"verification_code": "FISI-2026-ABC2345"}, "projects_verification_code_check"),
    ],
)
def test_local_store_enforces_sprint3_constraints_on_validated_project(people, clock, changes, constraint):
    validated = validated_project(clock)
    before = dict(sc._local_backend.projects[validated["id"]])

    with pytest.raises(sc.DatabaseError) as error:
        sc._local_backend.update_project(validated["id"], changes(before))

    assert (error.value.code, error.value.constraint) == ("23514", constraint)
    assert sc._local_backend.projects[validated["id"]] == before


def test_local_store_enforces_unique_verification_code(people, clock):
    first = validated_project(clock)
    second = validated_project(clock, student_email=OTHER_STUDENT)

    with pytest.raises(sc.DatabaseError) as error:
        sc._local_backend.update_project(second["id"], {"verification_code": first["verification_code"]})

    assert (error.value.code, error.value.constraint) == ("23505", "projects_verification_code_key")


def test_local_portfolio_rows_match_public_view_of_migration_04(people, clock):
    view = re.search(
        r"CREATE VIEW public\.public_verified_portfolios(.*?);", MIGRATION_04.read_text(encoding="utf-8"), re.S
    ).group(1)
    select_list, conditions = view.split("\nFROM public.projects p")
    validated = validated_project(clock)
    student_id = sc._local_backend.find_user_by_email(STUDENT)["id"]

    rows = sc._local_backend.fetch_public_portfolio(student_id)

    assert re.findall(r"\bAS ([a-z_]+)\b", select_list) == list(sc.PUBLIC_PORTFOLIO_COLUMNS)
    assert [list(row) for row in rows] == [list(sc.PUBLIC_PORTFOLIO_COLUMNS)]
    assert rows[0]["project_id"] == validated["id"]
    assert "email" not in view
    assert "WHERE p.status = 'Validado'" in conditions and "AND p.consent_law_29733" in conditions


def test_supabase_portfolio_query_reads_only_the_public_view(monkeypatch):
    calls = []

    class FakeQuery:
        def __getattr__(self, name):
            def method(*args, **kwargs):
                calls.append((name, args, kwargs))
                return self

            return method

        def execute(self):
            return type("Result", (), {"data": []})()

    class FakeClient:
        def table(self, name):
            calls.append(("table", (name,), {}))
            return FakeQuery()

    monkeypatch.setattr(sc, "get_admin_client", lambda: FakeClient())

    assert sc._SupabaseBackend().fetch_public_portfolio("id-del-estudiante") == []
    assert calls == [
        ("table", ("public_verified_portfolios",), {}),
        ("select", (",".join(sc.PUBLIC_PORTFOLIO_COLUMNS),), {}),
        ("eq", ("student_id", "id-del-estudiante"), {}),
        ("order", ("decision_at",), {"desc": True}),
        ("order", ("project_id",), {}),
    ]
