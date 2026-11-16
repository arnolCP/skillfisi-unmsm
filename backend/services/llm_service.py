import os
import hashlib
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


TAXONOMY_MAP: Dict[str, str] = {
    # Lenguajes de Programación
    "python": "Lenguajes de Programación",
    "py": "Lenguajes de Programación",
    "python3": "Lenguajes de Programación",
    "java": "Lenguajes de Programación",
    "javascript": "Lenguajes de Programación",
    "js": "Lenguajes de Programación",
    "typescript": "Lenguajes de Programación",
    "ts": "Lenguajes de Programación",
    "c++": "Lenguajes de Programación",
    "cpp": "Lenguajes de Programación",
    "c#": "Lenguajes de Programación",
    "csharp": "Lenguajes de Programación",
    "go": "Lenguajes de Programación",
    "golang": "Lenguajes de Programación",
    "rust": "Lenguajes de Programación",
    "kotlin": "Lenguajes de Programación",
    "swift": "Lenguajes de Programación",
    "php": "Lenguajes de Programación",
    "ruby": "Lenguajes de Programación",
    "sql": "Lenguajes de Programación",
    "r": "Lenguajes de Programación",
    # Frameworks y Librerías
    "fastapi": "Frameworks y Librerías",
    "flask": "Frameworks y Librerías",
    "django": "Frameworks y Librerías",
    "spring": "Frameworks y Librerías",
    "spring boot": "Frameworks y Librerías",
    "jpa": "Frameworks y Librerías",
    "hibernate": "Frameworks y Librerías",
    "next.js": "Frameworks y Librerías",
    "nextjs": "Frameworks y Librerías",
    "react": "Frameworks y Librerías",
    "react.js": "Frameworks y Librerías",
    "angular": "Frameworks y Librerías",
    "vue": "Frameworks y Librerías",
    "vue.js": "Frameworks y Librerías",
    "node.js": "Frameworks y Librerías",
    "nodejs": "Frameworks y Librerías",
    "express": "Frameworks y Librerías",
    "nestjs": "Frameworks y Librerías",
    "tailwind": "Frameworks y Librerías",
    "tailwind css": "Frameworks y Librerías",
    "bootstrap": "Frameworks y Librerías",
    "pydantic": "Frameworks y Librerías",
    "jetpack compose": "Frameworks y Librerías",
    # Bases de Datos
    "postgresql": "Bases de Datos",
    "postgres": "Bases de Datos",
    "mysql": "Bases de Datos",
    "mariadb": "Bases de Datos",
    "sqlite": "Bases de Datos",
    "mongodb": "Bases de Datos",
    "mongo": "Bases de Datos",
    "redis": "Bases de Datos",
    "oracle": "Bases de Datos",
    "sql server": "Bases de Datos",
    "firebase": "Bases de Datos",
    "firestore": "Bases de Datos",
    "supabase": "Bases de Datos",
    "dynamodb": "Bases de Datos",
    # Cloud y DevOps
    "docker": "Cloud y DevOps",
    "kubernetes": "Cloud y DevOps",
    "k8s": "Cloud y DevOps",
    "aws": "Cloud y DevOps",
    "amazon web services": "Cloud y DevOps",
    "gcp": "Cloud y DevOps",
    "google cloud": "Cloud y DevOps",
    "azure": "Cloud y DevOps",
    "github actions": "Cloud y DevOps",
    "gitlab ci": "Cloud y DevOps",
    "jenkins": "Cloud y DevOps",
    "terraform": "Cloud y DevOps",
    "linux": "Cloud y DevOps",
    "nginx": "Cloud y DevOps",
    "git": "Cloud y DevOps",
    "vercel": "Cloud y DevOps",
    "render": "Cloud y DevOps",
    # Ciencia de Datos / IA
    "pandas": "Ciencia de Datos / IA",
    "numpy": "Ciencia de Datos / IA",
    "scikit-learn": "Ciencia de Datos / IA",
    "sklearn": "Ciencia de Datos / IA",
    "tensorflow": "Ciencia de Datos / IA",
    "pytorch": "Ciencia de Datos / IA",
    "keras": "Ciencia de Datos / IA",
    "opencv": "Ciencia de Datos / IA",
    "langchain": "Ciencia de Datos / IA",
    "langgraph": "Ciencia de Datos / IA",
    "gemini": "Ciencia de Datos / IA",
    "openai": "Ciencia de Datos / IA",
    "jupyter": "Ciencia de Datos / IA",
    "matplotlib": "Ciencia de Datos / IA",
}


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
        self.model = os.getenv("LLM_MODEL", "gemini-2.0-flash")
        self.max_chars = 12000
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

    def categorize_technologies(self, technologies: List[str]) -> Dict[str, List[str]]:
            """
            Clasifica una lista de tecnologías en las 5 dimensiones curriculares
            para el Portafolio Público (Sprint 3) y Dashboard BI (Sprint 4).
            """
            categorized: Dict[str, List[str]] = {
                "Lenguajes de Programación": [],
                "Frameworks y Librerías": [],
                "Bases de Datos": [],
                "Cloud y DevOps": [],
                "Ciencia de Datos / IA": [],
            }

            for tech in technologies:
                clean_tech = tech.strip()
                if not clean_tech:
                    continue

                key = clean_tech.lower()
                category = TAXONOMY_MAP.get(key)

                if not category:
                    for map_key, map_cat in TAXONOMY_MAP.items():
                        if map_key in key:
                            category = map_cat
                            break

                if not category:
                    category = "Frameworks y Librerías"

                if clean_tech not in categorized[category]:
                    categorized[category].append(clean_tech)

            return categorized

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
        formatted_result["stack_categorizado"] = self.categorize_technologies(
            formatted_result["stack_tecnologico"]
        )

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
            model=self.model,
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
            stack_tecnologico=detected if detected else ["Python", "FastAPI"],
            resumen_profesional="Proyecto tecnológico validado mediante análisis heurístico de dependencias y fuentes estructurales.",
        )


llm_service = LLMAdapterService()