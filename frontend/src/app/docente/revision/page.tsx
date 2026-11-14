'use client';

import { useState, useEffect } from 'react';

interface PendingProject {
  id: string;
  title: string;
  course_name: string;
  student_email: string;
  github_url: string | null;
  professional_summary: string;
  tech_stack: string[];
  submitted_at: string;
}

export default function DocenteRevisionPage() {
  const [projects, setProjects] = useState<PendingProject[]>([]);
  const [selectedProject, setSelectedProject] = useState<PendingProject | null>(null);
  const [feedback, setFeedback] = useState('');
  const [activeSeconds, setActiveSeconds] = useState(0);
  const [timerRunning, setTimerRunning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  // 1. Cargar proyectos pendientes del curso del docente
  useEffect(() => {
    fetchPendingProjects();
  }, []);

  const fetchPendingProjects = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_URL}/api/v1/reviews/pending`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('No se pudo cargar la bandeja docente.');
      const data = await res.json();
      setProjects(data.projects);
    } catch {
      setStatusMessage({ type: 'error', text: 'No se pudo cargar la bandeja docente.' });
    } finally {
      setLoading(false);
    }
  };

  // 2. Control del cronómetro visual de revisión (SLA <= 5 min / 300 s)
  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (timerRunning) {
      interval = setInterval(() => {
        setActiveSeconds((prev) => prev + 1);
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [timerRunning]);

  // 3. Apertura de revisión y disparo de telemetría (/open)
  const handleOpenProject = async (project: PendingProject) => {
    if (actionLoading) return;
    setActionLoading(true);
    setStatusMessage(null);

    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_URL}/api/v1/reviews/${project.id}/open`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('No se pudo iniciar la revisión.');
      const data = await res.json();
      const elapsed = Math.floor((Date.now() - Date.parse(data.opened_by_teacher_at)) / 1000);
      setSelectedProject(project);
      setFeedback('');
      setActiveSeconds(Math.max(0, elapsed));
      setTimerRunning(true);
    } catch {
      setStatusMessage({ type: 'error', text: 'No se pudo iniciar la revisión.' });
    } finally {
      setActionLoading(false);
    }
  };

  // 4. Emisión de dictamen: Validar u Observar
  const handleDecision = async (decision: 'Validado' | 'Observado') => {
    if (!selectedProject) return;
    if (decision === 'Observado' && feedback.trim().length < 5) {
      setStatusMessage({ type: 'error', text: 'Ingrese un motivo de al menos cinco caracteres.' });
      return;
    }

    setActionLoading(true);

    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_URL}/api/v1/reviews/${selectedProject.id}/decision`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          decision,
          teacher_feedback: feedback,
        }),
      });

      if (!res.ok) {
        throw new Error('Error al registrar la decisión');
      }
      setTimerRunning(false);

      setStatusMessage({
        type: 'success',
        text: `Proyecto ${decision === 'Validado' ? 'acreditado exitosamente' : 'marcado como observado'}.`,
      });

      // Retirar el proyecto de la lista activa
      setProjects((prev) => prev.filter((p) => p.id !== selectedProject.id));
      setSelectedProject(null);
    } catch (err: any) {
      setStatusMessage({ type: 'error', text: err.message || 'No se pudo guardar la decisión' });
    } finally {
      setActionLoading(false);
    }
  };

  // Formato mm:ss para el cronómetro
  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="min-h-screen bg-slate-50 py-8 px-4 sm:px-6 lg:px-8">
      <div className="max-w-6xl mx-auto">
        {/* Cabecera */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between mb-8 pb-4 border-b border-slate-200">
          <div>
            <h1 className="text-2xl font-bold text-slate-800">Bandeja de Validación Docente</h1>
            <p className="text-sm text-slate-500 mt-1">Acreditación ágil de portafolios técnicos (SLA objetivo: &le; 5 minutos)</p>
          </div>
          <div className="mt-4 md:mt-0 flex items-center space-x-3">
            <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-blue-100 text-blue-800">
              {projects.length} {projects.length === 1 ? 'pendiente' : 'pendientes'}
            </span>
          </div>
        </div>

        {statusMessage && (
          <div
            className={`mb-6 p-4 rounded-lg text-sm ${
              statusMessage.type === 'success'
                ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                : 'bg-red-50 text-red-800 border border-red-200'
            }`}
          >
            {statusMessage.text}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Columna Izquierda: Listado de Proyectos */}
          <div className="lg:col-span-5 space-y-4">
            <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wider">
              Proyectos por Validar
            </h2>

            {loading ? (
              <div className="p-8 text-center text-sm text-slate-500 bg-white rounded-xl border border-slate-200">
                Cargando bandeja docente...
              </div>
            ) : projects.length === 0 ? (
              <div className="p-8 text-center text-sm text-slate-500 bg-white rounded-xl border border-slate-200">
                No hay proyectos pendientes de revisión en este momento.
              </div>
            ) : (
              projects.map((p) => (
                <div
                  key={p.id}
                  onClick={() => handleOpenProject(p)}
                  className={`p-5 bg-white rounded-xl border cursor-pointer transition-all duration-150 ${
                    selectedProject?.id === p.id
                      ? 'border-blue-600 ring-2 ring-blue-100 shadow-sm'
                      : 'border-slate-200 hover:border-slate-300 hover:shadow-xs'
                  }`}
                >
                  <div className="flex justify-between items-start mb-2">
                    <span className="text-xs font-medium text-blue-700 bg-blue-50 px-2.5 py-0.5 rounded">
                      {p.course_name}
                    </span>
                    <span className="text-xs text-slate-400">
                      {new Date(p.submitted_at).toLocaleDateString('es-PE')}
                    </span>
                  </div>
                  <h3 className="text-sm font-bold text-slate-800 mb-1">{p.title}</h3>
                  <p className="text-xs text-slate-500 mb-3">Estudiante: {p.student_email}</p>
                  
                  <div className="flex flex-wrap gap-1">
                    {p.tech_stack.slice(0, 4).map((tech, i) => (
                      <span key={i} className="text-[10px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded">
                        {tech}
                      </span>
                    ))}
                    {p.tech_stack.length > 4 && (
                      <span className="text-[10px] bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded">
                        +{p.tech_stack.length - 4}
                      </span>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Columna Derecha: Panel de Inspección y Dictamen */}
          <div className="lg:col-span-7">
            {selectedProject ? (
              <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-6">
                {/* Cabecera del Panel con Cronómetro SLA */}
                <div className="flex items-center justify-between pb-4 border-b border-slate-100">
                  <div>
                    <span className="text-xs text-slate-400 uppercase font-semibold">Inspección de Evidencias</span>
                    <h2 className="text-base font-bold text-slate-800">{selectedProject.title}</h2>
                  </div>
                  <div className="flex items-center space-x-2">
                    <span className="text-xs font-semibold text-slate-500">Tiempo activo:</span>
                    <span
                      className={`font-mono text-sm font-bold px-2.5 py-1 rounded-md ${
                        activeSeconds > 300
                          ? 'bg-red-100 text-red-700'
                          : activeSeconds > 240
                          ? 'bg-amber-100 text-amber-700'
                          : 'bg-emerald-100 text-emerald-700'
                      }`}
                    >
                      {formatTime(activeSeconds)}
                    </span>
                  </div>
                </div>

                {/* Enlace al Repositorio */}
                <div>
                  <label className="block text-xs font-semibold text-slate-600 uppercase mb-1">
                    Evidencia Técnica Principal (GitHub)
                  </label>
                  <a
                    href={selectedProject.github_url ?? undefined}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center text-xs font-medium text-blue-700 hover:text-blue-800 hover:underline"
                  >
                    <span>{selectedProject.github_url ?? 'Sin repositorio adjunto'}</span>
                    <svg className="w-3.5 h-3.5 ml-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                    </svg>
                  </a>
                </div>

                {/* Resumen Ejecutivo del LLM */}
                <div>
                  <label className="block text-xs font-semibold text-slate-600 uppercase mb-1">
                    Resumen Ejecutivo (Extraído por LLM)
                  </label>
                  <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs leading-relaxed text-slate-700">
                    {selectedProject.professional_summary}
                  </div>
                </div>

                {/* Stack Tecnológico Identificado */}
                <div>
                  <label className="block text-xs font-semibold text-slate-600 uppercase mb-2">
                    Stack Tecnológico Detectado
                  </label>
                  <div className="flex flex-wrap gap-1.5">
                    {selectedProject.tech_stack.map((tech, idx) => (
                      <span
                        key={idx}
                        className="px-2.5 py-1 bg-blue-50 text-blue-700 border border-blue-200 rounded-md text-xs font-medium"
                      >
                        {tech}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Caja de Observaciones Docente */}
                <div>
                  <label className="block text-xs font-semibold text-slate-600 uppercase mb-1">
                    Observaciones / Retroalimentación (Opcional para validar, obligatorio para observar)
                  </label>
                  <textarea
                    rows={3}
                    placeholder="Escriba comentarios para el estudiante..."
                    value={feedback}
                    onChange={(e) => setFeedback(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-xs focus:ring-2 focus:ring-blue-600 focus:outline-none text-slate-800"
                  />
                </div>

                {/* Botones de Acción en 1 Clic */}
                <div className="flex items-center justify-end space-x-3 pt-4 border-t border-slate-100">
                  <button
                    type="button"
                    disabled={actionLoading}
                    onClick={() => handleDecision('Observado')}
                    className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white font-medium rounded-lg text-xs transition-colors disabled:opacity-50"
                  >
                    {actionLoading ? 'Procesando...' : 'Observar Proyecto'}
                  </button>

                  <button
                    type="button"
                    disabled={actionLoading}
                    onClick={() => handleDecision('Validado')}
                    className="px-5 py-2 bg-emerald-600 hover:bg-emerald-700 text-white font-medium rounded-lg text-xs transition-colors disabled:opacity-50"
                  >
                    {actionLoading ? 'Procesando...' : 'Validar Proyecto'}
                  </button>
                </div>
              </div>
            ) : (
              <div className="h-full flex flex-col items-center justify-center p-12 bg-white rounded-xl border border-dashed border-slate-300 text-center">
                <svg className="w-12 h-12 text-slate-300 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <p className="text-sm font-semibold text-slate-600">Ningún proyecto seleccionado</p>
                <p className="text-xs text-slate-400 mt-1 max-w-xs">
                  Seleccione un proyecto de la lista de la izquierda para abrir la inspección de evidencias e iniciar el cronómetro.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
