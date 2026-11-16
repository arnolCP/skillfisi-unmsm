# QA del Sprint 3

Desde la raíz, ejecuta `python -m pytest -q`. Para revisar este incremento por
separado, ejecuta `python -m pytest -q tests/test_sprint3_portfolio_and_seal.py`.
Las pruebas pasan por la aplicación FastAPI con identidades de prueba y
almacenamiento en memoria.

| Criterio | Comprobación por HTTP |
| --- | --- |
| HU08 · Subsanación | El titular puede reenviar un proyecto observado con consentimiento. Se guardan las correcciones y la observación previa, se reinicia la telemetría y el proyecto vuelve a la bandeja docente. |
| HU10 · Sello | Una decisión de validación emite un código `FISI-2026-XXXXXX`. El portafolio, la consulta por proyecto y el verificador por código devuelven el mismo código. |
| HU11 · Publicación | Borradores, proyectos en revisión y proyectos observados quedan ocultos incluso con consentimiento activo. El portafolio tampoco incluye los comentarios del docente. |
| HU11 · Revocación | Un cambio autorizado retira el proyecto en la siguiente consulta. Ambas rutas públicas del sello devuelven 404 y las respuestas incluyen `Cache-Control: no-store`. |
| HU11 · Titularidad | Para modificar el consentimiento se requiere un token de sesión del titular. El correo del cuerpo es opcional y, si se envía, debe coincidir. Los listados y detalles internos también requieren autenticación. |

La suite local aprobó 146 casos, incluidos 7 del Sprint 3. La evaluación en
vivo con Gemini quedó omitida. Estas pruebas cubren la API en modo local.
La pantalla pública, la persistencia en Supabase, las políticas RLS y el
tiempo de carga requieren verificación con los componentes de sus respectivas ramas.

## Corte EVM proyectado

El entregable declara un corte al 22 de noviembre de 2026. Sus cifras para la
semana 7 son 80 HH del sprint y 280 HH acumuladas (70 % de las 400 HH
planificadas), con PV, EV y AC de S/ 8 050. Con esos valores, SPI y CPI serían
1,00, SV y CV serían S/ 0 y el EAC sería S/ 13 500 con el BAC declarado.

Este cálculo reproduce el escenario del entregable. El cierre queda sujeto a
validar EV con las historias aceptadas según la regla 0/100 y AC con las horas
y gastos registrados en la matriz del equipo.
