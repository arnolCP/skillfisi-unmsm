from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import auth_profiles, projects, llm_extraction, teacher_reviews

app = FastAPI(
    title="SkillFISI API - UNMSM",
    description="API REST para Gestión de Portafolios Académicos, Extracción IA y Validación Docente (FISI - UNMSM)",
    version="1.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_profiles.router)
app.include_router(projects.router)
app.include_router(llm_extraction.router)
app.include_router(teacher_reviews.router)


@app.get("/", tags=["Monitoreo de Salud"])
def health_check():
    return {
        "status": "online",
        "system": "SkillFISI Backend API",
        "module_3_1": "active",
        "module_3_2": "active",
        "module_3_3": "active",
        "module_3_4": "active",
    }