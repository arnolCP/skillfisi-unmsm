# QA del Sprint 2

Desde la raíz del repositorio, instala las dependencias con
`python -m pip install -r backend/requirements.txt` y ejecuta `python -m pytest -q`.
La suite valida por HTTP la ingesta de un notebook, el caché de extracción, el
consentimiento, la bandeja del docente asignado y los dictámenes con telemetría.
Las pruebas usan identidades simuladas y almacenamiento en memoria.

## Golden Dataset

`tests/golden_dataset.json` reúne 10 evidencias sintéticas de proyectos académicos
de desarrollo web, IA, móviles, IoT, nube y bases de datos. Incluye dependencias,
alias y tecnologías evaluadas pero descartadas. Cada caso aporta el mismo peso
al promedio de precisión y al promedio de recall. Al comparar etiquetas se
ignoran mayúsculas, espacios exteriores y duplicados.

Para medir la heurística local, ejecuta
`python -m pytest -q -s tests/test_sprint2_hitl_and_review.py -k golden_dataset_local`.
Resultado de referencia en esta rama: **60,0 % de precisión** y **29,3 % de recall**.

Para medir Gemini, configura `LLM_API_KEY` en el entorno y ejecuta:

```sh
python -m pytest -q -s --gemini-live tests/test_sprint2_hitl_and_review.py -k golden_dataset_gemini
```

También puedes lanzar el flujo **Pruebas de calidad** en GitHub Actions con
`evaluate_gemini` activado y el secreto `LLM_API_KEY` configurado. La evaluación
hace una solicitud por caso y exige precisión promedio de al menos 85 % y
recall promedio de al menos 80 %. Un fallo del proveedor interrumpe la
evaluación. El modelo se puede fijar con `LLM_MODEL`.

La ejecución remota con Gemini y la verificación de persistencia y RLS con
Supabase quedan pendientes hasta disponer del entorno correspondiente.

## Corte EVM del Hito 2

El borrador del sprint consigna 40 HH para la semana 5 y 200 HH acumuladas,
con PV, EV y AC de S/ 5 800 cada uno. Con esos valores, SPI y CPI serían 1,00.
La línea base del manual de gestión registra PV acumulado de S/ 5 850 para ese
corte. Hay que reconciliar el PV con la matriz oficial y validar EV y AC con
los entregables aceptados y los costos reales antes de cerrar el reporte.
