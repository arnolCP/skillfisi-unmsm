from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import projects
from routers import auth_profiles

app = FastAPI(
    title="SkillFISI API - UNMSM",
    description="Backend para gestión de portafolios académicos con IA y validación docente HITL",
    version="1.0.0",
)

# Permitir peticiones desde el Frontend en Next.js (localhost:3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Incluir el Módulo 3.2 desarrollado por Arnol Condori
app.include_router(projects.router)
app.include_router(auth_profiles.router)


@app.get("/")
def health_check():
    return {"status": "online", "system": "SkillFISI Backend API", "module_3_2": "active"}