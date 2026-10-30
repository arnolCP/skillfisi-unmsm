"use client";

import React, { useState } from "react";

export default function NuevoProyectoPage() {
  const [title, setTitle] = useState("");
  const [courseName, setCourseName] = useState("Ingeniería de Software");
  const [cycle, setCycle] = useState("8.° Ciclo");
  const [studentEmail, setStudentEmail] = useState("");
  const [teacherEmail, setTeacherEmail] = useState("");
  const [githubUrl, setGithubUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      // Paso 1 (HU03): Registrar el proyecto en estado Borrador
      const createResp = await fetch("http://localhost:8000/api/v1/projects/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          course_name: courseName,
          cycle,
          semester: "2026-2",
          student_email: studentEmail,
          teacher_email: teacherEmail,
        }),
      });

      const createData = await createResp.json();
      if (!createResp.ok) {
        throw new Error(createData.detail || "Error al registrar el proyecto.");
      }

      const projectId = createData.project.id;

      // Paso 2 (HU04): Subir evidencias (GitHub + PDF/Notebook) y preprocesar texto para el LLM
      const formData = new FormData();
      formData.append("github_url", githubUrl);
      if (file) {
        formData.append("evidence_file", file);
      }

      const evidenceResp = await fetch(
        `http://localhost:8000/api/v1/projects/${projectId}/evidences`,
        {
          method: "POST",
          body: formData,
        }
      );

      const evidenceData = await evidenceResp.json();
      if (!evidenceResp.ok) {
        throw new Error(evidenceData.detail || "Error al validar las evidencias.");
      }

      setResult(evidenceData);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto p-6 bg-white shadow-md rounded-xl mt-8 border border-gray-200">
      <h1 className="text-2xl font-bold text-slate-900 mb-2">
        Registrar Nuevo Proyecto Académico (SkillFISI)
      </h1>
      <p className="text-sm text-slate-600 mb-6">
        Módulo 3.2 (HU03 - HU04): Registra tu proyecto de asignatura y adjunta tus evidencias
        para que la IA extraiga automáticamente el stack tecnológico.
      </p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-slate-700">
            Título del Proyecto
          </label>
          <input
            type="text"
            required
            placeholder="Ej. Sistema de Telemetría IoT o Plataforma Web MVC"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="mt-1 w-full rounded-lg border border-gray-300 p-2.5 text-sm"
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-slate-700">
              Asignatura de Especialidad (FISI)
            </label>
            <select
              value={courseName}
              onChange={(e) => setCourseName(e.target.value)}
              className="mt-1 w-full rounded-lg border border-gray-300 p-2.5 text-sm"
            >
              <option value="Ingeniería de Software">Ingeniería de Software</option>
              <option value="Taller de Proyectos">Taller de Proyectos</option>
              <option value="Desarrollo de Sistemas Web">Desarrollo de Sistemas Web</option>
              <option value="Inteligencia Artificial">Inteligencia Artificial</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700">
              Ciclo Académico
            </label>
            <select
              value={cycle}
              onChange={(e) => setCycle(e.target.value)}
              className="mt-1 w-full rounded-lg border border-gray-300 p-2.5 text-sm"
            >
              <option value="7.° Ciclo">7.° Ciclo</option>
              <option value="8.° Ciclo">8.° Ciclo</option>
              <option value="9.° Ciclo">9.° Ciclo</option>
              <option value="10.° Ciclo">10.° Ciclo</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-slate-700">
              Tu Correo Institucional (@unmsm.edu.pe)
            </label>
            <input
              type="email"
              required
              placeholder="alumno@unmsm.edu.pe"
              value={studentEmail}
              onChange={(e) => setStudentEmail(e.target.value)}
              className="mt-1 w-full rounded-lg border border-gray-300 p-2.5 text-sm"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700">
              Correo del Docente Validador (@unmsm.edu.pe)
            </label>
            <input
              type="email"
              required
              placeholder="docente@unmsm.edu.pe"
              value={teacherEmail}
              onChange={(e) => setTeacherEmail(e.target.value)}
              className="mt-1 w-full rounded-lg border border-gray-300 p-2.5 text-sm"
            />
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700">
            Enlace Público del Repositorio en GitHub (Obligatorio)
          </label>
          <input
            type="url"
            required
            placeholder="https://github.com/usuario/mi-proyecto-fisi"
            value={githubUrl}
            onChange={(e) => setGithubUrl(e.target.value)}
            className="mt-1 w-full rounded-lg border border-gray-300 p-2.5 text-sm"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700">
            Reporte Técnico (.pdf) o Notebook (.ipynb) (Opcional)
          </label>
          <input
            type="file"
            accept=".pdf,.ipynb"
            onChange={(e) => setFile(e.target.files ? e.target.files[0] : null)}
            className="mt-1 w-full text-sm text-slate-600"
          />
        </div>

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-blue-700 hover:bg-blue-800 text-white font-semibold py-2.5 px-4 rounded-lg transition"
        >
          {loading ? "Validando repositorio y extrayendo evidencias..." : "Registrar Proyecto y Extraer Evidencias"}
        </button>
      </form>

      {error && (
        <div className="mt-4 p-4 bg-red-50 border border-red-300 text-red-700 rounded-lg text-sm">
          <strong>Error:</strong> {error}
        </div>
      )}

      {result && (
        <div className="mt-6 p-4 bg-emerald-50 border border-emerald-300 rounded-lg text-sm text-slate-800">
          <h3 className="font-bold text-emerald-800 mb-1">¡Proyecto y Evidencias Procesadas!</h3>
          <p><strong>ID del Proyecto:</strong> {result.project_id}</p>
          <p><strong>Caracteres extraídos para el LLM:</strong> {result.characters_extracted} / {result.max_characters_allowed}</p>
          <pre className="mt-2 p-2 bg-white rounded border text-xs overflow-x-auto">
            {result.preview_for_llm}
          </pre>
        </div>
      )}
    </div>
  );
}