"""Conexión con Supabase y persistencia de proyectos del backend (Módulos 3.1 a 3.4).

Se usan dos tipos de cliente:
- Administrador (clave service_role): solo vive en el backend y omite RLS,
  por eso cada endpoint debe validar antes quién hace la petición.
- Autenticación (clave anon): se crea uno nuevo por cada inicio de sesión
  para que las sesiones de distintos usuarios nunca se mezclen.

Persistencia de proyectos (HU03, HU04, HU06 y HU07):
- Las funciones públicas reciben los datos tal como los usan routers/projects.py y
  routers/teacher_reviews.py (correos, course_name, cycle) y devuelven un diccionario
  plano con las mismas claves que PROJECTS_DB.
- Modo "supabase": tablas de database/01_schema.sql y 02_sprint2_migration.sql.
- Modo "local": memoria del proceso (pruebas y CI), con las mismas restricciones que la base.
  El modo se decide una sola vez (ver resolve_persistence_mode) y nunca cambia por un
  error de red: si Supabase falla se lanza DatabaseError.

Errores que lanzan las funciones y código HTTP que debe devolver el router
(todos heredan de ProjectRepositoryError y traen ese código en http_status):
- ProjectValidationError (también es ValueError) -> 400: dato de entrada inválido.
- NotAuthorizedError -> 403: el correo no es del estudiante dueño ni del docente del curso.
- ProjectNotFoundError -> 404: el proyecto no existe.
- InvalidTransitionError -> 409: el estado actual no permite la operación.
- ReferenceNotFoundError -> 422: el estudiante o el docente no tiene cuenta en SkillFISI.
- DatabaseError -> 503: Supabase no respondió o rechazó la operación.

Uso en un router:

    try:
        project = supabase_client.update_project_review_submission(project_id, ...)
    except supabase_client.ProjectRepositoryError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc))
"""

import hashlib
import logging
import math
import os
import re
import threading
import uuid
from collections.abc import Iterable, Mapping
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse, urlsplit

from dotenv import load_dotenv
from supabase import Client, ClientOptions, PostgrestAPIError, create_client

from services.evidence_extractor import GITHUB_OWNER_PATTERN, GITHUB_REPOSITORY_PATTERN
from services.quality_metrics import teacher_active_time_seconds
from services.validators import is_institutional_email

# Carga backend/.env sin importar desde qué carpeta se levante el servidor.
# Las variables ya definidas en el sistema (por ejemplo, en el despliegue) tienen prioridad.
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH)

logger = logging.getLogger(__name__)


class SupabaseConfigError(RuntimeError):
    """Falta una variable de entorno necesaria para conectarse a Supabase."""


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SupabaseConfigError(
            f"Falta la variable {name} en backend/.env (usa backend/.env.example como guía)."
        )
    return value


def _project_url() -> str:
    """URL base del proyecto. Se descarta cualquier ruta (por ejemplo /rest/v1/) copiada por error,
    porque la librería agrega por su cuenta /rest/v1 y /auth/v1."""
    parsed = urlparse(_require_env("SUPABASE_URL"))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SupabaseConfigError(
            "SUPABASE_URL no es válida (ejemplo: https://tu-proyecto.supabase.co)."
        )
    return f"{parsed.scheme}://{parsed.netloc}"


def _server_options() -> ClientOptions:
    # El backend no guarda sesiones ni renueva tokens en segundo plano.
    return ClientOptions(auto_refresh_token=False, persist_session=False)


@lru_cache(maxsize=1)
def get_admin_client() -> Client:
    """Cliente compartido con la clave service_role. Nunca debe llegar al frontend."""
    return create_client(
        _project_url(),
        _require_env("SUPABASE_SERVICE_ROLE_KEY"),
        options=_server_options(),
    )


def create_auth_client() -> Client:
    """Cliente nuevo con la clave anon, pensado para un único inicio de sesión."""
    return create_client(
        _project_url(),
        _require_env("SUPABASE_ANON_KEY"),
        options=_server_options(),
    )


# ===========================================================================
# Persistencia de proyectos
# ===========================================================================
PersistenceMode = Literal["supabase", "local"]
TeacherDecision = Literal["Validado", "Observado"]

STATUS_DRAFT = "Borrador"
STATUS_IN_REVIEW = "En Revisión"
STATUS_VALIDATED = "Validado"
STATUS_OBSERVED = "Observado"
PROJECT_STATUSES = (STATUS_DRAFT, STATUS_IN_REVIEW, STATUS_VALIDATED, STATUS_OBSERVED)
EDITABLE_STATUSES = (STATUS_DRAFT, STATUS_OBSERVED)  # admiten evidencia nueva y envío a revisión
TEACHER_DECISIONS = (STATUS_VALIDATED, STATUS_OBSERVED)
USER_ROLES = ("Estudiante", "Docente", "Autoridad")

CURRENT_SEMESTER = "2026-2"
DEFAULT_VALIDATION_FEEDBACK = "Acreditación conforme."
MIN_OBSERVATION_FEEDBACK_CHARS = 5
MAX_FEEDBACK_CHARS = 1000
MAX_TECHNOLOGY_NAME_CHARS = 100

USERS_TABLE = "users"
COURSES_TABLE = "courses"
PROJECTS_TABLE = "projects"
TECHNOLOGIES_TABLE = "project_technologies"

