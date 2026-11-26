-- =============================================================================
-- SkillFISI - Migración del Sprint 4: vistas analíticas para autoridades (HU12, HU13)
--
-- Requisitos: database/01_schema.sql a 04_sprint3_portfolio.sql aplicados.
-- Uso: ejecutar el archivo completo, de una vez, en el SQL Editor de Supabase.
--   - Va dentro de una transacción: si una sentencia falla, no se aplica ningún cambio.
--   - Se puede volver a ejecutar: usa IF NOT EXISTS y elimina cada objeto antes de crearlo.
--
-- Contenido:
--   1. courses.semester: semestre académico del curso (AAAA-1 o AAAA-2).
--   2. Índices para las consultas de BI (inteligencia de negocios).
--   3. Vista vw_curriculum_tech_metrics: tecnologías validadas por curso, ciclo y semestre.
--   4. Vista vw_teacher_sla_performance: flujo de revisión y SLA docente por curso, ciclo y semestre.
--
-- Reglas comunes de las dos vistas:
--   - Un "curso" se agrupa por nombre sin distinguir mayúsculas, ciclo y semestre, aunque lo
--     dicten varios docentes. Su nombre visible es el primero en orden binario (COLLATE "C")
--     entre los cursos del grupo, así coincide en las dos vistas y con el backend.
--   - Las métricas de tecnologías, tiempos de revisión y portafolio público solo cuentan
--     proyectos 'Validado': los borradores, en revisión y observados no las distorsionan.
--   - Los porcentajes y promedios se redondean a 2 decimales; quedan en NULL cuando no hay
--     proyectos sobre los cuales calcularlos.
--   - Sin correos ni nombres de personas: ni siquiera se consulta la tabla users.
--   - security_invoker y sin permisos para anon ni authenticated: solo las lee el backend
--     (service_role).
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 0. Comprobación previa: objetos que crea la migración 04
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    IF (
        SELECT count(*)
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'projects'
          AND column_name IN ('verification_code', 'consent_revoked_at')
    ) <> 2
    OR to_regclass('public.public_verified_portfolios') IS NULL THEN
        RAISE EXCEPTION 'Falta aplicar database/04_sprint3_portfolio.sql: no existen las columnas verification_code o consent_revoked_at en public.projects, o la vista public.public_verified_portfolios. No se aplicó ningún cambio.';
    END IF;
END
$$;

-- -----------------------------------------------------------------------------
-- 1. courses: semestre académico (HU13)
--    Los cursos que ya existían quedan en 2026-2, el semestre en curso. El backend llena
--    la columna al crear un curso (supabase_client._get_or_create_course).
-- -----------------------------------------------------------------------------
ALTER TABLE public.courses
    ADD COLUMN IF NOT EXISTS semester VARCHAR(6);

UPDATE public.courses SET semester = '2026-2' WHERE semester IS NULL;

ALTER TABLE public.courses ALTER COLUMN semester SET DEFAULT '2026-2';
ALTER TABLE public.courses ALTER COLUMN semester SET NOT NULL;

-- 1.1 Formato AAAA-1 o AAAA-2 (por ejemplo, 2026-2).
ALTER TABLE public.courses DROP CONSTRAINT IF EXISTS courses_semester_check;
ALTER TABLE public.courses
    ADD CONSTRAINT courses_semester_check
    CHECK (semester ~ '^[0-9]{4}-[12]$');

COMMENT ON COLUMN public.courses.semester IS
    'HU13: semestre académico en que se dicta el curso, con formato AAAA-1 o AAAA-2 (por ejemplo, 2026-2).';

-- 1.2 Un docente puede dictar el mismo curso en distintos semestres: cada semestre es un curso
--     propio. Reemplaza el índice courses_teacher_name_key de la 02 (docente y nombre) por uno
--     que además incluye el semestre. Si se vuelve a ejecutar la 02, ejecutar después esta 05.
DROP INDEX IF EXISTS public.courses_teacher_name_key;
DROP INDEX IF EXISTS public.courses_teacher_name_semester_key;
CREATE UNIQUE INDEX courses_teacher_name_semester_key
    ON public.courses (teacher_id, lower(name), semester);

