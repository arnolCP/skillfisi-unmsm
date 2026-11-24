# QA del Sprint 4 y control del Hito 3

Responsable: Miguel Ángel Sanchez Osorio. Rama: `feature/sprint4-qa-dashboard-hito3`.
Base de integración: `a47985b`. Corte de preparación: 24 de noviembre de 2026.

## Estado de la entrega

Se prepararon 13 casos de aceptación en `tests/test_sprint4_analytics_dashboard.py`.
El backend analítico aún falta en la base integrada. La suite omite estos casos
con una razón explícita mientras falte `backend/routers/analytics_dashboard.py`.
Al añadirse el archivo, los casos se habilitan automáticamente. Si el router
existe y sus rutas aún no están registradas en `main.py`, las pruebas fallan.

El resultado local es **179 aprobadas y 14 omitidas** (13 del dashboard y una
evaluación opcional de Gemini). Los casos
omitidos del dashboard quedan pendientes de ejecución con la implementación de
Arnol y Erick y la fuente de datos de Demian.

## Criterios y datos de aceptación

La muestra local contiene siete proyectos distribuidos entre dos cursos, dos
ciclos y dos semestres. Cuatro están validados, uno en borrador, uno en revisión
y uno observado. La tecnología exclusiva de los registros sin validar y el
tiempo de revisión de 900 segundos del proyecto observado permiten detectar
contaminación en las métricas curriculares.

| Criterio | Resultado esperado de la muestra |
| --- | --- |
| HU12 · Conteos | 7 registrados, 4 validados y tasa de validación de 4/7 × 100. |
| HU12 · Tecnologías | Python aparece en 3 proyectos (75 % de los validados). Repetir una etiqueta dentro del mismo proyecto cuenta una sola vez. |
| HU12 · Tiempo docente | Promedio de 180 segundos calculado con los cuatro proyectos validados. |
| HU12 · Consentimiento | El proyecto validado sin consentimiento público participa en las métricas internas. Su porcentaje público individual es 0 %. |
| HU13 · Filtros | Se verifican curso, ciclo y semestre por separado y sus cuatro combinaciones. |
| HU13 · Resultado vacío | Curso sin coincidencias devuelve conteos y tasa en cero, ranking vacío y tiempo promedio nulo. |
| HU13 · Reporte curricular | El reporte de sílabos aplica simultáneamente curso, ciclo y semestre. |
| Integración | El endpoint de salud informa activos los seis módulos, 3.1 a 3.6. |

## Contrato propuesto para integrar las pruebas

La planificación define las rutas y métricas, pero deja abiertos los nombres
de varios campos JSON. Estos nombres constituyen una propuesta de QA para
coordinar con los responsables del backend y frontend.

`GET /api/v1/analytics/dashboard` recibe `course_name`, `cycle` y `semester`
como parámetros opcionales y combinables. La suite espera:

| Campo JSON | Definición |
| --- | --- |
| `total_projects` | Total de proyectos que coinciden con los filtros, en todos los estados. |
| `total_validated_projects` | Total de proyectos filtrados cuyo estado es Validado. |
| `validation_rate_percent` | Validados / registrados × 100, o 0 cuando no hay registros. |
| `avg_review_seconds` | Promedio de tiempos de revisión de proyectos validados, o null sin datos. |
| `top_technologies` | Lista de objetos con `technology`, `project_count` y `percentage`, sobre proyectos validados. |
| `public_portfolio_percent` | Porcentaje de proyectos validados con consentimiento público activo. |

`GET /api/v1/analytics/syllabus-report` recibe los mismos filtros. La propuesta
incluye `total_validated_projects` y `courses`, una lista con `course_name`,
`total_validated_projects` y `top_technologies` para cada asignatura.

La identidad de Autoridad y la consulta de su rol están simuladas en las pruebas.
La fuente de prueba usa el almacén compartido `routers.projects.PROJECTS_DB`,
empleado por los routers actuales del proyecto. Al integrar la consulta
persistente de Demian, habrá que conectar la muestra a ese punto de lectura y
acordar los nombres JSON definitivos antes de cerrar la validación.

## Ejecución y evidencias

Desde la raíz del repositorio:

```powershell
.\.venv\Scripts\python.exe -m pytest -v -rs tests/test_sprint4_analytics_dashboard.py
.\.venv\Scripts\python.exe -m pytest -q -rs
```

El primer comando muestra los casos específicos y el motivo de las omisiones.
El segundo comprueba la regresión completa. GitHub Actions ya ejecuta la suite
en cada push y pull request.

Las capturas para el informe deben indicar el estado real de las pruebas.
La aceptación del dashboard, sus tiempos de respuesta, la vista de autoridades
y la ejecución sobre Supabase requieren verificación después de la integración.

## Línea base EVM de la Semana 8

El corte previsto del Hito 3 corresponde al 29 de noviembre de 2026.

| Concepto | Línea base |
| --- | --- |
| Esfuerzo de la semana 8 | 40 HH |
| Esfuerzo acumulado | 320 HH de 400 HH (80,00 %) |
| Cuenta CC-02 al cierre previsto | 240 HH de desarrollo |
| PV semanal | S/ 1 100 (S/ 1 000 de esfuerzo + S/ 100 de entorno Cloud BI) |
| PV acumulado | S/ 9 150 |
| Participación sobre costos directos de S/ 12 000 | 76,25 % |

EV queda pendiente de acreditar los paquetes terminados y aceptados con la regla
0/100. AC depende de las horas y gastos reales registrados. Por tanto, SPI
(EV/PV), CPI (EV/AC), SV (EV−PV), CV (EV−AC) y EAC (BAC/CPI) quedan pendientes
del corte real. La preparación de esta suite acredita el avance de QA y el
cierre del Hito 3 requiere aceptar el incremento integrado.
