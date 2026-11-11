"use client";

import React, { useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function NuevoProyectoPage() {
  // Estado Paso 1: Registro en Borrador (HU03)
  const [title, setTitle] = useState("");
  const [courseName, setCourseName] = useState("Gestión de Proyectos de TI");
  const [cycle, setCycle] = useState("8vo Ciclo");
  const [studentEmail, setStudentEmail] = useState("");
  const [teacherEmail, setTeacherEmail] = useState("");

  // Estado Paso 2: Carga de Evidencias e IA (HU04 / HU05)
  const [projectId, setProjectId] = useState<string | null>(null);
  const [projectStatus, setProjectStatus] = useState<string>("Sin crear");
  const [githubUrl, setGithubUrl] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [extractedText, setExtractedText] = useState("");
  const [charCount, setCharCount] = useState<number>(0);

  // Estado Paso 3: Edición Human-in-the-Loop y Ley N.° 29733 (HU06)
  const [techStack, setTechStack] = useState<string[]>([]);
  const [newTechInput, setNewTechInput] = useState("");
  const [professionalSummary, setProfessionalSummary] = useState("");
  const [consentLaw29733, setConsentLaw29733] = useState(false);

  // Mensajes de interfaz
  const [statusMsg, setStatusMsg] = useState<string>("");
  const [errorMsg, setErrorMsg] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);

  // Paso 1: Crear Proyecto en Borrador
  const handleCreateDraft = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg("");
    setStatusMsg("");

    if (!studentEmail.endsWith("@unmsm.edu.pe") || !teacherEmail.endsWith("@unmsm.edu.pe")) {
      setErrorMsg("Tanto el correo del estudiante como el del docente deben terminar en @unmsm.edu.pe");
      return;
    }

    setLoading(true);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/projects/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          course_name: courseName,
          cycle,
          student_email: studentEmail,
          teacher_email: teacherEmail,
        }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "Error al registrar el proyecto");

      setProjectId(data.project.id);
      setProjectStatus(data.project.status);
      setStatusMsg(`Paso 1 completado: Proyecto creado en estado '${data.project.status}'.`);
    } catch (err: any) {
      setErrorMsg(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Paso 2: Extraer Evidencias y Procesar con IA
  const handleUploadEvidencesAndExtractIA = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectId) return;
    setErrorMsg("");
    setStatusMsg("");
    setLoading(true);

    try {
      const formData = new FormData();
      if (githubUrl.trim()) formData.append("github_url", githubUrl.trim());
      if (selectedFile) formData.append("evidence_file", selectedFile);

      const evResp = await fetch(`${API_BASE}/api/v1/projects/${projectId}/evidences`, {
        method: "POST",
        body: formData,
      });
      const evData = await evResp.json();
      if (!evResp.ok) throw new Error(evData.detail || "Error al procesar evidencias");

      const fullText = evData.extracted_evidence_text || evData.extracted_text_preview || "";
      setExtractedText(fullText);
      setCharCount(evData.char_count);

      // Invocar al Motor LLM (Módulo 3.3) para sugerir stack y resumen
      const llmResp = await fetch(`${API_BASE}/api/v1/llm/extract`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: projectId,
          extracted_evidence_text: fullText,
        }),
      });
      const llmData = await llmResp.json();
      if (llmResp.ok) {
        setTechStack(llmData.stack_tecnologico || []);
        setProfessionalSummary(llmData.resumen_profesional || "");
        setStatusMsg(
          `Paso 2 completado: Evidencias extraídas (${evData.char_count} / 12,000 caracteres) y analizadas por IA. Revisa y edita antes de enviar.`
        );
      } else {
        setStatusMsg(
          `Evidencias extraídas (${evData.char_count} caracteres). Puedes completar el stack y resumen manualmente.`
        );
      }
    } catch (err: any) {
      setErrorMsg(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Funciones de edición Human-in-the-Loop (chips tecnológicos)
  const handleAddTech = () => {
    const clean = newTechInput.trim();
    if (clean && !techStack.includes(clean)) {
      setTechStack([...techStack, clean]);
      setNewTechInput("");
    }
  };

  const handleRemoveTech = (techToRemove: string) => {
    setTechStack(techStack.filter((t) => t !== techToRemove));
  };

  // Paso 3: Enviar a Revisión Docente (HU06)
  const handleSubmitForReview = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectId) return;
    setErrorMsg("");
    setStatusMsg("");

    if (!consentLaw29733) {
      setErrorMsg("Debes aceptar la cláusula de la Ley N.° 29733 para enviar el proyecto a revisión.");
      return;
    }

    setLoading(true);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/projects/${projectId}/submit-review`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tech_stack: techStack,
          professional_summary: professionalSummary,
          consent_law_29733: consentLaw29733,
        }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "Error al enviar el proyecto a revisión");

      setProjectStatus(data.project.status);
      setStatusMsg(
        `¡Flujo completado! Proyecto enviado al docente (${teacherEmail}) en estado '${data.project.status}'.`
      );
    } catch (err: any) {
      setErrorMsg(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="max-w-4xl mx-auto p-6 space-y-6 font-sans text-slate-800">
      <header className="border-b pb-4 flex flex-col md:flex-row md:items-center md:justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            SkillFISI – Registro, Extracción IA y Envío a Revisión
          </h1>
          <p className="text-sm text-slate-600">
            Módulos 3.2 y 3.3 (HU03, HU04 y HU06): Flujo Human-in-the-Loop bajo Ley N.° 29733.
          </p>
        </div>
        <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-blue-100 text-blue-800">
          Estado: {projectStatus}
        </span>
      </header>

      {errorMsg && (
        <div className="p-4 bg-red-50 border border-red-300 text-red-700 rounded-lg text-sm">
          {errorMsg}
        </div>
      )}

      {statusMsg && (
        <div className="p-4 bg-emerald-50 border border-emerald-300 text-emerald-800 rounded-lg text-sm">
          {statusMsg}
        </div>
      )}

      {/* PASO 1: HU03 */}
      <form
        onSubmit={handleCreateDraft}
        className="space-y-4 bg-white p-6 rounded-xl shadow-sm border border-slate-200"
      >
        <h2 className="text-lg font-semibold text-slate-800">
          1. Datos Académicos del Proyecto (HU03 – Estado Borrador)
        </h2>

        <div>
          <label className="block text-sm font-medium mb-1">Título del Proyecto</label>
          <input
            type="text"
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Ej. Sistema Inteligente de Portafolios Académicos SkillFISI"
            className="w-full border border-slate-300 rounded-lg p-2 text-sm"
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-1">Asignatura FISI</label>
            <select
              value={courseName}
              onChange={(e) => setCourseName(e.target.value)}
              className="w-full border border-slate-300 rounded-lg p-2 text-sm"
            >
              <option>Gestión de Proyectos de TI</option>
              <option>Ingeniería de Software</option>
              <option>Inteligencia Artificial</option>
              <option>Arquitectura de Software</option>
              <option>Desarrollo de Sistemas Móviles</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Ciclo Académico</label>
            <select
              value={cycle}
              onChange={(e) => setCycle(e.target.value)}
              className="w-full border border-slate-300 rounded-lg p-2 text-sm"
            >
              <option>7mo Ciclo</option>
              <option>8vo Ciclo</option>
              <option>9no Ciclo</option>
              <option>10mo Ciclo</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-1">Correo del Estudiante</label>
            <input
              type="email"
              required
              value={studentEmail}
              onChange={(e) => setStudentEmail(e.target.value)}
              placeholder="alumno@unmsm.edu.pe"
              className="w-full border border-slate-300 rounded-lg p-2 text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Correo del Docente Titular</label>
            <input
              type="email"
              required
              value={teacherEmail}
              onChange={(e) => setTeacherEmail(e.target.value)}
              placeholder="docente@unmsm.edu.pe"
              className="w-full border border-slate-300 rounded-lg p-2 text-sm"
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={loading}
          className="bg-blue-700 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-800 disabled:opacity-50"
        >
          {loading ? "Guardando..." : "Guardar Proyecto en Borrador"}
        </button>
      </form>

      {/* PASO 2: HU04 + HU05 */}
      {projectId && (
        <form
          onSubmit={handleUploadEvidencesAndExtractIA}
          className="space-y-4 bg-white p-6 rounded-xl shadow-sm border border-slate-200"
        >
          <h2 className="text-lg font-semibold text-slate-800">
            2. Ingesta de Evidencias y Extracción con IA (HU04 + HU05)
          </h2>

          <div>
            <label className="block text-sm font-medium mb-1">
              URL de Repositorio Público en GitHub
            </label>
            <input
              type="url"
              value={githubUrl}
              onChange={(e) => setGithubUrl(e.target.value)}
              placeholder="https://github.com/arnolCP/skillfisi-unmsm"
              className="w-full border border-slate-300 rounded-lg p-2 text-sm"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">
              Reporte Técnico (.pdf) o Notebook (.ipynb)
            </label>
            <input
              type="file"
              accept=".pdf,.ipynb"
              onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
              className="w-full text-sm"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="bg-emerald-700 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-emerald-800 disabled:opacity-50"
          >
            {loading ? "Extrayendo y Analizando con IA..." : "Extraer Evidencias y Analizar con IA"}
          </button>

          {charCount > 0 && (
            <p className="text-xs text-slate-500">
              Texto técnico consolidado: <strong>{charCount}</strong> / 12,000 caracteres (Cuota protegida).
            </p>
          )}
        </form>
      )}

      {/* PASO 3: HU06 - EDICIÓN HUMAN-IN-THE-LOOP Y ENVÍO A REVISIÓN */}
      {projectId && (charCount > 0 || techStack.length > 0) && (
        <form
          onSubmit={handleSubmitForReview}
          className="space-y-5 bg-white p-6 rounded-xl shadow-sm border border-slate-200"
        >
          <h2 className="text-lg font-semibold text-slate-800">
            3. Revisión del Estudiante (Human-in-the-Loop) y Envío al Docente (HU06)
          </h2>

          <div>
            <label className="block text-sm font-medium mb-2">
              Stack Tecnológico Detectado (Puedes agregar o quitar etiquetas)
            </label>
            <div className="flex flex-wrap gap-2 mb-3">
              {techStack.map((tech) => (
                <span
                  key={tech}
                  className="inline-flex items-center gap-1.5 px-3 py-1 bg-slate-100 border border-slate-300 rounded-full text-xs font-medium text-slate-800"
                >
                  {tech}
                  <button
                    type="button"
                    onClick={() => handleRemoveTech(tech)}
                    className="text-red-600 hover:text-red-800 font-bold"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                value={newTechInput}
                onChange={(e) => setNewTechInput(e.target.value)}
                placeholder="Agregar tecnología (ej. Docker, PostgreSQL)"
                className="flex-1 border border-slate-300 rounded-lg p-2 text-sm"
              />
              <button
                type="button"
                onClick={handleAddTech}
                className="px-4 py-2 bg-slate-800 text-white rounded-lg text-xs font-medium hover:bg-slate-900"
              >
                + Agregar
              </button>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">
              Resumen Ejecutivo Profesional (Editable antes de enviar al docente)
            </label>
            <textarea
              rows={4}
              required
              value={professionalSummary}
              onChange={(e) => setProfessionalSummary(e.target.value)}
              className="w-full border border-slate-300 rounded-lg p-2.5 text-sm"
            />
          </div>

          <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg flex items-start gap-3">
            <input
              id="consent_law"
              type="checkbox"
              checked={consentLaw29733}
              onChange={(e) => setConsentLaw29733(e.target.checked)}
              className="mt-1 h-4 w-4 text-blue-700 border-slate-300 rounded"
            />
            <label htmlFor="consent_law" className="text-xs text-slate-700 leading-relaxed">
              <strong>Consentimiento Informado (Ley N.° 29733 – Protección de Datos Personales):</strong>{" "}
              Autorizo de manera libre, previa, expresa e inequívoca a la FISI - UNMSM el tratamiento y
              publicación académica de mi portafolio y evidencias técnicas una vez acreditadas por el docente titular.
            </label>
          </div>

          <button
            type="submit"
            disabled={loading || projectStatus === "En Revisión"}
            className="w-full py-2.5 bg-indigo-700 hover:bg-indigo-800 text-white font-semibold rounded-lg text-sm disabled:opacity-50"
          >
            {projectStatus === "En Revisión"
              ? "Proyecto Enviado a Revisión Docente ✓"
              : "Confirmar Edición y Enviar a Revisión Docente (HU06)"}
          </button>
        </form>
      )}
    </main>
  );
}