-- -----------------------------------------------------------------------------
-- 2. Índices para las consultas de BI
-- -----------------------------------------------------------------------------

-- 2.1 Filtros por semestre y ciclo, y agrupación por nombre de curso sin mayúsculas.
DROP INDEX IF EXISTS public.idx_courses_bi_semester_cycle;
CREATE INDEX idx_courses_bi_semester_cycle
    ON public.courses (semester, cycle, lower(name));

-- 2.2 Conteo por curso y estado con los datos del SLA y del consentimiento en el mismo índice:
--     las dos vistas leen los proyectos de cada curso sin visitar la tabla.
DROP INDEX IF EXISTS public.idx_projects_bi_course_status;
CREATE INDEX idx_projects_bi_course_status
    ON public.projects (course_id, status)
    INCLUDE (id, active_review_seconds, consent_law_29733);

-- 2.3 Índice parcial: solo las tecnologías validadas por el docente, con su nombre.
DROP INDEX IF EXISTS public.idx_project_technologies_bi_validated;
CREATE INDEX idx_project_technologies_bi_validated
    ON public.project_technologies (project_id)
    INCLUDE (technology_name)
    WHERE validated_by_teacher;

-- -----------------------------------------------------------------------------
-- 3. Vista vw_curriculum_tech_metrics (HU12, HU13)
--    Una fila por curso, ciclo, semestre y tecnología validada (sin distinguir mayúsculas).
--    - project_count: proyectos 'Validado' del grupo que usan la tecnología (cada proyecto
--      cuenta una sola vez aunque repita la etiqueta).
--    - validated_projects: total de proyectos 'Validado' del grupo.
--    - usage_percent: project_count sobre validated_projects.
--    - technology: la forma de escribirla más usada en el grupo; si empatan, la primera en
--      orden binario.
--    Solo cuenta las tecnologías marcadas validated_by_teacher de proyectos 'Validado'.
-- -----------------------------------------------------------------------------
DROP VIEW IF EXISTS public.vw_curriculum_tech_metrics;
CREATE VIEW public.vw_curriculum_tech_metrics
WITH (security_invoker = true) AS
WITH course_groups AS (
    SELECT lower(c.name) AS course_key,
           c.cycle,
           c.semester,
           min(c.name COLLATE "C") AS course_name
    FROM public.courses c
    GROUP BY lower(c.name), c.cycle, c.semester
),
-- NOT MATERIALIZED: se usa dos veces, y así los filtros por ciclo y semestre llegan a la tabla.
validated_projects AS NOT MATERIALIZED (
    SELECT p.id AS project_id,
           lower(c.name) AS course_key,
           c.cycle,
           c.semester
    FROM public.projects p
    JOIN public.courses c ON c.id = p.course_id
    WHERE p.status = 'Validado'
),
validated_per_group AS (
    SELECT course_key, cycle, semester, count(*) AS validated_projects
    FROM validated_projects
    GROUP BY course_key, cycle, semester
),
technology_uses AS (
    -- Una fila por proyecto y forma de escribir la tecnología.
    SELECT DISTINCT
           v.course_key,
           v.cycle,
           v.semester,
           v.project_id,
           lower(pt.technology_name) AS technology_key,
           pt.technology_name::text AS technology_name
    FROM validated_projects v
    JOIN public.project_technologies pt
      ON pt.project_id = v.project_id
     AND pt.validated_by_teacher
),
technology_per_group AS (
    SELECT course_key,
           cycle,
           semester,
           technology_key,
           mode() WITHIN GROUP (ORDER BY technology_name COLLATE "C") AS technology,
           count(DISTINCT project_id) AS project_count
    FROM technology_uses
    GROUP BY course_key, cycle, semester, technology_key
)
SELECT g.course_name::text COLLATE "default" AS course_name,
       t.cycle AS cycle,
       t.semester::text AS semester,
       t.technology COLLATE "default" AS technology,
       t.project_count::integer AS project_count,
       v.validated_projects::integer AS validated_projects,
       round(100.0 * t.project_count / v.validated_projects, 2) AS usage_percent
