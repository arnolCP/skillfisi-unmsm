"""Módulo 3.1: autenticación institucional (HU01) y perfil académico (HU02)."""

import logging
from typing import Annotated
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from supabase import (
    AuthApiError,
    AuthError,
    AuthRetryableError,
    AuthWeakPasswordError,
    PostgrestAPIError,
)

from services.supabase_client import create_auth_client, get_admin_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Módulo 3.1 - Autenticación y Perfiles"])

USERS_TABLE = "users"
DEFAULT_ROLE = "Estudiante"
PROFILE_FIELDS = "full_name,email,student_code,school,current_cycle,linkedin_url,github_url"

INVALID_DOMAIN_DETAIL = "Acceso restringido: debes usar tu correo institucional (@unmsm.edu.pe)."
AUTH_UNAVAILABLE_DETAIL = "El servicio de autenticación no está disponible. Intenta nuevamente."
DB_UNAVAILABLE_DETAIL = "No se pudo acceder a la base de datos. Intenta nuevamente."


# ---------------------------------------------------------------------------
# Validación de correo institucional
# TODO: reemplazar _INSTITUTIONAL_EMAIL_DOMAIN, _normalize_email e _is_institutional_email
# por is_institutional_email de services/validators.py cuando esté en main.
# ---------------------------------------------------------------------------
_INSTITUTIONAL_EMAIL_DOMAIN = "unmsm.edu.pe"


def _normalize_email(email: str) -> str:
    return email.strip().casefold()


def _is_institutional_email(email: str) -> bool:
    """Un solo @ y dominio exactamente unmsm.edu.pe (sin subdominios)."""
    if not isinstance(email, str):
        return False

    local_part, separator, domain = _normalize_email(email).rpartition("@")

    return bool(
        separator
        and local_part
        and "@" not in local_part
        and domain == _INSTITUTIONAL_EMAIL_DOMAIN
    )


# ---------------------------------------------------------------------------
# Modelos de entrada y salida
# ---------------------------------------------------------------------------
class RegisterRequest(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(min_length=8, max_length=72)
    full_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=255)]


class LoginRequest(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(min_length=1, max_length=72)


class ProfileResponse(BaseModel):
    full_name: str
    email: str
    student_code: str | None = None
    school: str | None = None
    current_cycle: int | None = None
    linkedin_url: str | None = None
    github_url: str | None = None


def _validate_site_url(value: str | None, domain: str, label: str) -> str | None:
    """Acepta solo enlaces http(s) del dominio indicado (evita, por ejemplo, enlaces javascript:)."""
    if value is None:
        return None

    parsed = urlparse(value)
    host = (parsed.hostname or "").casefold()
    if parsed.scheme not in {"http", "https"} or not (host == domain or host.endswith(f".{domain}")):
        raise ValueError(f"{label} debe ser un enlace de {domain} (por ejemplo, https://{domain}/...).")
    return value


class ProfileUpdate(BaseModel):
    """Campos editables del perfil. Lo demás que envíe el frontend (full_name, email) se ignora."""

    model_config = ConfigDict(extra="ignore")

    student_code: str | None = Field(default=None, max_length=20)
    school: str | None = Field(default=None, max_length=100)
    current_cycle: int | None = Field(default=None, ge=1, le=10)
    linkedin_url: str | None = Field(default=None, max_length=255)
    github_url: str | None = Field(default=None, max_length=255)

    @field_validator("student_code", "school", "linkedin_url", "github_url", mode="before")
    @classmethod
    def _blank_to_none(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("student_code")
    @classmethod
    def _check_student_code(cls, value: str | None) -> str | None:
        if value is not None and not (len(value) == 8 and value.isdigit()):
            raise ValueError("El código de matrícula debe tener 8 dígitos.")
        return value

    @field_validator("linkedin_url")
    @classmethod
    def _check_linkedin_url(cls, value: str | None) -> str | None:
        return _validate_site_url(value, "linkedin.com", "El perfil de LinkedIn")

    @field_validator("github_url")
    @classmethod
    def _check_github_url(cls, value: str | None) -> str | None:
        return _validate_site_url(value, "github.com", "El perfil de GitHub")


class CurrentUser(BaseModel):
    id: str
    email: str


# ---------------------------------------------------------------------------
# Dependencia reutilizable: usuario autenticado
# ---------------------------------------------------------------------------
_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> CurrentUser:
    """Valida el token Bearer con Supabase Auth y devuelve al usuario autenticado.

    Uso en otros routers: `user: Annotated[CurrentUser, Depends(get_current_user)]`.
    """
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido o expirado. Inicia sesión nuevamente.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta el token de acceso.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        response = get_admin_client().auth.get_user(credentials.credentials)
    except AuthRetryableError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=AUTH_UNAVAILABLE_DETAIL)
    except AuthApiError as exc:
        if exc.status in {400, 401, 403}:
            raise unauthorized
        logger.error("Supabase Auth respondió %s al validar el token", exc.status)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=AUTH_UNAVAILABLE_DETAIL)
    except AuthError:
        raise unauthorized
    except Exception as exc:
        logger.error("Error al validar el token: %s", type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=AUTH_UNAVAILABLE_DETAIL)

    user = response.user if response else None
    if user is None or not user.email:
        raise unauthorized
    if not _is_institutional_email(user.email):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=INVALID_DOMAIN_DETAIL)

    return CurrentUser(id=str(user.id).casefold(), email=_normalize_email(user.email))


