-- =============================================================================
-- SkillFISI - Migración del Sprint 3: sello docente y portafolio público (HU10, HU11)
--
-- Requisitos: database/01_schema.sql, 02_sprint2_migration.sql y 03_rls_policies.sql aplicados.
-- Uso: ejecutar el archivo completo, de una vez, en el SQL Editor de Supabase.
--   - Va dentro de una transacción: si una sentencia falla, no se aplica ningún cambio.
--   - Se puede volver a ejecutar: usa IF NOT EXISTS y elimina cada objeto antes de crearlo.
--
-- Contenido:
--   1. verification_code: código único del sello "Validado por Docente" (HU10).
--   2. Revocación del consentimiento de la Ley N.° 29733 en proyectos 'Validado' (HU11, riesgo R06).
--   3. Índice idx_projects_public_portfolio para la consulta del portafolio público.
--   4. Vista public_verified_portfolios: solo datos públicos, solo para el backend.
--   5. Índices de la versión reducida de la 02 (PR #8) que la 02 restaurada no incluye.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 0. Comprobación previa: columnas que crea la migración 02
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    IF (
        SELECT count(*)
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'projects'
          AND column_name IN ('consent_at', 'professional_summary', 'teacher_feedback')
    ) <> 3 THEN
        RAISE EXCEPTION 'Falta aplicar database/02_sprint2_migration.sql: no existen las columnas consent_at, professional_summary o teacher_feedback en public.projects.';
    END IF;
END
$$;

-- -----------------------------------------------------------------------------
-- 1. projects: código de verificación del sello docente (HU10)
-- -----------------------------------------------------------------------------
ALTER TABLE public.projects
    ADD COLUMN IF NOT EXISTS verification_code VARCHAR(32);

COMMENT ON COLUMN public.projects.verification_code IS
    'HU10: código único del sello "Validado por Docente" (formato FISI-2026-XXXXXX). Solo existe en proyectos Validado.';

-- 1.1 Un código identifica a un solo proyecto. Los NULL (proyectos sin validar) no chocan entre sí.
ALTER TABLE public.projects DROP CONSTRAINT IF EXISTS projects_verification_code_key;
ALTER TABLE public.projects
    ADD CONSTRAINT projects_verification_code_key UNIQUE (verification_code);

-- 1.2 Proyectos que ya estaban 'Validado' antes de esta migración: reciben un código nuevo.
--     El backend genera los siguientes al validar (supabase_client.register_teacher_decision).
--     Se omiten 0, O, 1 e I para que el código no se confunda al dictarlo o copiarlo.
DO $$
DECLARE
    v_alphabet CONSTANT text := 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    v_project_id uuid;
    v_code text;
BEGIN
    FOR v_project_id IN
        SELECT id FROM public.projects
        WHERE status = 'Validado' AND verification_code IS NULL
    LOOP
        LOOP
            SELECT 'FISI-2026-' || string_agg(substr(v_alphabet, 1 + floor(random() * length(v_alphabet))::int, 1), '')
            INTO v_code
            FROM generate_series(1, 6);
            EXIT WHEN NOT EXISTS (SELECT 1 FROM public.projects WHERE verification_code = v_code);
        END LOOP;
        UPDATE public.projects SET verification_code = v_code WHERE id = v_project_id;
    END LOOP;
END
$$;

-- 1.3 Formato FISI-2026- seguido de 6 letras mayúsculas o dígitos.
ALTER TABLE public.projects DROP CONSTRAINT IF EXISTS projects_verification_code_check;
ALTER TABLE public.projects
    ADD CONSTRAINT projects_verification_code_check
    CHECK (verification_code IS NULL OR verification_code ~ '^FISI-2026-[A-Z0-9]{6}$');

-- 1.4 Todo proyecto 'Validado' tiene código, y ningún otro estado lo tiene.
ALTER TABLE public.projects DROP CONSTRAINT IF EXISTS projects_verification_code_status_check;
ALTER TABLE public.projects
    ADD CONSTRAINT projects_verification_code_status_check
    CHECK ((status = 'Validado') = (verification_code IS NOT NULL));

-- -----------------------------------------------------------------------------
-- 2. projects: revocación del consentimiento de la Ley N.° 29733 (HU11, riesgo R06)
--
--    Estados posibles del consentimiento:
--      - Nunca otorgado ('Borrador'): consent_law_29733 = false y consent_at nulo.
--      - Activo: consent_law_29733 = true; consent_at es la fecha del último otorgamiento.
--      - Revocado (solo 'Validado'): consent_law_29733 = false; consent_at conserva la fecha
--        del último otorgamiento y consent_revoked_at guarda la fecha de la revocación.
--    Al volver a activarlo, consent_at toma la fecha nueva y consent_revoked_at se conserva
--    como la última revocación (queda anterior a consent_at).
--    En 'Borrador', 'En Revisión' y 'Observado' rigen las mismas reglas de la migración 02.
-- -----------------------------------------------------------------------------
ALTER TABLE public.projects
    ADD COLUMN IF NOT EXISTS consent_revoked_at TIMESTAMP WITH TIME ZONE;

COMMENT ON COLUMN public.projects.consent_at IS
    'HU06/HU11: fecha y hora del último consentimiento de la Ley N.° 29733 otorgado por el estudiante.';
COMMENT ON COLUMN public.projects.consent_revoked_at IS
    'HU11: fecha y hora de la última revocación del consentimiento de la Ley N.° 29733 (solo en proyectos Validado).';

-- 2.1 Reemplaza la regla 3.2 de la 02 (consent_law_29733 = (consent_at IS NOT NULL)):
--     se agrega el caso "revocado", que solo puede darse en un proyecto 'Validado'.
ALTER TABLE public.projects DROP CONSTRAINT IF EXISTS projects_consent_check;
ALTER TABLE public.projects
    ADD CONSTRAINT projects_consent_check
    CHECK (
        (consent_law_29733
            AND consent_at IS NOT NULL
            AND (consent_revoked_at IS NULL OR consent_revoked_at <= consent_at))
        OR (NOT consent_law_29733 AND consent_at IS NULL)
        OR (NOT consent_law_29733
            AND status = 'Validado'
            AND consent_at IS NOT NULL
            AND consent_revoked_at IS NOT NULL
            AND consent_revoked_at >= consent_at)
    );

-- 2.2 Reemplaza la regla 3.3 de la 02: fuera de 'Borrador' el proyecto fue enviado con
--     consentimiento; la única excepción es un proyecto 'Validado' con consentimiento revocado.
ALTER TABLE public.projects DROP CONSTRAINT IF EXISTS projects_submission_check;
ALTER TABLE public.projects
    ADD CONSTRAINT projects_submission_check
    CHECK (
        status = 'Borrador'
        OR ((consent_law_29733 OR consent_revoked_at IS NOT NULL)
            AND submitted_at IS NOT NULL
            AND professional_summary IS NOT NULL)
    );

-- 2.3 Solo se revoca el consentimiento de un proyecto 'Validado' que antes lo tuvo.
ALTER TABLE public.projects DROP CONSTRAINT IF EXISTS projects_consent_revoked_check;
ALTER TABLE public.projects
    ADD CONSTRAINT projects_consent_revoked_check
    CHECK (consent_revoked_at IS NULL OR (status = 'Validado' AND consent_at IS NOT NULL));

-- -----------------------------------------------------------------------------
-- 3. Índice del portafolio público
--    Índice parcial: solo guarda los proyectos visibles ('Validado' con consentimiento activo),
--    ordenados por estudiante y por fecha de validación, que es la consulta de la vista.
--    Una revocación saca la fila del índice en el mismo UPDATE.
-- -----------------------------------------------------------------------------
DROP INDEX IF EXISTS public.idx_projects_public_portfolio;
CREATE INDEX idx_projects_public_portfolio
    ON public.projects (student_id, decision_at DESC)
    WHERE status = 'Validado' AND consent_law_29733;

-- -----------------------------------------------------------------------------
-- 4. Vista public_verified_portfolios (HU11)
--    - Solo proyectos 'Validado' con consentimiento activo: una revocación los oculta al instante.
--    - Solo datos públicos: sin correos de estudiantes ni de docentes, sin código de matrícula,
--      sin comentarios del docente ni datos de telemetría.
--    - security_invoker: la vista se consulta con los permisos y las políticas RLS de quien la
--      usa, no con los de su dueño.
--    - Sin permisos para anon ni authenticated: solo la lee el backend (service_role), que
--      expone el portafolio por el id del estudiante, sin poner su correo en la URL.
-- -----------------------------------------------------------------------------
DROP VIEW IF EXISTS public.public_verified_portfolios;
CREATE VIEW public.public_verified_portfolios
WITH (security_invoker = true) AS
SELECT
    s.id AS student_id,
    s.full_name AS student_full_name,
    s.school AS student_school,
    s.current_cycle AS student_current_cycle,
    s.linkedin_url AS student_linkedin_url,
    s.github_url AS student_github_url,
    p.id AS project_id,
    p.title AS project_title,
    c.name AS course_name,
    p.professional_summary AS professional_summary,
    ARRAY(
        SELECT pt.technology_name::text
        FROM public.project_technologies pt
        WHERE pt.project_id = p.id
          AND pt.validated_by_teacher
        ORDER BY pt.created_at, pt.technology_name
    ) AS validated_technologies,
    p.verification_code AS verification_code,
    p.decision_at AS decision_at,
    t.full_name AS teacher_full_name
FROM public.projects p
JOIN public.users s ON s.id = p.student_id
JOIN public.courses c ON c.id = p.course_id
LEFT JOIN public.users t ON t.id = c.teacher_id
WHERE p.status = 'Validado'
  AND p.consent_law_29733
  AND s.role = 'Estudiante';

COMMENT ON VIEW public.public_verified_portfolios IS
    'HU11: proyectos Validado con consentimiento activo de la Ley N.° 29733 y solo datos públicos. Uso exclusivo del backend.';

REVOKE ALL ON public.public_verified_portfolios FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON public.public_verified_portfolios TO service_role;

-- -----------------------------------------------------------------------------
-- 5. Lo que aportaba la versión reducida de la 02 (PR #8)
--    La 02 del repositorio volvió a ser la aplicada en skillfisi-dev. De la versión del
--    PR #8 se conservan sus dos índices, que la 02 no tiene.
--    No se copian: la clave foránea fk_users_auth_id ni el UNIQUE unique_student_code,
--    porque la 02 ya los crea como users_id_fkey y users_student_code_key; tampoco el valor
--    por defecto 0 de active_review_seconds, que contradice projects_review_seconds_check
--    (sin decisión, el tiempo de revisión debe ser nulo).
-- -----------------------------------------------------------------------------

-- 5.1 Búsqueda por huella de la evidencia (caché del motor LLM).
CREATE INDEX IF NOT EXISTS idx_projects_evidence_hash
    ON public.projects (evidence_hash);

-- 5.2 Bandeja del docente: proyectos 'En Revisión' de sus cursos.
CREATE INDEX IF NOT EXISTS idx_projects_teacher_review
    ON public.projects (course_id, status)
    WHERE status = 'En Revisión';

-- 5.3 Si en alguna base se ejecutó la versión del PR #8, se quitan sus restricciones
--     duplicadas y el valor por defecto 0. En skillfisi-dev no cambia nada.
ALTER TABLE public.projects ALTER COLUMN active_review_seconds DROP DEFAULT;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'public.users'::regclass AND conname = 'users_id_fkey') THEN
        ALTER TABLE public.users DROP CONSTRAINT IF EXISTS fk_users_auth_id;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'public.users'::regclass AND conname = 'users_student_code_key') THEN
        ALTER TABLE public.users DROP CONSTRAINT IF EXISTS unique_student_code;
    END IF;