FROM technology_per_group t
JOIN validated_per_group v USING (course_key, cycle, semester)
JOIN course_groups g USING (course_key, cycle, semester);

COMMENT ON VIEW public.vw_curriculum_tech_metrics IS
    'HU12/HU13: tecnologías validadas por el docente en proyectos Validado, por curso, ciclo y semestre. Sin datos de personas. Uso exclusivo del backend.';

REVOKE ALL ON public.vw_curriculum_tech_metrics FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON public.vw_curriculum_tech_metrics TO service_role;

-- -----------------------------------------------------------------------------
-- 4. Vista vw_teacher_sla_performance (HU12, HU13)
--    Una fila por curso, ciclo y semestre con al menos un proyecto.
--    - registered_projects: todos los proyectos (incluye borradores).
--    - in_review_projects, observed_projects, validated_projects: proyectos en cada estado.
--    - validation_rate_percent: validados sobre decididos ('Validado' + 'Observado').
--    - total_review_seconds y avg_review_seconds: suma y promedio de active_review_seconds
--      de los proyectos 'Validado'.
--    - reviews_within_sla y reviews_within_sla_percent: proyectos 'Validado' revisados en
--      300 segundos o menos, y su porcentaje sobre los validados.
--    - public_portfolio_projects y public_portfolio_percent: proyectos 'Validado' con
--      consentimiento activo de la Ley N.° 29733 (visibles en el portafolio público).
--    Las columnas de conteo y suma permiten calcular indicadores globales exactos sumando filas.
-- -----------------------------------------------------------------------------
DROP VIEW IF EXISTS public.vw_teacher_sla_performance;
CREATE VIEW public.vw_teacher_sla_performance
WITH (security_invoker = true) AS
WITH course_groups AS (
    SELECT lower(c.name) AS course_key,
           c.cycle,
           c.semester,
           min(c.name COLLATE "C") AS course_name
    FROM public.courses c
    GROUP BY lower(c.name), c.cycle, c.semester
),
per_group AS (
    SELECT lower(c.name) AS course_key,
           c.cycle,
           c.semester,
           count(*) AS registered_projects,
           count(*) FILTER (WHERE p.status = 'En Revisión') AS in_review_projects,
           count(*) FILTER (WHERE p.status = 'Observado') AS observed_projects,
           count(*) FILTER (WHERE p.status = 'Validado') AS validated_projects,
           sum(p.active_review_seconds) FILTER (WHERE p.status = 'Validado') AS total_review_seconds,
           avg(p.active_review_seconds) FILTER (WHERE p.status = 'Validado') AS avg_review_seconds,
           count(*) FILTER (WHERE p.status = 'Validado' AND p.active_review_seconds <= 300) AS reviews_within_sla,
           count(*) FILTER (WHERE p.status = 'Validado' AND p.consent_law_29733) AS public_portfolio_projects
    FROM public.projects p
    JOIN public.courses c ON c.id = p.course_id
    GROUP BY lower(c.name), c.cycle, c.semester
)
SELECT g.course_name::text COLLATE "default" AS course_name,
       s.cycle AS cycle,
       s.semester::text AS semester,
       s.registered_projects::integer AS registered_projects,
       s.in_review_projects::integer AS in_review_projects,
       s.observed_projects::integer AS observed_projects,
       s.validated_projects::integer AS validated_projects,
       round(100.0 * s.validated_projects / NULLIF(s.validated_projects + s.observed_projects, 0), 2)
           AS validation_rate_percent,
       s.total_review_seconds::bigint AS total_review_seconds,
       round(s.avg_review_seconds, 2) AS avg_review_seconds,
       s.reviews_within_sla::integer AS reviews_within_sla,
       round(100.0 * s.reviews_within_sla / NULLIF(s.validated_projects, 0), 2) AS reviews_within_sla_percent,
       s.public_portfolio_projects::integer AS public_portfolio_projects,
       round(100.0 * s.public_portfolio_projects / NULLIF(s.validated_projects, 0), 2) AS public_portfolio_percent