def _ensure_profile_owner(user_id: UUID, current_user: CurrentUser) -> str:
    target_id = str(user_id)
    if target_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para acceder a este perfil.",
        )
    return target_id


def _delete_auth_user(user_id: str) -> None:
    """Revierte una cuenta creada en Auth cuando no se pudo crear su perfil."""
    try:
        get_admin_client().auth.admin.delete_user(user_id)
    except Exception as exc:
        logger.error("No se pudo revertir la cuenta %s en Auth: %s", user_id, type(exc).__name__)


def _fetch_profile(user_id: str) -> dict:
    try:
        result = (
            get_admin_client()
            .table(USERS_TABLE)
            .select(PROFILE_FIELDS)
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        logger.error("Error al consultar el perfil: %s", type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=DB_UNAVAILABLE_DETAIL)

    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Perfil no encontrado.")
    return result.data[0]


# ---------------------------------------------------------------------------
# HU01: registro e inicio de sesión institucional
# ---------------------------------------------------------------------------
@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest):
    """HU01: crea una cuenta de estudiante solo con correo @unmsm.edu.pe."""
    if not _is_institutional_email(payload.email):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=INVALID_DOMAIN_DETAIL)

    email = _normalize_email(payload.email)
    admin = get_admin_client()

    try:
        created = admin.auth.admin.create_user(
            {
                "email": email,
                "password": payload.password,
                "email_confirm": True,
                "user_metadata": {"full_name": payload.full_name},
            }
        )
    except AuthWeakPasswordError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña es muy débil. Usa al menos 8 caracteres combinando letras y números.",
        )
    except AuthRetryableError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=AUTH_UNAVAILABLE_DETAIL)
    except AuthApiError as exc:
        if exc.code in {"email_exists", "user_already_exists"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El correo ya está registrado.")
        if exc.status in {400, 422}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se pudo crear la cuenta. Revisa el correo y la contraseña.",
            )
        logger.error("Supabase Auth respondió %s al crear la cuenta", exc.status)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=AUTH_UNAVAILABLE_DETAIL)
    except Exception as exc:
        logger.error("Error al crear la cuenta en Auth: %s", type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=AUTH_UNAVAILABLE_DETAIL)

    user_id = str(created.user.id)
    try:
        admin.table(USERS_TABLE).insert(
            {
                "id": user_id,
                "email": email,
                "full_name": payload.full_name,
                "role": DEFAULT_ROLE,
            }
        ).execute()
    except Exception as exc:
        _delete_auth_user(user_id)
        if isinstance(exc, PostgrestAPIError) and exc.code == "23505":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El correo ya está registrado.")
        logger.error("Error al crear el perfil en la tabla users: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo crear el perfil académico. La cuenta no se registró; intenta nuevamente.",
        )

    return {
        "message": "Cuenta creada correctamente.",
        "user": {"id": user_id, "email": email, "full_name": payload.full_name, "role": DEFAULT_ROLE},
    }


@router.post("/auth/login")
def login(payload: LoginRequest):
    """HU01: inicia sesión solo con correo @unmsm.edu.pe y devuelve el token de acceso."""
    if not _is_institutional_email(payload.email):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=INVALID_DOMAIN_DETAIL)

    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Correo o contraseña incorrectos.",
    )
    try:
        result = create_auth_client().auth.sign_in_with_password(
            {"email": _normalize_email(payload.email), "password": payload.password}
        )
    except AuthRetryableError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=AUTH_UNAVAILABLE_DETAIL)
    except AuthApiError as exc:
        if exc.status == status.HTTP_429_TOO_MANY_REQUESTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Demasiados intentos. Espera un momento e inténtalo de nuevo.",
            )
        if exc.status in {400, 422}:
            raise invalid_credentials
        logger.error("Supabase Auth respondió %s al iniciar sesión", exc.status)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=AUTH_UNAVAILABLE_DETAIL)
    except AuthError:
        raise invalid_credentials
    except Exception as exc:
        logger.error("Error al iniciar sesión: %s", type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=AUTH_UNAVAILABLE_DETAIL)

    if result.session is None or result.user is None:
        raise invalid_credentials

    return {
        "access_token": result.session.access_token,
        "token_type": "bearer",
        "expires_in": result.session.expires_in,
        "user": {"id": str(result.user.id), "email": result.user.email},
    }


# ---------------------------------------------------------------------------
# HU02: perfil académico
# ---------------------------------------------------------------------------
@router.get("/profile/{user_id}", response_model=ProfileResponse)
def get_profile(user_id: UUID, current_user: Annotated[CurrentUser, Depends(get_current_user)]):
    """HU02: devuelve el perfil académico del usuario autenticado."""
    target_id = _ensure_profile_owner(user_id, current_user)
    return _fetch_profile(target_id)


@router.put("/profile/{user_id}", response_model=ProfileResponse)
def update_profile(
    user_id: UUID,
    payload: ProfileUpdate,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    """HU02: actualiza código de matrícula, escuela, ciclo, LinkedIn y GitHub."""
    target_id = _ensure_profile_owner(user_id, current_user)

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return _fetch_profile(target_id)

    try:
        result = get_admin_client().table(USERS_TABLE).update(changes).eq("id", target_id).execute()
    except Exception as exc:
        logger.error("Error al actualizar el perfil: %s", type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=DB_UNAVAILABLE_DETAIL)

    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Perfil no encontrado.")
    return result.data[0]
