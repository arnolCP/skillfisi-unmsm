from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from services.llm_service import llm_adapter, AIExtractionSchema  # <-- Sin "backend." al inicio

router = APIRouter(
    prefix="/api/v1/llm",
    tags=["Módulo 3.3 - Extracción con IA (LLM)"]
)

class EvidenceExtractionRequest(BaseModel):
    project_id: str | None = Field(
        default=None,
        description="UUID opcional del proyecto registrado en estado Borrador."
    )
    extracted_evidence_text: str = Field(
        ...,
        min_length=10,
        description="Texto limpio preprocesado por el módulo 3.2 (GitHub, PDF o Notebook)."
    )

@router.post(
    "/extract",
    response_model=AIExtractionSchema,
    status_code=status.HTTP_200_OK,
    summary="Extrae stack tecnológico y resumen profesional mediante LLM"
)
async def extract_project_technologies(payload: EvidenceExtractionRequest) -> AIExtractionSchema:
    try:
        result = llm_adapter.extract_skills_and_summary(payload.extracted_evidence_text)
        return result
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al procesar la evidencia con el motor LLM: {str(e)}"
        )