# Proyecto con su estudiante, su curso (con el docente) y sus tecnologías en una sola consulta.
# Los nombres de las claves foráneas evitan la ambigüedad users <-> courses a través de projects.
_PROJECT_SELECT = (
    "*,"
    "student:users!projects_student_id_fkey(email),"
    "course:courses(name,cycle,teacher_id,teacher:users!courses_teacher_id_fkey(email)),"
    "project_technologies(technology_name,validated_by_teacher,created_at)"
)

DB_ERROR_DETAIL = "No se pudo acceder a la base de datos. Intenta nuevamente."
CONSENT_REQUIRED_DETAIL = (
    "Cumplimiento legal obligatorio: Debes aceptar el consentimiento de la Ley N.° 29733 "
    "para enviar el proyecto a revisión."
)
OBSERVATION_FEEDBACK_DETAIL = (
    "Al observar un proyecto es obligatorio detallar la retroalimentación para el estudiante."
)
NOT_OPENED_DETAIL = (
    "Primero abre el proyecto en la bandeja: no se puede registrar una decisión sin la apertura previa."
)
EVIDENCE_STATE_DETAIL = (
    "Solo se puede cambiar la evidencia de un proyecto en 'Borrador' u 'Observado' (estado actual: {status})."
)
SUBMIT_STATE_DETAIL = (
    "Solo se puede enviar a revisión un proyecto en 'Borrador' u 'Observado' (estado actual: {status})."
)
OPEN_STATE_DETAIL = (
    "El proyecto debe estar 'En Revisión' para iniciar evaluación (estado actual: {status})."
)
DECISION_STATE_DETAIL = (
    "Solo se pueden evaluar proyectos en estado 'En Revisión' (estado actual: {status})."
)


# ---------------------------------------------------------------------------
# Errores
# ---------------------------------------------------------------------------
class ProjectRepositoryError(Exception):
    """Base de los errores de persistencia. http_status es el código que debe responder el router."""

    http_status = 500


class ProjectValidationError(ProjectRepositoryError, ValueError):
    """Dato de entrada inválido -> 400."""

    http_status = 400


class NotAuthorizedError(ProjectRepositoryError):
    """El correo indicado no es del estudiante dueño ni del docente del curso -> 403."""

    http_status = 403


class ProjectNotFoundError(ProjectRepositoryError):
    """El proyecto no existe -> 404."""

    http_status = 404

    def __init__(self, message: str = "Proyecto no encontrado."):
        super().__init__(message)


class InvalidTransitionError(ProjectRepositoryError):
    """El estado actual del proyecto no permite la operación -> 409."""

    http_status = 409

    def __init__(self, message: str, current_status: str | None = None):
        super().__init__(message)
        self.current_status = current_status


class ReferenceNotFoundError(ProjectRepositoryError):
    """El estudiante o el docente indicado no tiene cuenta en SkillFISI -> 422."""

    http_status = 422


class DatabaseError(ProjectRepositoryError):
    """Supabase no respondió o rechazó la operación -> 503.

    code guarda el SQLSTATE cuando se conoce (por ejemplo, 23514 para una restricción CHECK)
    y constraint el nombre de la restricción violada en el modo local.
    """

    http_status = 503

    def __init__(self, message: str = DB_ERROR_DETAIL, code: str | None = None, constraint: str | None = None):
        super().__init__(message)
        self.code = code
        self.constraint = constraint


# ---------------------------------------------------------------------------
# Modo de persistencia
# ---------------------------------------------------------------------------
def resolve_persistence_mode(env: Mapping[str, str]) -> PersistenceMode:
    """Decide dónde se guardan los proyectos, en este orden:

    1. APP_ENV=production: siempre Supabase. Si faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY,
       o si se pide SKILLFISI_PERSISTENCE=local, lanza SupabaseConfigError.
    2. SKILLFISI_PERSISTENCE=local: modo local (lo fija tests/conftest.py).
    3. SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY definidas: Supabase.
    4. Ninguna de las dos y CI=true (GitHub Actions lo define solo): modo local.
    5. Cualquier otro caso (variables a medias, o ausentes fuera de la CI): SupabaseConfigError.
    """

    def read(name: str) -> str:
        return (env.get(name) or "").strip()

    app_env = read("APP_ENV").casefold()
    forced = read("SKILLFISI_PERSISTENCE").casefold()
    has_url = bool(read("SUPABASE_URL"))
    has_key = bool(read("SUPABASE_SERVICE_ROLE_KEY"))

    if forced not in {"", "local"}:
        raise SupabaseConfigError("SKILLFISI_PERSISTENCE solo admite el valor 'local' o quedar vacía.")
    if app_env == "production":
        if forced == "local":
            raise SupabaseConfigError("APP_ENV=production no permite SKILLFISI_PERSISTENCE=local.")
        if not (has_url and has_key):
            raise SupabaseConfigError(
                "APP_ENV=production exige SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY."
            )
        return "supabase"
    if forced == "local":
        return "local"
    if has_url and has_key:
        return "supabase"
    if not has_url and not has_key and read("CI").casefold() == "true":
        return "local"
    raise SupabaseConfigError(
        "Faltan SUPABASE_URL y/o SUPABASE_SERVICE_ROLE_KEY en backend/.env "
        "(o define SKILLFISI_PERSISTENCE=local para trabajar sin Supabase)."
    )


