# SkillFISI: Plataforma Inteligente de Portafolios Académicos (FISI - UNMSM)

Plataforma web responsiva asistida por IA (LLM vía API) que centraliza evidencias de proyectos de asignatura, extrae automáticamente el stack tecnológico y genera resúmenes ejecutivos bajo validación humana obligatoria (*Human-in-the-Loop*: edición del estudiante y acreditación docente en <= 5 minutos).

## Estructura del Repositorio y Responsables (Equipo 6)
* `backend/`: API REST en Python (FastAPI), ingesta de evidencias y motor LLM.
* `frontend/`: Interfaz web en Next.js (React) + Tailwind CSS.
* `database/`: Scripts SQL para PostgreSQL (Supabase).
* `tests/`: Pruebas unitarias y evaluación de precisión IA (Pytest).
* `.github/workflows/`: Integración continua (CI/CD).

## Asignación por Paquete de la EDT
1. **Erick Ticsihua (DP / IA):** Paquete `3.3` - Motor LLM, prompts JSON y caché (`backend/services/llm_service.py`).
2. **Arnol Condori (PO / BI):** Paquete `3.2` - Registro de proyectos y extractor de evidencias GitHub/PDF/Notebook (`backend/routers/projects.py`, `backend/services/evidence_extractor.py`) y Paquete `3.6` - Dashboard BI.
3. **Bryan Rodriguez (Arquitecto / UI):** Paquete `2.3` - Esquema SQL (`database/`) y Paquete `3.4` - Bandeja de validación docente (`frontend/`).
4. **Demian Ninamango (Cloud / Seguridad):** Paquete `3.1` - Autenticación `@unmsm.edu.pe` y Paquete `3.5` - Portafolio público con Ley N.° 29733.
5. **Miguel Sanchez (Scrum Master / QA):** Paquete `3.2` (Validadores), Paquete `4.1` (Pruebas en `tests/`) y telemetría `HU14`.
