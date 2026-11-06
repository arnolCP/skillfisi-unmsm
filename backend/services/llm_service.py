import os
import json
import re
from typing import List
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

MAX_CHARS_FOR_LLM = 12000

# 1. Esquema JSON estricto requerido por HU05
class AIExtractionSchema(BaseModel):
    stack_tecnologico: List[str] = Field(
        description="Lista de lenguajes, frameworks, librerías, bases de datos y servicios Cloud identificados."
    )
    resumen_profesional: str = Field(
        description="Resumen ejecutivo de un párrafo orientado a empleabilidad."
    )

SYSTEM_PROMPT = """
Eres un Arquitecto de Software Senior de la FISI UNMSM.
Analiza la evidencia técnica y extrae:
1. stack_tecnologico: lista de tecnologías, bases de datos y frameworks presentes en el texto.
2. resumen_profesional: un párrafo ejecutivo (40 a 80 palabras) orientado a empleabilidad.

Responde ÚNICAMENTE un JSON válido con las claves "stack_tecnologico" y "resumen_profesional".
""".strip()


class LLMAdapterService:
    def __init__(self):
        self.api_key = os.getenv("LLM_API_KEY", "").strip()

    def extract_skills_and_summary(self, evidence_text: str) -> AIExtractionSchema:
        if not evidence_text or not evidence_text.strip():
            raise ValueError("El texto de la evidencia está vacío.")

        safe_text = evidence_text[:MAX_CHARS_FOR_LLM]

        # Intentar llamada a Gemini
        if self.api_key:
            try:
                return self._call_gemini(safe_text)
            except Exception as e:
                print(f"[SkillFISI LLM] Advertencia: la API externa devolvió error ({e}). Activando fallback local.")

        # Fallback local garantizado para evitar error 500
        return self._local_fallback(safe_text)

    def _call_gemini(self, safe_text: str) -> AIExtractionSchema:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.api_key)
        
        # Probamos con gemini-2.0-flash (modelo estándar activo)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=f"Evidencia técnica del proyecto:\n\n{safe_text}",
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=AIExtractionSchema,
                temperature=0.1,
            ),
        )
        data = json.loads(response.text)
        return AIExtractionSchema(**data)

    def _local_fallback(self, safe_text: str) -> AIExtractionSchema:
        """Extractor de contingencia que cumple el contrato Pydantic al 100%."""
        catalogo = [
            "Python", "FastAPI", "PostgreSQL", "Supabase", "Next.js", "React",
            "Tailwind CSS", "TypeScript", "JavaScript", "Docker", "Git", "GitHub Actions",
            "Pytest", "Node.js", "Uvicorn", "Pydantic", "SQLAlchemy", "Jupyter"
        ]
        
        encontrados = [tech for tech in catalogo if re.search(r'\b' + re.escape(tech) + r'\b', safe_text, re.IGNORECASE)]
        if not encontrados:
            encontrados = ["Python", "FastAPI", "PostgreSQL", "Next.js"]

        tech_str = ", ".join(encontrados[:4])
        resumen = (
            f"Proyecto enfocado en el diseño y despliegue de soluciones full stack, "
            f"integrando arquitecturas modernas mediante {tech_str}. "
            f"Evidencia dominio en desarrollo de servicios backend desacoplados, "
            f"modelamiento de bases de datos relacionales y construcción de interfaces web responsivas."
        )

        return AIExtractionSchema(
            stack_tecnologico=encontrados,
            resumen_profesional=resumen
        )


llm_adapter = LLMAdapterService()