@lru_cache(maxsize=1)
def get_persistence_mode() -> PersistenceMode:
    """Modo de persistencia del proceso. Se calcula una sola vez y no cambia por errores de red."""
    mode = resolve_persistence_mode(os.environ)
    if mode == "local":
        logger.warning(
            "Persistencia en modo local: los proyectos viven solo en memoria y se pierden al reiniciar."
        )
    return mode


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Validación y normalización de datos de entrada
# ---------------------------------------------------------------------------
def normalize_github_url(url: str) -> str:
    """Devuelve el enlace en la forma https://github.com/usuario/repositorio.

    Acepta www.github.com, el sufijo .git y una barra final. Lanza ProjectValidationError
    (que también es ValueError) si el enlace no apunta a la raíz de un repositorio de GitHub.
    """
    invalid = ProjectValidationError(
        "El enlace del repositorio debe tener la forma https://github.com/usuario/repositorio."
    )
    if not isinstance(url, str) or not url.strip():
        raise invalid

    candidate = url.strip()
    if any(char.isspace() for char in candidate):
        raise ProjectValidationError("El enlace del repositorio no debe contener espacios.")

    try:
        parts = urlsplit(candidate)
        port = parts.port
    except ValueError:
        raise invalid from None

    if (
        parts.scheme != "https"
        or parts.hostname not in {"github.com", "www.github.com"}
        or port is not None
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
    ):
        raise invalid

    segments = [segment for segment in parts.path.split("/") if segment]
    if len(segments) != 2:
        raise invalid

    owner, repository = segments
    if repository.endswith(".git"):
        repository = repository[:-4]
    if not GITHUB_OWNER_PATTERN.fullmatch(owner) or not GITHUB_REPOSITORY_PATTERN.fullmatch(repository):
        raise invalid

    return f"https://github.com/{owner}/{repository}"


def compute_evidence_hash(evidence_text: str) -> str:
    """SHA-256 en hexadecimal del texto de evidencia sin espacios al inicio ni al final."""
    return hashlib.sha256(evidence_text.strip().encode("utf-8")).hexdigest()


def _normalize_email(email: str, owner_label: str) -> str:
    if not isinstance(email, str) or not is_institutional_email(email):
        raise ProjectValidationError(
            f"El correo {owner_label} debe pertenecer al dominio institucional @unmsm.edu.pe."
        )
    return email.strip().casefold()


def _clean_text(value: str, label: str, min_length: int, max_length: int) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not min_length <= len(text) <= max_length:
        raise ProjectValidationError(f"{label} debe tener entre {min_length} y {max_length} caracteres.")
    return text


def _parse_cycle(cycle: str | int) -> int:
    """Convierte el ciclo del formulario ("8vo Ciclo", "8" u 8) al entero de courses.cycle."""
    if isinstance(cycle, int) and not isinstance(cycle, bool):
        number = cycle
    else:
        match = re.search(r"\d+", cycle) if isinstance(cycle, str) else None
        number = int(match.group()) if match else 0
    if not 1 <= number <= 10:
        raise ProjectValidationError("El ciclo debe indicar un número del 1 al 10 (por ejemplo, '8vo Ciclo').")
    return number


