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
    resumen_profesional: str
    cached: bool
    evidence_hash: str


@router.post("/extract", response_model=ExtractionResponse)
def extract_project_technologies(payload: EvidenceExtractionRequest):
    try:
        extraction_result = llm_service.extract_skills_and_summary(
            payload.extracted_evidence_text
        )
        data = extraction_result["data"]
        return ExtractionResponse(
            project_id=payload.project_id,
            stack_tecnologico=data["stack_tecnologico"],
            resumen_profesional=data["resumen_profesional"],
            cached=extraction_result["cached"],
            evidence_hash=extraction_result["hash"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en procesamiento LLM: {str(e)}")


@router.get("/cache/metrics")
def get_llm_cache_metrics() -> Dict[str, Any]:
    """Retorna telemetría del caché SHA-256 (hits, misses y tasa de aciertos)."""
    return llm_service.get_cache_metrics()