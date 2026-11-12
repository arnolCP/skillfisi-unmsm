-- =============================================================================
-- SkillFISI - Políticas RLS (Row Level Security, seguridad a nivel de fila)
-- Protección de datos personales según la Ley N.° 29733
--
-- Requisitos: database/01_schema.sql y database/02_sprint2_migration.sql aplicados.
-- Uso: ejecutar el archivo completo en el SQL Editor de Supabase.
--   - Va dentro de una transacción: si una sentencia falla, no se aplica ningún cambio.
--   - Se puede volver a ejecutar: borra y recrea las políticas y vuelve a fijar los permisos.
--
-- Contexto:
--   - El backend usa la clave service_role, que omite RLS: este archivo no lo afecta y
--     no modifica ningún permiso de ese rol.
--   - Al iniciar sesión el navegador recibe el token del usuario, y la clave anon no es
--     secreta. Con ambos se podría consultar la Data API de Supabase sin pasar por el
--     backend. Estas reglas limitan lo que cada persona puede ver o cambiar en ese caso.
--
-- Relación con la Ley N.° 29733 (Ley de Protección de Datos Personales):
--   - Proporcionalidad: cada usuario accede solo a los datos que necesita para su función.
--   - Consentimiento: el docente ve un proyecto solo cuando el estudiante ya lo envió
--     aceptando la ley (estado distinto de 'Borrador').
--   - Seguridad (art. 16) y confidencialidad (art. 17): no hay acceso anónimo ni escrituras
--     directas; los cambios pasan por el backend, que valida reglas y permisos.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 1. RLS activado en todas las tablas con datos del sistema
-- -----------------------------------------------------------------------------
ALTER TABLE public.users                ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.courses              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.projects             ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.evidences            ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.project_technologies ENABLE ROW LEVEL SECURITY;

-- -----------------------------------------------------------------------------
-- 2. Privilegios de tabla (RLS filtra filas; estos permisos limitan las operaciones)
-- -----------------------------------------------------------------------------

-- 2.1 anon (visitante sin sesión): ningún acceso a los datos personales.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon;

-- 2.2 authenticated (usuario con sesión): se parte de cero. TRUNCATE no está sujeto a RLS,
--     por eso se quita junto con INSERT, DELETE, REFERENCES y TRIGGER.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM authenticated;

-- 2.3 Solo lectura, siempre filtrada por las políticas de la sección 4.
GRANT SELECT ON public.users, public.courses, public.projects, public.evidences, public.project_technologies
    TO authenticated;

-- 2.4 Cada usuario puede corregir los datos de su perfil académico (derecho de rectificación),
--     pero nunca su rol, su correo ni su id.
GRANT UPDATE (student_code, school, current_cycle, linkedin_url, github_url)
    ON public.users TO authenticated;

-- 2.5 Tablas futuras creadas desde el SQL Editor: anon y authenticated no reciben permisos
--     automáticos. Cada migración debe otorgar de forma explícita lo que necesite.
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON TABLES FROM anon;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON TABLES FROM authenticated;

-- -----------------------------------------------------------------------------
-- 3. Función auxiliar en un esquema que la Data API no expone
-- -----------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS private;
REVOKE ALL ON SCHEMA private FROM PUBLIC;
GRANT USAGE ON SCHEMA private TO authenticated;

-- ¿El usuario de la sesión es el docente del curso? SECURITY DEFINER evita depender de las
-- políticas de courses, y el search_path vacío obliga a nombrar cada objeto con su esquema.
CREATE OR REPLACE FUNCTION private.is_course_teacher(p_course_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM public.courses AS c
        WHERE c.id = p_course_id
          AND c.teacher_id = (SELECT auth.uid())
    );
$$;

REVOKE ALL ON FUNCTION private.is_course_teacher(uuid) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION private.is_course_teacher(uuid) TO authenticated;

-- -----------------------------------------------------------------------------
-- 4. Políticas
-- -----------------------------------------------------------------------------

-- 4.1 Se eliminan todas las políticas previas de estas tablas, para que solo rijan las de
--     este archivo (las políticas permisivas se suman: una olvidada abriría el acceso).
DO $$
DECLARE
    pol record;
BEGIN
    FOR pol IN
        SELECT schemaname, tablename, policyname
        FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename IN ('users', 'courses', 'projects', 'evidences', 'project_technologies')
    LOOP
        EXECUTE format('DROP POLICY %I ON %I.%I', pol.policyname, pol.schemaname, pol.tablename);
    END LOOP;
END
$$;