def _clean_technologies(names: Iterable[str] | None) -> list[str]:
    """Quita espacios, vacíos y repetidos (sin distinguir mayúsculas), respetando el orden."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for name in names or []:
        if not isinstance(name, str):
            raise ProjectValidationError("Cada tecnología debe ser texto.")
        clean = name.strip()
        if not clean or clean.casefold() in seen:
            continue
        if len(clean) > MAX_TECHNOLOGY_NAME_CHARS:
            raise ProjectValidationError(
                f"El nombre de una tecnología no puede superar {MAX_TECHNOLOGY_NAME_CHARS} caracteres."
            )
        seen.add(clean.casefold())
        cleaned.append(clean)
    return cleaned


def _parse_project_id(project_id: str) -> str:
    try:
        return str(uuid.UUID(str(project_id)))
    except ValueError:
        raise ProjectNotFoundError() from None


def _parse_timestamp(value: datetime | str | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _iso(value: datetime | str | None) -> str | None:
    moment = _parse_timestamp(value)
    return moment.astimezone(timezone.utc).isoformat() if moment else None


def _serialize(row: Mapping) -> dict:
    return {key: value.isoformat() if isinstance(value, datetime) else value for key, value in row.items()}


# ---------------------------------------------------------------------------
# Restricciones de la base replicadas en el modo local
# (deben coincidir con 01_schema.sql y 02_sprint2_migration.sql)
# ---------------------------------------------------------------------------
_GITHUB_URL_DB_PATTERN = re.compile(r"^https://(www\.)?github\.com/[^/?#]+/[^/?#]+")
_EVIDENCE_HASH_DB_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _is_after_or_equal(later: datetime | None, earlier: datetime | None) -> bool:
    return later is not None and earlier is not None and later >= earlier


_PROJECT_CHECKS = (
    ("projects_status_check", lambda p: p["status"] in PROJECT_STATUSES),
    ("projects_consent_check", lambda p: p["consent_law_29733"] == (p["consent_at"] is not None)),
    (
        "projects_submission_check",
        lambda p: p["status"] == STATUS_DRAFT
        or (p["consent_law_29733"] and p["submitted_at"] is not None and p["professional_summary"] is not None),
    ),
    (
        "projects_opened_check",
        lambda p: p["opened_by_teacher_at"] is None or _is_after_or_equal(p["opened_by_teacher_at"], p["submitted_at"]),
    ),
    (
        "projects_decision_check",
        lambda p: p["decision_at"] is None or _is_after_or_equal(p["decision_at"], p["opened_by_teacher_at"]),
    ),
    (
        "projects_decision_status_check",
        lambda p: (p["status"] in TEACHER_DECISIONS) == (p["decision_at"] is not None),
    ),
    (
        "projects_review_seconds_check",
        lambda p: ((p["active_review_seconds"] is None) == (p["decision_at"] is None))
        and (p["active_review_seconds"] or 0) >= 0,
    ),
    (
        "projects_observed_feedback_check",
        lambda p: p["status"] != STATUS_OBSERVED
        or len((p["teacher_feedback"] or "").strip(" ")) >= MIN_OBSERVATION_FEEDBACK_CHARS,
    ),
    (
        "projects_evidence_hash_check",
        lambda p: p["evidence_hash"] is None or bool(_EVIDENCE_HASH_DB_PATTERN.match(p["evidence_hash"])),
    ),
    (
        "projects_github_url_check",
        lambda p: p["github_url"] is None or bool(_GITHUB_URL_DB_PATTERN.match(p["github_url"])),
    ),
)


def _check_local_project(row: dict) -> None:
    for name, is_valid in _PROJECT_CHECKS:
        if not is_valid(row):
            raise DatabaseError(code="23514", constraint=name)


# ---------------------------------------------------------------------------
# Almacenamientos: Supabase y local
# ---------------------------------------------------------------------------
class _SupabaseBackend:
    """Tablas reales de skillfisi-dev a través del cliente administrador."""

    @staticmethod
    def atomic():
        return nullcontext()

    @staticmethod
    def _execute(action: str, build_query):
        client = get_admin_client()
        try:
            return build_query(client).execute()
        except PostgrestAPIError as exc:
            logger.error("Supabase rechazó la operación '%s' (código %s)", action, exc.code)
            raise DatabaseError(code=exc.code) from exc
        except Exception as exc:
            logger.error("Error de conexión con Supabase en '%s': %s", action, type(exc).__name__)
            raise DatabaseError() from exc

    def find_user_by_email(self, email: str) -> dict | None:
        result = self._execute(
            "buscar usuario",
            lambda c: c.table(USERS_TABLE).select("id,email,full_name,role").eq("email", email).limit(1),
        )
        return result.data[0] if result.data else None

    def list_courses_for_teacher(self, teacher_id: str) -> list[dict]:
        result = self._execute(
            "listar cursos",
            lambda c: c.table(COURSES_TABLE).select("id,code,name,cycle,teacher_id").eq("teacher_id", teacher_id),
        )
        return result.data or []

    def insert_course(self, row: dict) -> dict:
        result = self._execute("crear curso", lambda c: c.table(COURSES_TABLE).insert(_serialize(row)))
        return result.data[0]

    def insert_project(self, row: dict) -> dict:
        result = self._execute("crear proyecto", lambda c: c.table(PROJECTS_TABLE).insert(_serialize(row)))
        return result.data[0]

    def fetch_projects(
        self,
        *,
        project_id: str | None = None,
        student_id: str | None = None,
        course_ids: list[str] | None = None,
        status: str | None = None,
    ) -> list[dict]:
        def build(c):
            query = c.table(PROJECTS_TABLE).select(_PROJECT_SELECT)
            if project_id is not None:
                query = query.eq("id", project_id)
            if student_id is not None:
                query = query.eq("student_id", student_id)
            if course_ids is not None:
                query = query.in_("course_id", course_ids)
            if status is not None:
                query = query.eq("status", status)
            return query.order("created_at")

        if course_ids is not None and not course_ids:
            return []
        return self._execute("consultar proyectos", build).data or []

    def update_project(
        self,
        project_id: str,
        changes: dict,
        *,
        statuses: Iterable[str] | None = None,
        opened_is_null: bool | None = None,
    ) -> dict | None:
        """UPDATE condicional: devuelve la fila actualizada o None si ninguna fila cumplía las condiciones."""

        def build(c):
            query = c.table(PROJECTS_TABLE).update(_serialize(changes)).eq("id", project_id)
            if statuses is not None:
                query = query.in_("status", list(statuses))
            if opened_is_null is True:
                query = query.is_("opened_by_teacher_at", "null")
            elif opened_is_null is False:
                query = query.not_.is_("opened_by_teacher_at", "null")
            return query

        result = self._execute("actualizar proyecto", build)
        return result.data[0] if result.data else None

    def replace_technologies(self, project_id: str, rows: list[dict]) -> None:
        self._execute(
            "borrar tecnologías",
            lambda c: c.table(TECHNOLOGIES_TABLE).delete().eq("project_id", project_id),
        )
        if rows:
            self._execute(
                "guardar tecnologías",
                lambda c: c.table(TECHNOLOGIES_TABLE).insert([_serialize(row) for row in rows]),
            )


class _LocalBackend:
    """Tablas en memoria con las mismas restricciones que la base (claves, UNIQUE y CHECK)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.users: dict[str, dict] = {}
            self.courses: dict[str, dict] = {}
            self.projects: dict[str, dict] = {}
            self.technologies: list[dict] = []

    @contextmanager
    def atomic(self):
        with self._lock:
            yield

    def add_user(self, row: dict) -> dict:
        with self._lock:
            if row["id"] in self.users:
                raise DatabaseError(code="23505", constraint="users_pkey")
            if any(user["email"] == row["email"] for user in self.users.values()):
                raise DatabaseError(code="23505", constraint="users_email_key")
            if row["role"] not in USER_ROLES:
                raise DatabaseError(code="23514", constraint="users_role_check")
            if not row["email"].endswith("@unmsm.edu.pe"):
                raise DatabaseError(code="23514", constraint="check_institutional_email")
            self.users[row["id"]] = dict(row)
            return dict(row)

    def find_user_by_email(self, email: str) -> dict | None:
        with self._lock:
            for user in self.users.values():
                if user["email"] == email:
                    return dict(user)
            return None

    def list_courses_for_teacher(self, teacher_id: str) -> list[dict]:
        with self._lock:
            return [dict(course) for course in self.courses.values() if course["teacher_id"] == teacher_id]

    def insert_course(self, row: dict) -> dict:
        with self._lock:
            course = {"id": str(uuid.uuid4()), "created_at": _utcnow(), **row}
            if any(existing["code"] == course["code"] for existing in self.courses.values()):
                raise DatabaseError(code="23505", constraint="courses_code_key")
            if not 1 <= course["cycle"] <= 10:
                raise DatabaseError(code="23514", constraint="courses_cycle_check")
            if course["teacher_id"] is not None:
                if course["teacher_id"] not in self.users:
                    raise DatabaseError(code="23503", constraint="courses_teacher_id_fkey")
                key = (course["teacher_id"], course["name"].lower())
                if any((c["teacher_id"], c["name"].lower()) == key for c in self.courses.values()):
                    raise DatabaseError(code="23505", constraint="courses_teacher_name_key")
            self.courses[course["id"]] = course
            return dict(course)

    def insert_project(self, row: dict) -> dict:
        with self._lock:
            project = {
                "id": str(uuid.uuid4()),
                "description": None,
                "status": STATUS_DRAFT,
                "consent_law_29733": False,
                "submitted_at": None,
                "opened_by_teacher_at": None,
                "decision_at": None,
                "created_at": _utcnow(),
                "teacher_feedback": None,
                "active_review_seconds": None,
                "evidence_hash": None,
                "professional_summary": None,
                "github_url": None,
                "consent_at": None,
                **row,
            }
            if project["student_id"] not in self.users:
                raise DatabaseError(code="23503", constraint="projects_student_id_fkey")
            if project["course_id"] not in self.courses:
                raise DatabaseError(code="23503", constraint="projects_course_id_fkey")
            _check_local_project(project)
            self.projects[project["id"]] = project
            return dict(project)

    def _joined(self, project: dict) -> dict:
        course = self.courses[project["course_id"]]
        teacher = self.users.get(course["teacher_id"]) if course["teacher_id"] else None
        return {
            **deepcopy(project),
            "student": {"email": self.users[project["student_id"]]["email"]},
            "course": {
                "name": course["name"],
                "cycle": course["cycle"],
                "teacher_id": course["teacher_id"],
                "teacher": {"email": teacher["email"]} if teacher else None,
            },
            "project_technologies": [
                {key: tech[key] for key in ("technology_name", "validated_by_teacher", "created_at")}
                for tech in self.technologies
                if tech["project_id"] == project["id"]
            ],
        }

    def fetch_projects(
        self,
        *,
        project_id: str | None = None,
        student_id: str | None = None,
        course_ids: list[str] | None = None,
        status: str | None = None,
    ) -> list[dict]:
        with self._lock:
            rows = [
                self._joined(project)
                for project in self.projects.values()
                if (project_id is None or project["id"] == project_id)
                and (student_id is None or project["student_id"] == student_id)
                and (course_ids is None or project["course_id"] in course_ids)
                and (status is None or project["status"] == status)
            ]
            return sorted(rows, key=lambda row: row["created_at"])

    def update_project(
        self,
        project_id: str,
        changes: dict,
        *,
        statuses: Iterable[str] | None = None,
        opened_is_null: bool | None = None,
    ) -> dict | None:
        with self._lock:
            current = self.projects.get(project_id)
            if current is None:
                return None
            if statuses is not None and current["status"] not in tuple(statuses):
                return None
            if opened_is_null is not None and (current["opened_by_teacher_at"] is None) != opened_is_null:
                return None
            candidate = {**current, **changes}
            _check_local_project(candidate)
            self.projects[project_id] = candidate
            return dict(candidate)

    def replace_technologies(self, project_id: str, rows: list[dict]) -> None:
        with self._lock:
            if project_id not in self.projects:
                raise DatabaseError(code="23503", constraint="project_technologies_project_id_fkey")
            if any(len(row["technology_name"]) > MAX_TECHNOLOGY_NAME_CHARS for row in rows):
                raise DatabaseError(code="22001", constraint="project_technologies_technology_name")
            self.technologies = [tech for tech in self.technologies if tech["project_id"] != project_id]
            self.technologies.extend({"id": str(uuid.uuid4()), **row} for row in rows)


