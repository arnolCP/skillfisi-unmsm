import json
import re
from io import BytesIO
from urllib.parse import urlsplit

import requests
from pypdf import PdfReader
from fastapi import HTTPException

# Límite máximo de caracteres para proteger la cuota de tokens del LLM (Mitigación R03 - HU04)
MAX_CHARS_FOR_LLM = 12000
GITHUB_OWNER_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
GITHUB_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,100}$")


def truncate_for_llm(text: str) -> str:
    """Apply the single character quota used by every LLM-bound evidence source."""
    if not isinstance(text, str):
        raise TypeError("El contenido de la evidencia debe ser texto.")

    return text[:MAX_CHARS_FOR_LLM]


def parse_github_url(url: str) -> tuple[str, str]:
    """Valida que la URL sea de GitHub y extrae el usuario (owner) y nombre del repositorio."""
    if not isinstance(url, str):
        raise HTTPException(
            status_code=400,
            detail="La URL ingresada no es un enlace válido de GitHub."
        )

    try:
        parsed_url = urlsplit(url.strip())
        parsed_port = parsed_url.port
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="La URL ingresada no es un enlace HTTPS válido de GitHub."
        ) from exc

    if (
        parsed_url.scheme != "https"
        or parsed_url.hostname not in {"github.com", "www.github.com"}
        or parsed_port is not None
        or parsed_url.username is not None
        or parsed_url.password is not None
        or parsed_url.query
        or parsed_url.fragment
    ):
        raise HTTPException(
            status_code=400,
            detail="La URL ingresada no es un enlace HTTPS válido de GitHub."
        )

    path_parts = [part for part in parsed_url.path.split("/") if part]
    if len(path_parts) != 2:
        raise HTTPException(
            status_code=400,
            detail="La URL debe apuntar a la raíz de un repositorio de GitHub."
        )

    owner, repository = path_parts
    if repository.endswith(".git"):
        repository = repository[:-4]

    if (
        not GITHUB_OWNER_PATTERN.fullmatch(owner)
        or not GITHUB_REPOSITORY_PATTERN.fullmatch(repository)
    ):
        raise HTTPException(
            status_code=400,
            detail="El propietario o el nombre del repositorio de GitHub no es válido."
        )

    return owner, repository


def extract_from_github(github_url: str) -> str:
    """
    HU04: Verifica que el repositorio de GitHub sea público y extrae el README.md
    junto con los archivos de dependencias técnicas (requirements.txt, package.json, pom.xml).
    """
    owner, repo = parse_github_url(github_url)
    
    # 1. Verificar que el repositorio exista y sea público
    repo_api_url = f"https://api.github.com/repos/{owner}/{repo}"
    resp = requests.get(repo_api_url, timeout=10, allow_redirects=False)
    if resp.status_code == 404:
        raise HTTPException(
            status_code=400,
            detail="El repositorio no existe o es PRIVADO. Habilita el acceso público en GitHub."
        )
    elif resp.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail=f"No se pudo verificar el repositorio en GitHub (HTTP {resp.status_code})."
        )

    repository_metadata = resp.json()
    if repository_metadata.get("private", False):
        raise HTTPException(
            status_code=400,
            detail="El repositorio debe ser público para poder procesar sus evidencias."
        )

    default_branch = repository_metadata.get("default_branch")
    if not isinstance(default_branch, str) or not default_branch.strip():
        raise HTTPException(
            status_code=400,
            detail="GitHub no informó una rama principal válida para el repositorio."
        )
    extracted_parts = [f"REPOSITORIO GITHUB: {owner}/{repo}"]

    # 2. Archivos clave donde se evidencia el stack tecnológico real
    target_files = [
        "README.md",
        "readme.md",
        "requirements.txt",
        "package.json",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "Dockerfile",
    ]

    for filename in target_files:
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{default_branch}/{filename}"
        file_resp = requests.get(raw_url, timeout=8)
        if file_resp.status_code == 200 and file_resp.text.strip():
            # Tomamos hasta 4000 caracteres por archivo para balancear contexto
            content = file_resp.text.strip()[:4000]
            extracted_parts.append(f"\n--- ARCHIVO: {filename} ---\n{content}")

    full_text = "\n".join(extracted_parts)
    return truncate_for_llm(full_text)


def extract_from_pdf(file_bytes: bytes) -> str:
    """HU04: Extrae el texto técnico de un informe en formato PDF."""
    try:
        reader = PdfReader(BytesIO(file_bytes))
        pages_text = []
        # Leemos las primeras 15 páginas (donde están resumen, arquitectura y herramientas)
        for page in reader.pages[:15]:
            text = page.extract_text()
            if text:
                pages_text.append(text)
        full_text = "\n".join(pages_text)
        return truncate_for_llm(full_text)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al leer el archivo PDF: {str(e)}")


def extract_from_ipynb(file_bytes: bytes) -> str:
    """HU04: Extrae celdas Markdown y los imports de código de un Jupyter Notebook (.ipynb)."""
    try:
        notebook = json.loads(file_bytes.decode("utf-8"))
        extracted_cells = []
        for cell in notebook.get("cells", []):
            cell_type = cell.get("cell_type")
            source = "".join(cell.get("source", []))
            if cell_type == "markdown":
                extracted_cells.append(source)
            elif cell_type == "code":
                # Extraemos líneas que contengan librerías (import / from) o definiciones clave
                code_lines = [
                    line for line in source.splitlines()
                    if line.strip().startswith(("import ", "from ", "def ", "class "))
                ]
                if code_lines:
                    extracted_cells.append("\n".join(code_lines))
        full_text = "\n---\n".join(extracted_cells)
        return truncate_for_llm(full_text)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al leer el notebook .ipynb: {str(e)}")
