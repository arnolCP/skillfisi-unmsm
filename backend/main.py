from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import (
    auth_profiles,
    llm_extraction,
    projects,
    teacher_reviews,
    public_portfolio,
)

app = FastAPI(
    title="SkillFISI API - UNMSM",
    description="API REST para Gestión de Portafolios Académicos, Extracción IA, Validación Docente y Portafolio Público (FISI - UNMSM)",
    version="2.1.0",
)

# Configuración CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. Módulo 3.1 - Autenticación y Perfiles
app.include_router(auth_profiles.router)

# 2. Módulo 3.2 - Registro de Proyectos y Evidencias
app.include_router(projects.router)

# 3. Módulo 3.3 - Extracción con IA y Métricas de Caché (Erick)
app.include_router(
    llm_extraction.router,
    prefix="/api/v1/llm",
    tags=["Módulo 3.3 - Extracción con IA"],
)

# 4. Módulo 3.4 / HU07 y HU10 - Bandeja, Revisión Docente y Sello Oficial (Arnol)
app.include_router(teacher_reviews.router)

# 5. Módulo 3.5 / HU11 - Portafolio Profesional Público y Ley N.° 29733 (Arnol)
app.include_router(public_portfolio.router)

@app.get("/", tags=["Health Check"])
def health_check():
    return {
        "status": "online",
        "system": "SkillFISI Backend API",
        "module_3_1": "active",
        "module_3_2": "active",
        "module_3_3": "active",
        "module_3_4": "active",
        "module_3_5": "active",
    }