_supabase_backend = _SupabaseBackend()
_local_backend = _LocalBackend()


def _backend() -> _SupabaseBackend | _LocalBackend:
    return _local_backend if get_persistence_mode() == "local" else _supabase_backend


# ---------------------------------------------------------------------------
# Conversión al diccionario plano de PROJECTS_DB
# ---------------------------------------------------------------------------
def _sorted_technologies(row: dict) -> list[dict]:
    return sorted(
        row.get("project_technologies") or [],
        key=lambda tech: (_parse_timestamp(tech.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc),
                          tech["technology_name"].casefold()),
    )


def _teacher_email(row: dict) -> str | None:
    return ((row.get("course") or {}).get("teacher") or {}).get("email")


def _to_record(row: dict) -> dict:
    """Misma forma que PROJECTS_DB en routers/projects.py.

    extracted_evidence_text y evidence_char_count no se guardan (minimización de datos,
    Ley N.° 29733): se devuelven vacíos; el texto solo vive en la respuesta de la carga.
    """
    course = row.get("course") or {}
    return {
        "id": str(row["id"]),
        "title": row["title"],
        "course_name": course.get("name"),
        "cycle": str(course["cycle"]) if course.get("cycle") is not None else None,
        "semester": CURRENT_SEMESTER,
        "student_email": (row.get("student") or {}).get("email"),
        "teacher_email": _teacher_email(row),
        "status": row["status"],
        "github_url": row.get("github_url"),
        "extracted_evidence_text": "",
        "evidence_char_count": 0,
        "tech_stack": [tech["technology_name"] for tech in _sorted_technologies(row)],
        "professional_summary": row.get("professional_summary") or "",
        "consent_law_29733": bool(row.get("consent_law_29733")),
        "consent_timestamp": _iso(row.get("consent_at")),
        "submitted_at": _iso(row.get("submitted_at")),
        "opened_by_teacher_at": _iso(row.get("opened_by_teacher_at")),
        "decision_at": _iso(row.get("decision_at")),
        "active_review_seconds": row.get("active_review_seconds"),
        "teacher_feedback": row.get("teacher_feedback"),
        "created_at": _iso(row.get("created_at")),
    }


