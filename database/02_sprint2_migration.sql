-- ====================================================================
-- MIGRACIÓN INCREMENTAL SPRINT 2 - SkillFISI
-- Paquetes: 2.3, 3.1, 3.2, 3.4
-- ====================================================================

-- 1. Vinculación de la tabla pública users con Supabase Auth (auth.users)
ALTER TABLE public.users
DROP CONSTRAINT IF EXISTS fk_users_auth_id,
ADD CONSTRAINT fk_users_auth_id 
FOREIGN KEY (id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- 2. Restricción UNIQUE para código de estudiante (HU02)
ALTER TABLE public.users 
DROP CONSTRAINT IF EXISTS unique_student_code,
ADD CONSTRAINT unique_student_code UNIQUE (student_code);

-- 3. Añadir columnas de telemetría, retroalimentación y huella de caché (HU06, HU07)
ALTER TABLE public.projects
ADD COLUMN IF NOT EXISTS teacher_feedback TEXT,
ADD COLUMN IF NOT EXISTS active_review_seconds INT DEFAULT 0,
ADD COLUMN IF NOT EXISTS evidence_hash VARCHAR(64);

-- 4. Índice para acelerar la búsqueda por huella de evidencias (Caché LLM)
CREATE INDEX IF NOT EXISTS idx_projects_evidence_hash ON public.projects(evidence_hash);

-- 5. Índice para agilizar la carga de la bandeja docente por estado
CREATE INDEX IF NOT EXISTS idx_projects_teacher_review 
ON public.projects(course_id, status) 
WHERE status = 'En Revisión';

-- Comentarios explicativos
COMMENT ON COLUMN public.projects.active_review_seconds IS 'Tiempo activo que el docente pasó revisando el proyecto antes de emitir dictamen (Meta SLA <= 300 s)';
COMMENT ON COLUMN public.projects.evidence_hash IS 'Hash SHA-256 de las evidencias para evitar reprocesamientos redundantes en el motor LLM';