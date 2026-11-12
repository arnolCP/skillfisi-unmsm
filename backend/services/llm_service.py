import os
import hashlib
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class AIExtractionSchema(BaseModel):
    stack_tecnologico: List[str] = Field(
        description="Lista de frameworks, lenguajes, bases de datos y herramientas de infraestructura detectadas."
    )
    resumen_profesional: str = Field(
        description="Resumen ejecutivo de un párrafo orientado a empleabilidad técnica."
    )


class LLMAdapterService:
    def __init__(self):
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.provider = os.getenv("LLM_PROVIDER", "gemini")
        self.max_chars = 12000
        # Almacén de caché en memoria y métricas
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_stats = {"hits": 0, "misses": 0, "total_requests": 0}

    def _compute_hash(self, text: str) -> str:
        """Calcula el identificador único SHA-256 del texto de evidencia."""
        return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()

    def get_cache_metrics(self) -> Dict[str, Any]:
        """Retorna las métricas operativas del subsistema de caché."""
        total = self._cache_stats["total_requests"]
        hit_ratio = (self._cache_stats["hits"] / total) if total > 0 else 0.0
        return {
            "cache_size": len(self._cache),
            "hits": self._cache_stats["hits"],
            "misses": self._cache_stats["misses"],
            "total_requests": total,
            "hit_ratio_percent": round(hit_ratio * 100, 2),
        }

    def _build_calibrated_prompt(self) -> str:
        """System Prompt con calibración Few-Shot para proyectos de ingeniería FISI."""
        return """Eres un evaluador técnico de arquitecturas de software y portafolios de ingeniería de sistemas de la FISI - UNMSM.
Tu tarea es analizar evidencias de proyectos (README, dependencias, código) y generar estrictamente un objeto JSON.
Reglas de extracción:
1. Identifica únicamente herramientas y tecnologías explícitamente utilizadas (lenguajes, frameworks, BD, Cloud/DevOps).
2. Redacta un resumen ejecutivo formal de 1 párrafo destacando arquitectura, buenas prácticas y valor técnico.

### EJEMPLO 1 (Few-Shot):
Entrada: Sistema backend con FastAPI, PostgreSQL, Supabase y Next.js con Tailwind.
Salida JSON:
{"stack_tecnologico": ["FastAPI", "Python", "PostgreSQL", "Supabase", "Next.js", "Tailwind CSS"], "resumen_profesional": "Solución full-stack desacoplada con API REST asíncrona, persistencia en la nube mediante PostgreSQL y diseño frontend modular responsivo."}

### EJEMPLO 2 (Few-Shot):
Entrada: Microservicio en Spring Boot con Java 17, JPA/Hibernate, base MySQL y contenedor Docker.
Salida JSON:
{"stack_tecnologico": ["Java", "Spring Boot", "JPA", "Hibernate", "MySQL", "Docker"], "resumen_profesional": "Microservicio empresarial implementado bajo arquitectura robusta orientada al dominio, gestión de transacciones ORM y empaquetamiento contenerizado."}
"""

    def extract_skills_and_summary(self, evidence_text: str) -> Dict[str, Any]:
        if not evidence_text or not evidence_text.strip():
            raise ValueError("El texto de la evidencia está vacío.")

        safe_text = evidence_text[: self.max_chars]
        text_hash = self._compute_hash(safe_text)
        self._cache_stats["total_requests"] += 1

        # 1. Comprobación en Caché (Hit)
        if text_hash in self._cache:
            self._cache_stats["hits"] += 1
            cached_data = self._cache[text_hash]
            return {
                "data": cached_data,
                "cached": True,
                "hash": text_hash,
            }

        # 2. Caché Miss: Ejecución vía Gemini API
        self._cache_stats["misses"] += 1
        result_data: Optional[AIExtractionSchema] = None

        if self.api_key:
            try:
                result_data = self._call_gemini(safe_text)
            except Exception as e:
                print(f"[SkillFISI LLM Warning] Error en API externa: {e}. Activando fallback.")
                result_data = self._local_fallback(safe_text)
        else:
            result_data = self._local_fallback(safe_text)

        formatted_result = result_data.model_dump()

        # Guardar en caché
        self._cache[text_hash] = formatted_result

        return {
            "data": formatted_result,
            "cached": False,
            "hash": text_hash,
        }

    def _call_gemini(self, safe_text: str) -> AIExtractionSchema:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.api_key)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=f"Evidencia técnica del proyecto:\n\n{safe_text}",
            config=types.GenerateContentConfig(
                system_instruction=self._build_calibrated_prompt(),
                response_mime_type="application/json",
                response_schema=AIExtractionSchema,
                temperature=0.1,
            ),
        )
        return AIExtractionSchema.model_validate_json(response.text)

    def _local_fallback(self, safe_text: str) -> AIExtractionSchema:
        keywords = {
            "python": "Python",
            "fastapi": "FastAPI",
            "flask": "Flask",
            "django": "Django",
            "next.js": "Next.js",
            "nextjs": "Next.js",
            "react": "React",
            "typescript": "TypeScript",
            "postgresql": "PostgreSQL",
            "postgres": "PostgreSQL",
            "supabase": "Supabase",
            "tailwind": "Tailwind CSS",
            "docker": "Docker",
            "sqlite": "SQLite",
            "git": "Git",
        }
        detected = []
        lower = safe_text.lower()
        for k, v in keywords.items():
            if k in lower and v not in detected:
                detected.append(v)

        return AIExtractionSchema(
            stack_tecnologico=detected if detected else ["Arquitectura de Software", "Full Stack"],
            resumen_profesional="Proyecto tecnológico validado mediante análisis heurístico de dependencias y fuentes estructurales.",
        )


llm_service = LLMAdapterService()