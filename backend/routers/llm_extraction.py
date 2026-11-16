from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from services.llm_service import llm_service

router = APIRouter()


class EvidenceExtractionRequest(BaseModel):
    project_id: Optional[str] = None
    extracted_evidence_text: str = Field(..., min_length=10)


class ExtractionResponse(BaseModel):
    project_id: Optional[str] = None
    stack_tecnologico: List[str]
    stack_categorizado: Dict[str, List[str]]
    resumen_profesional: str
    cached: bool
    evidence_hash: str


class CategorizeRequest(BaseModel):
    technologies: List[str] = Field(..., min_length=1)


class CategorizeResponse(BaseModel):
    total_technologies: int
    categorias: Dict[str, List[str]]


@router.post("/extract", response_model=ExtractionResponse)
def extract_project_technologies(payload: EvidenceExtractionRequest):
    try:
        extraction_result = llm_service.extract_skills_and_summary(
            payload.extracted_evidence_text
        )
        data = extraction_result["data"]
        stack_cat = data.get("stack_categorizado") or llm_service.categorize_technologies(
            data["stack_tecnologico"]
        )
        return ExtractionResponse(
            project_id=payload.project_id,
            stack_tecnologico=data["stack_tecnologico"],
            stack_categorizado=stack_cat,
            resumen_profesional=data["resumen_profesional"],
            cached=extraction_result["cached"],
            evidence_hash=extraction_result["hash"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en procesamiento LLM: {str(e)}")


@router.post("/categorize", response_model=CategorizeResponse)
def categorize_validated_stack(payload: CategorizeRequest):
    """Agrupa tecnologías validadas en Lenguajes, Frameworks & Librerías, Bases de Datos y Cloud & DevOps."""
    categorias = llm_service.categorize_technologies(payload.technologies)
    total = sum(len(items) for items in categorias.values())
    return CategorizeResponse(
        total_technologies=total,
        categorias=categorias,
    )


@router.get("/cache/metrics")
def get_llm_cache_metrics() -> Dict[str, Any]:
    """Retorna telemetría del caché SHA-256 (hits, misses y tasa de aciertos)."""
    return llm_service.get_cache_metrics()