def _technology_rows(project_id: str, names: list[str], *, validated: bool, now: datetime) -> list[dict]:
    # created_at creciente (1 microsegundo) conserva el orden en que el estudiante dejó las etiquetas.
    return [
        {
            "project_id": project_id,
            "technology_name": name,
            "validated_by_teacher": validated,
            "created_at": now + timedelta(microseconds=position),
        }
        for position, name in enumerate(names)
    ]


# ---------------------------------------------------------------------------
# Apoyo interno de las operaciones
# ---------------------------------------------------------------------------
def _load_project(backend, project_id: str) -> dict:
    rows = backend.fetch_projects(project_id=project_id)
    if not rows:
        raise ProjectNotFoundError()
    return rows[0]


def _require_status(row: dict, allowed: tuple[str, ...], template: str) -> None:
    if row["status"] not in allowed:
        raise InvalidTransitionError(template.format(status=row["status"]), current_status=row["status"])


def _raise_conflict(backend, project_id: str, allowed: tuple[str, ...], template: str) -> None:
    """El UPDATE condicional no afectó filas: otro proceso cambió el proyecto antes."""
    latest = _load_project(backend, project_id)
    _require_status(latest, allowed, template)
    raise InvalidTransitionError(template.format(status=latest["status"]), current_status=latest["status"])


def _require_user(backend, email: str, role: str) -> dict:
    user = backend.find_user_by_email(email)
    if user is None or user["role"] != role:
        if role == "Docente":
            raise ReferenceNotFoundError(
                "El correo del docente no corresponde a una cuenta docente registrada en SkillFISI."
            )
        raise ReferenceNotFoundError(
            "El correo del estudiante no corresponde a una cuenta de estudiante registrada en SkillFISI."
        )
    return user


def _get_or_create_course(backend, teacher_id: str, name: str, cycle: int) -> dict:
    """Busca el curso del docente por nombre (sin distinguir mayúsculas) o lo crea.

    Si el curso ya existe se usa su ciclo registrado. Si otro registro lo crea al mismo
    tiempo, el índice courses_teacher_name_key rechaza el duplicado y se vuelve a buscar.
    """
    key = name.lower()
    for _ in range(3):
        for course in backend.list_courses_for_teacher(teacher_id):
            if course["name"].lower() == key:
                return course
        try:
            return backend.insert_course(
                {"code": f"AUTO-{uuid.uuid4().hex[:8].upper()}", "name": name, "cycle": cycle, "teacher_id": teacher_id}
            )
        except DatabaseError as exc:
            if exc.code != "23505":
                raise
    raise DatabaseError()


# ---------------------------------------------------------------------------
# Operaciones públicas
# ---------------------------------------------------------------------------
def insert_project(*, title: str, course_name: str, cycle: str | int, student_email: str, teacher_email: str) -> dict:
    """HU03: registra el proyecto en 'Borrador'.

    El estudiante debe tener rol Estudiante y el docente rol Docente. El curso se busca entre
    los del docente por nombre (sin distinguir mayúsculas) y, si no existe, se crea.
    Errores: ProjectValidationError (400), ReferenceNotFoundError (422), DatabaseError (503).
    """
    clean_title = _clean_text(title, "El título", 5, 255)
    clean_course = _clean_text(course_name, "El nombre del curso", 3, 255)
    cycle_number = _parse_cycle(cycle)
    student_address = _normalize_email(student_email, "del estudiante")
    teacher_address = _normalize_email(teacher_email, "del docente")

    backend = _backend()
    with backend.atomic():
        student = _require_user(backend, student_address, "Estudiante")
        teacher = _require_user(backend, teacher_address, "Docente")
        course = _get_or_create_course(backend, teacher["id"], clean_course, cycle_number)
        row = backend.insert_project(
            {"title": clean_title, "course_id": course["id"], "student_id": student["id"], "status": STATUS_DRAFT}
        )

    return _to_record(
        {
            **row,
            "student": {"email": student["email"]},
            "course": {
                "name": course["name"],
                "cycle": course["cycle"],
                "teacher_id": teacher["id"],
                "teacher": {"email": teacher["email"]},
            },
            "project_technologies": [],
        }
    )