FROM per_group s
JOIN course_groups g USING (course_key, cycle, semester);

COMMENT ON VIEW public.vw_teacher_sla_performance IS
    'HU12/HU13: proyectos por estado, tasa de validación, SLA de revisión docente (300 s) y portafolios públicos por curso, ciclo y semestre. Sin datos de personas. Uso exclusivo del backend.';

REVOKE ALL ON public.vw_teacher_sla_performance FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON public.vw_teacher_sla_performance TO service_role;

COMMIT;

-- -----------------------------------------------------------------------------
-- Verificación (solo lectura). Resultado esperado (9 filas):
--   1. Columna semester: character varying(6), NOT NULL, por defecto '2026-2'.
--   2. Restricción courses_semester_check.
--   3. Índices courses_teacher_name_semester_key, idx_courses_bi_semester_cycle,
--      idx_project_technologies_bi_validated (con su WHERE) e idx_projects_bi_course_status,
--      y courses_teacher_name_key marcado como reemplazado.
--   4. Las dos vistas con security_invoker=true, solo service_role con SELECT y su número de filas.
-- -----------------------------------------------------------------------------
SELECT '1. Columna' AS seccion, 'courses.semester' AS objeto,
       format('%s(%s) | nulos=%s | por defecto=%s | cursos sin semestre válido=%s',
              data_type, character_maximum_length, is_nullable, column_default,
              (SELECT count(*) FROM public.courses WHERE semester !~ '^[0-9]{4}-[12]$')) AS detalle
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'courses' AND column_name = 'semester'
UNION ALL
SELECT '2. Restricción', conname::text, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'public.courses'::regclass AND conname = 'courses_semester_check'
UNION ALL
SELECT '3. Índice', indexname::text, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND indexname IN ('courses_teacher_name_semester_key', 'idx_courses_bi_semester_cycle',
                    'idx_projects_bi_course_status', 'idx_project_technologies_bi_validated')
UNION ALL
SELECT '3. Índice', 'courses_teacher_name_key',
       CASE WHEN to_regclass('public.courses_teacher_name_key') IS NULL
            THEN 'no existe: reemplazado por courses_teacher_name_semester_key'
            ELSE 'ERROR: todavía existe' END
UNION ALL
SELECT '4. Vista', c.relname::text,
       format('opciones=%s | privilegios=%s | filas=%s',
              array_to_string(c.reloptions, ','),
              COALESCE((SELECT string_agg(format('%s:%s', g.grantee, g.privilege_type), ', ' ORDER BY g.grantee, g.privilege_type)
                        FROM information_schema.role_table_grants g
                        WHERE g.table_schema = 'public'
                          AND g.table_name = c.relname
                          AND g.grantee IN ('anon', 'authenticated', 'service_role', 'PUBLIC')),
                       'ninguno'),
              CASE c.relname
                  WHEN 'vw_curriculum_tech_metrics' THEN (SELECT count(*) FROM public.vw_curriculum_tech_metrics)
                  ELSE (SELECT count(*) FROM public.vw_teacher_sla_performance)
              END)
FROM pg_class c
WHERE c.oid IN ('public.vw_curriculum_tech_metrics'::regclass, 'public.vw_teacher_sla_performance'::regclass)
ORDER BY 1, 2;
