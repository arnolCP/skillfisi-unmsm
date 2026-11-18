-- =============================================================================
-- SkillFISI - Migración incremental del Sprint 2
--
-- Requisito: database/01_schema.sql ya aplicado.
-- Uso: ejecutar el archivo completo, una sola vez, en el SQL Editor de Supabase.
--   - Va dentro de una transacción: si una sentencia falla, no se aplica ningún cambio.
--   - Se puede volver a ejecutar: usa IF NOT EXISTS y elimina cada restricción antes de crearla.
--   - Las políticas RLS no van aquí: se definen en database/03_rls_policies.sql.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 1. users: vínculo con Supabase Auth y código de matrícula único
-- -----------------------------------------------------------------------------

-- El id del perfil es el mismo id de la cuenta en auth.users; ya no se genera aquí.
ALTER TABLE public.users ALTER COLUMN id DROP DEFAULT;

-- Todo perfil corresponde a una cuenta de Auth. Al borrar la cuenta se borra el perfil
-- y, en cascada, sus proyectos (derecho de cancelación, Ley N.° 29733).
ALTER TABLE public.users DROP CONSTRAINT IF EXISTS users_id_fkey;
ALTER TABLE public.users
    ADD CONSTRAINT users_id_fkey
    FOREIGN KEY (id) REFERENCES auth.users (id) ON DELETE CASCADE;

-- Un código de matrícula pertenece a un solo estudiante.
-- Los perfiles sin código (NULL), como los de docentes, no chocan entre sí.
ALTER TABLE public.users DROP CONSTRAINT IF EXISTS users_student_code_key;
ALTER TABLE public.users
    ADD CONSTRAINT users_student_code_key UNIQUE (student_code);

-- -----------------------------------------------------------------------------
-- 2. projects: columnas nuevas
--    El stack tecnológico no necesita columna: se guarda en project_technologies.
-- -----------------------------------------------------------------------------

-- 2.1 Pedidas por el plan del Sprint 2
ALTER TABLE public.projects
    ADD COLUMN IF NOT EXISTS teacher_feedback      TEXT,
    ADD COLUMN IF NOT EXISTS active_review_seconds INT,
    ADD COLUMN IF NOT EXISTS evidence_hash         VARCHAR(64);

-- 2.2 Necesarias para guardar lo que hoy maneja el flujo en memoria
ALTER TABLE public.projects
    ADD COLUMN IF NOT EXISTS professional_summary TEXT,
    ADD COLUMN IF NOT EXISTS github_url           TEXT,
    ADD COLUMN IF NOT EXISTS consent_at           TIMESTAMP WITH TIME ZONE;

COMMENT ON COLUMN public.projects.teacher_feedback IS
    'HU07: comentario del docente al validar u observar el proyecto.';
COMMENT ON COLUMN public.projects.active_review_seconds IS
    'HU07: segundos entre opened_by_teacher_at y decision_at (meta: 300 o menos).';
COMMENT ON COLUMN public.projects.evidence_hash IS
    'HU05: SHA-256 en hexadecimal (64 caracteres) del texto de evidencia analizado por el motor LLM.';
COMMENT ON COLUMN public.projects.professional_summary IS
    'HU06: resumen profesional generado por el motor LLM y editado por el estudiante.';
COMMENT ON COLUMN public.projects.github_url IS
    'HU04: repositorio público de GitHub del proyecto; el docente lo abre al revisar.';
COMMENT ON COLUMN public.projects.consent_at IS
    'HU06: fecha y hora en que el estudiante aceptó la Ley N.° 29733.';

-- -----------------------------------------------------------------------------
-- 3. projects: restricciones contra estados inválidos
-- -----------------------------------------------------------------------------

-- 3.1 Solo los cuatro estados del flujo. Ya existía en 01_schema.sql; se vuelve a
--     declarar para que esta migración deje la regla garantizada por sí misma.
ALTER TABLE public.projects DROP CONSTRAINT IF EXISTS projects_status_check;
ALTER TABLE public.projects
    ADD CONSTRAINT projects_status_check
    CHECK (status IN ('Borrador', 'En Revisión', 'Validado', 'Observado'));

-- 3.2 El consentimiento de la Ley N.° 29733 y su fecha van siempre juntos.
ALTER TABLE public.projects DROP CONSTRAINT IF EXISTS projects_consent_check;
ALTER TABLE public.projects
    ADD CONSTRAINT projects_consent_check
    CHECK (consent_law_29733 = (consent_at IS NOT NULL));

-- 3.3 Fuera de 'Borrador' el proyecto ya fue enviado: con consentimiento,
--     fecha de envío y resumen profesional.
ALTER TABLE public.projects DROP CONSTRAINT IF EXISTS projects_submission_check;
ALTER TABLE public.projects
    ADD CONSTRAINT projects_submission_check
    CHECK (
        status = 'Borrador'
        OR (consent_law_29733 AND submitted_at IS NOT NULL AND professional_summary IS NOT NULL)
    );