def save_project_evidence(project_id: str, *, github_url: str | None = None, evidence_text: str | None = None) -> dict:
    """HU04: guarda el enlace normalizado del repositorio y el hash SHA-256 de la evidencia.

    El texto de la evidencia no se guarda, solo su hash (minimización de datos, Ley N.° 29733).
    Solo se permite en 'Borrador' u 'Observado'.
    Errores: ProjectValidationError (400), ProjectNotFoundError (404),
    InvalidTransitionError (409), DatabaseError (503).
    """
    pid = _parse_project_id(project_id)
    changes: dict = {}
    if github_url is not None:
        changes["github_url"] = normalize_github_url(github_url)
    if evidence_text is not None:
        if not isinstance(evidence_text, str) or not evidence_text.strip():
            raise ProjectValidationError("El texto de la evidencia está vacío.")
        changes["evidence_hash"] = compute_evidence_hash(evidence_text)
    if not changes:
        raise ProjectValidationError("Debes indicar el enlace de GitHub o el texto de la evidencia.")

    backend = _backend()
    with backend.atomic():
        current = _load_project(backend, pid)
        _require_status(current, EDITABLE_STATUSES, EVIDENCE_STATE_DETAIL)
        updated = backend.update_project(pid, changes, statuses=EDITABLE_STATUSES)
        if updated is None:
            _raise_conflict(backend, pid, EDITABLE_STATUSES, EVIDENCE_STATE_DETAIL)
    return _to_record({**current, **updated})


def update_project_review_submission(
    project_id: str,
    *,
    tech_stack: Iterable[str],
    professional_summary: str,
    consent_law_29733: bool,
    student_email: str | None = None,
) -> dict:
    """HU06: guarda la edición del estudiante y pasa el proyecto a 'En Revisión'.

    Solo desde 'Borrador' u 'Observado'. Registra consent_at y submitted_at, reemplaza las
    tecnologías y limpia la apertura, la decisión y el tiempo de la revisión anterior
    (el último comentario del docente se conserva). Si se indica student_email, debe ser el dueño.
    Errores: ProjectValidationError (400), NotAuthorizedError (403), ProjectNotFoundError (404),
    InvalidTransitionError (409), DatabaseError (503).
    """
    pid = _parse_project_id(project_id)
    if consent_law_29733 is not True:
        raise ProjectValidationError(CONSENT_REQUIRED_DETAIL)
    technologies = _clean_technologies(tech_stack)
    if not technologies:
        raise ProjectValidationError("El proyecto debe incluir al menos una tecnología validada por el estudiante.")
    summary = _clean_text(professional_summary, "El resumen profesional", 20, 2500)
    owner = _normalize_email(student_email, "del estudiante") if student_email is not None else None

    backend = _backend()
    with backend.atomic():
        current = _load_project(backend, pid)
        if owner is not None and (current.get("student") or {}).get("email") != owner:
            raise NotAuthorizedError("Solo el estudiante dueño puede enviar este proyecto a revisión.")
        _require_status(current, EDITABLE_STATUSES, SUBMIT_STATE_DETAIL)

        # Primero las tecnologías y al final el cambio de estado: si algo falla a mitad,
        # el proyecto sigue en su estado anterior y el estudiante puede reintentar.
        now = _utcnow()
        tech_rows = _technology_rows(pid, technologies, validated=False, now=now)
        backend.replace_technologies(pid, tech_rows)
        updated = backend.update_project(
            pid,
            {
                "status": STATUS_IN_REVIEW,
                "consent_law_29733": True,
                "consent_at": now,
                "submitted_at": now,
                "professional_summary": summary,
                "opened_by_teacher_at": None,
                "decision_at": None,
                "active_review_seconds": None,
            },
            statuses=EDITABLE_STATUSES,
        )
        if updated is None:
            _raise_conflict(backend, pid, EDITABLE_STATUSES, SUBMIT_STATE_DETAIL)
    return _to_record({**current, **updated, "project_technologies": tech_rows})


def mark_project_opened(project_id: str, *, teacher_email: str | None = None) -> dict:
    """HU07: registra opened_by_teacher_at la primera vez que el docente abre el proyecto.

    Si ya estaba abierto no reinicia el cronómetro: devuelve el proyecto sin cambios.
    Si se indica teacher_email, debe ser el docente del curso.
    Errores: ProjectValidationError (400), NotAuthorizedError (403), ProjectNotFoundError (404),
    InvalidTransitionError (409), DatabaseError (503).
    """
    pid = _parse_project_id(project_id)
    teacher = _normalize_email(teacher_email, "del docente") if teacher_email is not None else None

    backend = _backend()
    with backend.atomic():
        current = _load_project(backend, pid)
        if teacher is not None and _teacher_email(current) != teacher:
            raise NotAuthorizedError("Solo el docente del curso puede abrir este proyecto.")
        _require_status(current, (STATUS_IN_REVIEW,), OPEN_STATE_DETAIL)
        if current["opened_by_teacher_at"] is not None:
            return _to_record(current)

        updated = backend.update_project(
            pid, {"opened_by_teacher_at": _utcnow()}, statuses=(STATUS_IN_REVIEW,), opened_is_null=True
        )
        if updated is None:
            latest = _load_project(backend, pid)
            _require_status(latest, (STATUS_IN_REVIEW,), OPEN_STATE_DETAIL)
            return _to_record(latest)  # otra petición lo abrió primero
    return _to_record({**current, **updated})