END
$$;

COMMIT;

-- -----------------------------------------------------------------------------
-- Verificación (solo lectura). Resultado esperado (12 filas):
--   1. Columnas verification_code (character varying(32)) y consent_revoked_at.
--   2. Las 6 restricciones de esta migración en projects.
--   3. Los índices idx_projects_evidence_hash, idx_projects_public_portfolio e
--      idx_projects_teacher_review, los dos últimos con su condición WHERE.
--   4. La vista con security_invoker=true y los privilegios: solo service_role con SELECT.
-- -----------------------------------------------------------------------------
SELECT '1. Columna' AS seccion, column_name::text AS objeto,
       CASE WHEN character_maximum_length IS NULL THEN data_type::text
            ELSE format('%s(%s)', data_type, character_maximum_length) END AS detalle
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'projects'
  AND column_name IN ('verification_code', 'consent_revoked_at')
UNION ALL
SELECT '2. Restricción', conname::text, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'public.projects'::regclass
  AND conname IN (
        'projects_verification_code_key', 'projects_verification_code_check',
        'projects_verification_code_status_check', 'projects_consent_check',
        'projects_submission_check', 'projects_consent_revoked_check'
      )
UNION ALL
SELECT '3. Índice', indexname::text, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND indexname IN ('idx_projects_evidence_hash', 'idx_projects_public_portfolio', 'idx_projects_teacher_review')
UNION ALL
SELECT '4. Vista', c.relname::text,
       format('opciones=%s | privilegios=%s',
              array_to_string(c.reloptions, ','),
              COALESCE((SELECT string_agg(format('%s:%s', g.grantee, g.privilege_type), ', ' ORDER BY g.grantee, g.privilege_type)
                        FROM information_schema.role_table_grants g
                        WHERE g.table_schema = 'public'
                          AND g.table_name = 'public_verified_portfolios'
                          AND g.grantee IN ('anon', 'authenticated', 'service_role', 'PUBLIC')),
                       'ninguno'))
FROM pg_class c
WHERE c.oid = 'public.public_verified_portfolios'::regclass
ORDER BY 1, 2;