-- 3.4 El docente solo abre proyectos ya enviados, y nunca antes del envío.
ALTER TABLE public.projects DROP CONSTRAINT IF EXISTS projects_opened_check;
ALTER TABLE public.projects
    ADD CONSTRAINT projects_opened_check
    CHECK (
        opened_by_teacher_at IS NULL
        OR (submitted_at IS NOT NULL AND opened_by_teacher_at >= submitted_at)
    );

-- 3.5 No hay decisión sin apertura previa, ni decisión anterior a la apertura.
ALTER TABLE public.projects DROP CONSTRAINT IF EXISTS projects_decision_check;
ALTER TABLE public.projects
    ADD CONSTRAINT projects_decision_check
    CHECK (
        decision_at IS NULL
        OR (opened_by_teacher_at IS NOT NULL AND decision_at >= opened_by_teacher_at)
    );

-- 3.6 'Validado' y 'Observado' tienen fecha de decisión; 'Borrador' y 'En Revisión' no.
--     Al reenviar un proyecto observado, la decisión anterior debe limpiarse.
ALTER TABLE public.projects DROP CONSTRAINT IF EXISTS projects_decision_status_check;
ALTER TABLE public.projects
    ADD CONSTRAINT projects_decision_status_check
    CHECK ((status IN ('Validado', 'Observado')) = (decision_at IS NOT NULL));

-- 3.7 El tiempo de revisión existe solo si hubo decisión, y nunca es negativo.
ALTER TABLE public.projects DROP CONSTRAINT IF EXISTS projects_review_seconds_check;
ALTER TABLE public.projects
    ADD CONSTRAINT projects_review_seconds_check
    CHECK (
        ((active_review_seconds IS NULL) = (decision_at IS NULL))
        AND COALESCE(active_review_seconds, 0) >= 0
    );

-- 3.8 Un proyecto 'Observado' explica al estudiante qué corregir (al menos 5 caracteres).
ALTER TABLE public.projects DROP CONSTRAINT IF EXISTS projects_observed_feedback_check;
ALTER TABLE public.projects
    ADD CONSTRAINT projects_observed_feedback_check
    CHECK (status <> 'Observado' OR char_length(btrim(COALESCE(teacher_feedback, ''))) >= 5);

-- 3.9 El hash de evidencia es un SHA-256 en hexadecimal en minúsculas.
ALTER TABLE public.projects DROP CONSTRAINT IF EXISTS projects_evidence_hash_check;
ALTER TABLE public.projects
    ADD CONSTRAINT projects_evidence_hash_check
    CHECK (evidence_hash IS NULL OR evidence_hash ~ '^[0-9a-f]{64}$');

-- 3.10 El enlace del repositorio es de GitHub y por https (evita, por ejemplo,
--      enlaces javascript: en la bandeja del docente).
ALTER TABLE public.projects DROP CONSTRAINT IF EXISTS projects_github_url_check;
ALTER TABLE public.projects
    ADD CONSTRAINT projects_github_url_check
    CHECK (github_url IS NULL OR github_url ~ '^https://(www\.)?github\.com/[^/?#]+/[^/?#]+');

-- -----------------------------------------------------------------------------
-- 4. courses: un docente no repite el nombre de un curso
-- -----------------------------------------------------------------------------
-- El registro de proyectos recibe el nombre del curso y el correo del docente, y busca
-- ese curso o lo crea. Este índice evita cursos duplicados si dos estudiantes registran
-- a la vez el primer proyecto del mismo curso (sin distinguir mayúsculas).
CREATE UNIQUE INDEX IF NOT EXISTS courses_teacher_name_key
    ON public.courses (teacher_id, lower(name));

COMMIT;

-- -----------------------------------------------------------------------------
-- Verificación (solo lectura): debe listar 2 restricciones de users,
-- 10 de projects y el índice de courses.
-- -----------------------------------------------------------------------------
SELECT conrelid::regclass::text AS tabla, conname::text AS nombre, pg_get_constraintdef(oid) AS definicion
FROM pg_constraint
WHERE connamespace = 'public'::regnamespace
  AND conname IN (
        'users_id_fkey', 'users_student_code_key',
        'projects_status_check', 'projects_consent_check', 'projects_submission_check',
        'projects_opened_check', 'projects_decision_check', 'projects_decision_status_check',
        'projects_review_seconds_check', 'projects_observed_feedback_check',
        'projects_evidence_hash_check', 'projects_github_url_check'
      )
UNION ALL
SELECT tablename::text, indexname::text, indexdef
FROM pg_indexes
WHERE schemaname = 'public' AND indexname = 'courses_teacher_name_key'
ORDER BY 1, 2;