-- 4.2 users: cada persona ve y edita solo su propia fila.
CREATE POLICY users_select_own ON public.users
    FOR SELECT TO authenticated
    USING (id = (SELECT auth.uid()));

CREATE POLICY users_update_own ON public.users
    FOR UPDATE TO authenticated
    USING (id = (SELECT auth.uid()))
    WITH CHECK (id = (SELECT auth.uid()));

-- 4.3 courses: catálogo sin datos personales; lo leen los usuarios con sesión.
CREATE POLICY courses_select_authenticated ON public.courses
    FOR SELECT TO authenticated
    USING (true);

-- 4.4 projects: el estudiante dueño, o el docente del curso solo cuando el proyecto ya fue
--     enviado con consentimiento (los borradores son privados del estudiante).
CREATE POLICY projects_select_owner_or_course_teacher ON public.projects
    FOR SELECT TO authenticated
    USING (
        student_id = (SELECT auth.uid())
        OR (status <> 'Borrador' AND private.is_course_teacher(course_id))
    );

-- 4.5 evidences y project_technologies: visibles para quien puede ver su proyecto.
--     La subconsulta a projects aplica la política 4.4, así que la regla es la misma.
CREATE POLICY evidences_select_like_project ON public.evidences
    FOR SELECT TO authenticated
    USING (EXISTS (SELECT 1 FROM public.projects AS p WHERE p.id = evidences.project_id));

CREATE POLICY project_technologies_select_like_project ON public.project_technologies
    FOR SELECT TO authenticated
    USING (EXISTS (SELECT 1 FROM public.projects AS p WHERE p.id = project_technologies.project_id));

COMMIT;

-- -----------------------------------------------------------------------------
-- Verificación (solo lectura). Resultado esperado:
--   1. rls_activado=true en las 5 tablas.
--   2. Las 6 políticas de este archivo, todas para authenticated.
--   3. anon con 0 privilegios; authenticated solo con SELECT en cada tabla.
--   4. UPDATE de authenticated solo en las 5 columnas editables de users.
--   5. Ninguna tabla futura otorga permisos automáticos a anon ni a authenticated.
--   6. Función auxiliar con security_definer=true y search_path vacío.
-- -----------------------------------------------------------------------------
SELECT '1. RLS' AS seccion, c.relname::text AS objeto,
       format('rls_activado=%s', c.relrowsecurity) AS detalle
FROM pg_class c
WHERE c.relnamespace = 'public'::regnamespace
  AND c.relname IN ('users', 'courses', 'projects', 'evidences', 'project_technologies')
UNION ALL
SELECT '2. Políticas', tablename::text || ' / ' || policyname::text,
       format('cmd=%s | roles=%s | using=%s', cmd, roles, qual)
FROM pg_policies
WHERE schemaname = 'public'
UNION ALL
SELECT '3. Privilegios de tabla', 'anon (total en public)',
       format('%s privilegios', count(*))
FROM information_schema.role_table_grants
WHERE table_schema = 'public' AND grantee = 'anon'
UNION ALL
SELECT '3. Privilegios de tabla', 'authenticated -> ' || table_name::text,
       string_agg(privilege_type::text, ', ' ORDER BY privilege_type::text)
FROM information_schema.role_table_grants
WHERE table_schema = 'public' AND grantee = 'authenticated'
GROUP BY table_name
UNION ALL
SELECT '4. Columnas editables', 'authenticated -> users (UPDATE)',
       string_agg(column_name::text, ', ' ORDER BY column_name::text)
FROM information_schema.column_privileges
WHERE table_schema = 'public' AND table_name = 'users'
  AND grantee = 'authenticated' AND privilege_type = 'UPDATE'
UNION ALL
SELECT '5. Permisos por defecto', 'anon o authenticated en tablas futuras de postgres',
       format('presentes=%s', EXISTS (
           SELECT 1
           FROM pg_default_acl d, aclexplode(d.defaclacl) a
           WHERE d.defaclnamespace = 'public'::regnamespace
             AND d.defaclrole = 'postgres'::regrole
             AND d.defaclobjtype = 'r'
             AND a.grantee IN ('anon'::regrole, 'authenticated'::regrole)
       ))
UNION ALL
SELECT '6. Función auxiliar', p.oid::regprocedure::text,
       format('security_definer=%s | config=%s', p.prosecdef, array_to_string(p.proconfig, ','))
FROM pg_proc p
WHERE p.pronamespace = 'private'::regnamespace AND p.proname = 'is_course_teacher'
ORDER BY 1, 2;