def register_teacher_decision(
    project_id: str,
    *,
    teacher_email: str,
    decision: TeacherDecision,
    teacher_feedback: str | None = None,
    validated_technologies: Iterable[str] | None = None,
) -> dict:
    """HU07: registra el veredicto del docente del curso ('Validado' u 'Observado').

    Exige que el proyecto esté 'En Revisión' y abierto antes. active_review_seconds se calcula
    con quality_metrics.teacher_active_time_seconds y se redondea hacia arriba, para que
    300,4 segundos no cuenten como dentro de la meta de 300. 'Observado' exige un comentario
    de al menos 5 caracteres; 'Validado' sin comentario guarda "Acreditación conforme.".
    Si llegan validated_technologies, reemplazan el stack; las tecnologías quedan marcadas como
    validadas solo si la decisión es 'Validado'. El UPDATE es condicional al estado
    'En Revisión', así que una segunda decisión sobre el mismo proyecto falla con 409.
    Errores: ProjectValidationError (400), NotAuthorizedError (403), ProjectNotFoundError (404),
    InvalidTransitionError (409), DatabaseError (503).
    """
    pid = _parse_project_id(project_id)
    if decision not in TEACHER_DECISIONS:
        raise ProjectValidationError("La decisión debe ser 'Validado' u 'Observado'.")
    teacher = _normalize_email(teacher_email, "del docente")
    feedback = teacher_feedback.strip() if isinstance(teacher_feedback, str) else ""
    if decision == STATUS_OBSERVED and len(feedback) < MIN_OBSERVATION_FEEDBACK_CHARS:
        raise ProjectValidationError(OBSERVATION_FEEDBACK_DETAIL)
    if len(feedback) > MAX_FEEDBACK_CHARS:
        raise ProjectValidationError(f"La retroalimentación no puede superar {MAX_FEEDBACK_CHARS} caracteres.")
    feedback = feedback or DEFAULT_VALIDATION_FEEDBACK
    new_stack = _clean_technologies(validated_technologies) if validated_technologies is not None else []

    backend = _backend()
    with backend.atomic():
        current = _load_project(backend, pid)
        if _teacher_email(current) != teacher:
            raise NotAuthorizedError("Solo el docente del curso puede evaluar este proyecto.")
        _require_status(current, (STATUS_IN_REVIEW,), DECISION_STATE_DETAIL)
        opened_at = _parse_timestamp(current["opened_by_teacher_at"])
        if opened_at is None:
            raise InvalidTransitionError(NOT_OPENED_DETAIL, current_status=current["status"])

        decided_at = _utcnow()
        try:
            review_seconds = math.ceil(teacher_active_time_seconds(opened_at, decided_at))
        except ValueError:
            # Solo ocurre si el reloj del servidor retrocede respecto de la apertura registrada.
            raise InvalidTransitionError(
                "La apertura registrada es posterior a la hora actual del servidor; intenta en unos segundos.",
                current_status=current["status"],
            ) from None
        names = new_stack or [tech["technology_name"] for tech in _sorted_technologies(current)]
        tech_rows = _technology_rows(pid, names, validated=decision == STATUS_VALIDATED, now=decided_at)
        backend.replace_technologies(pid, tech_rows)
        updated = backend.update_project(
            pid,
            {
                "status": decision,
                "decision_at": decided_at,
                "active_review_seconds": review_seconds,
                "teacher_feedback": feedback,
            },
            statuses=(STATUS_IN_REVIEW,),
            opened_is_null=False,
        )
        if updated is None:
            _raise_conflict(backend, pid, (STATUS_IN_REVIEW,), DECISION_STATE_DETAIL)
    return _to_record({**current, **updated, "project_technologies": tech_rows})


def get_project(project_id: str) -> dict:
    """Detalle de un proyecto. Errores: ProjectNotFoundError (404), DatabaseError (503)."""
    return _to_record(_load_project(_backend(), _parse_project_id(project_id)))


def list_projects_by_student(student_email: str) -> list[dict]:
    """Proyectos de un estudiante, del más antiguo al más reciente ([] si el correo no tiene cuenta).

    Errores: ProjectValidationError (400), DatabaseError (503).
    """
    email = _normalize_email(student_email, "consultado")
    backend = _backend()
    student = backend.find_user_by_email(email)
    if student is None:
        return []
    return [_to_record(row) for row in backend.fetch_projects(student_id=student["id"])]


def list_pending_reviews(teacher_email: str | None = None) -> list[dict]:
    """Proyectos 'En Revisión' ordenados por fecha de envío; si se indica teacher_email,
    solo los de los cursos de ese docente ([] si el correo no tiene cuenta).

    Errores: ProjectValidationError (400), DatabaseError (503).
    """
    backend = _backend()
    if teacher_email is None:
        rows = backend.fetch_projects(status=STATUS_IN_REVIEW)
    else:
        teacher = backend.find_user_by_email(_normalize_email(teacher_email, "del docente"))
        if teacher is None:
            return []
        course_ids = [course["id"] for course in backend.list_courses_for_teacher(teacher["id"])]
        rows = backend.fetch_projects(course_ids=course_ids, status=STATUS_IN_REVIEW)
    rows.sort(key=lambda row: _parse_timestamp(row["submitted_at"]))
    return [_to_record(row) for row in rows]


# ---------------------------------------------------------------------------
# Solo para el modo local (pruebas)
# ---------------------------------------------------------------------------
def _require_local_mode(function_name: str) -> None:
    if get_persistence_mode() != "local":
        raise RuntimeError(f"{function_name} solo está disponible en el modo de persistencia local.")


def register_local_user(*, email: str, full_name: str, role: str = "Estudiante") -> dict:
    """Crea un usuario en el almacenamiento local, como si existiera en auth.users y en users."""
    _require_local_mode("register_local_user")
    return _local_backend.add_user(
        {
            "id": str(uuid.uuid4()),
            "email": _normalize_email(email, "del usuario"),
            "full_name": full_name,
            "role": role,
        }
    )


def reset_local_store() -> None:
    """Vacía el almacenamiento local."""
    _require_local_mode("reset_local_store")
    _local_backend.reset()
