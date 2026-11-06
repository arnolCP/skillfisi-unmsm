"""Conexión con Supabase para el backend (Módulo 3.1).

Se usan dos tipos de cliente:
- Administrador (clave service_role): solo vive en el backend y omite RLS,
  por eso cada endpoint debe validar antes quién hace la petición.
- Autenticación (clave anon): se crea uno nuevo por cada inicio de sesión
  para que las sesiones de distintos usuarios nunca se mezclen.
"""

import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from supabase import Client, ClientOptions, create_client

# Carga backend/.env sin importar desde qué carpeta se levante el servidor.
# Las variables ya definidas en el sistema (por ejemplo, en el despliegue) tienen prioridad.
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH)


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
