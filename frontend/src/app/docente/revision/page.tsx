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
  verification_code?: string;
}

export default function DocenteRevisionPage() {
  const [projects, setProjects] = useState<PendingProject[]>([]);
  const [selectedProject, setSelectedProject] = useState<PendingProject | null>(null);
  const [feedback, setFeedback] = useState('');
  const [newTag, setNewTag] = useState('');
  const [activeSeconds, setActiveSeconds] = useState(0);
  const [timerRunning, setTimerRunning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

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
      setProjects(data.projects || data);
    } catch {
      // Datos de respaldo (Mock) para pruebas visuales locales de la Bandeja Docente
      setProjects([
        {
          id: 'p-001',
          title: 'SkillFISI - Plataforma Inteligente de Portafolios',
          course_name: 'Gestión de Proyectos de TI',
          student_email: 'bryan.rodriguezt@unmsm.edu.pe',
          github_url: 'https://github.com/arnolCP/skillfisi-unmsm',
          professional_summary: 'Sistema web colaborativo con validación Human-in-the-Loop y motor LLM para la acreditación de competencias profesionales de estudiantes FISI.',
          tech_stack: ['Next.js', 'Tailwind CSS', 'FastAPI', 'Supabase', 'Python'],
          submitted_at: new Date().toISOString(),
        },
        {
          id: 'p-002',
          title: 'Sistema de Gestión Logística Aduanera',
          course_name: 'Arquitectura de Software',
          student_email: 'carlos.mendoza@unmsm.edu.pe',
          github_url: 'https://github.com/carlosm/logistica-slw',
          professional_summary: 'Módulo backend y frontend para control de inventarios de carga internacional con trazabilidad en tiempo real.',
          tech_stack: ['TypeScript', 'Node.js', 'PostgreSQL', 'Docker'],
          submitted_at: new Date().toISOString(),
        },
      ]);
      setStatusMessage(null); // Oculta el error rojo al activar el modo visual de pruebas
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (timerRunning) {
      interval = setInterval(() => {
        setActiveSeconds((prev) => prev + 1);
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [timerRunning]);

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
      
      if (res.ok) {
        const data = await res.json();
        const elapsed = Math.floor((Date.now() - Date.parse(data.opened_by_teacher_at)) / 1000);
        setActiveSeconds(Math.max(0, elapsed));
      } else {
        // Fallback local si la API no está activa
        setActiveSeconds(0);
      }

      setSelectedProject(project);
      setFeedback('');
      setNewTag('');
      setTimerRunning(true);
    } catch {
      // Modo de pruebas visuales locales sin backend encendido
      setSelectedProject(project);
      setFeedback('');
      setNewTag('');
      setActiveSeconds(0);
      setTimerRunning(true);
    } finally {
      setActionLoading(false);
    }
  };

  // HU09: Funciones para agregar y eliminar etiquetas tecnológicas de forma dinámica
  const handleAddTag = () => {
    if (!newTag.trim() || !selectedProject) return;
    if (selectedProject.tech_stack.includes(newTag.trim())) return;

    setSelectedProject({
      ...selectedProject,
      tech_stack: [...selectedProject.tech_stack, newTag.trim()],
    });
    setNewTag('');
  };

  const handleRemoveTag = (tagToRemove: string) => {
    if (!selectedProject) return;
    setSelectedProject({
      ...selectedProject,
      tech_stack: selectedProject.tech_stack.filter((t) => t !== tagToRemove),
    });
  };

  const handleDecision = async (decision: 'Validado' | 'Observado') => {
    if (!selectedProject) return;
    if (decision === 'Observado' && feedback.trim().length < 5) {
      setStatusMessage({ type: 'error', text: 'Ingrese un motivo de al menos cinco caracteres para observar.' });
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
          validated_technologies: selectedProject.tech_stack, // Envía el stack depurado por el docente (HU09)
        }),
      });

      if (!res.ok) {
        throw new Error('Error al registrar la decisión');
      }
      setTimerRunning(false);

      setStatusMessage({
        type: 'success',
        text: `Proyecto ${decision === 'Validado' ? 'acreditado con Sello Oficial' : 'marcado como observado'}.`,
      });

      setProjects((prev) => prev.filter((p) => p.id !== selectedProject.id));
      setSelectedProject(null);
    } catch (err: any) {
      setStatusMessage({ type: 'error', text: err.message || 'No se pudo guardar la decisión' });
    } finally {
      setActionLoading(false);
    }
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="min-h-screen bg-slate-50 py-8 px-4 sm:px-6 lg:px-8">
      <div className="max-w-6xl mx-auto">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between mb-8 pb-4 border-b border-slate-200">
          <div>
            <h1 className="text-2xl font-bold text-slate-800">Bandeja de Validación Docente</h1>
            <p className="text-sm text-slate-500 mt-1">Acreditación ágil, ajuste de etiquetas y Sello Oficial FISI (SLA: &le; 5 min)</p>
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
                    {p.tech_stack?.slice(0, 4).map((tech, i) => (
                      <span key={i} className="text-[10px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded">
                        {tech}
                      </span>
                    ))}
                  </div>
                </div>
              ))
            )}
          </div>

          <div className="lg:col-span-7">
            {selectedProject ? (
              <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-6">
                <div className="flex items-center justify-between pb-4 border-b border-slate-100">
                  <div>
                    <span className="text-xs text-slate-400 uppercase font-semibold">Inspección y Sello Docente</span>
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
                  </a>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-600 uppercase mb-1">
                    Resumen Ejecutivo (Extraído por LLM)
                  </label>
                  <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs leading-relaxed text-slate-700">
                    {selectedProject.professional_summary}
                  </div>
                </div>

                {/* HU09: Depuración y adición interactiva de etiquetas tecnológicas por el docente */}
                <div>
                  <label className="block text-xs font-semibold text-slate-600 uppercase mb-2">
                    Stack Tecnológico (Depuración Docente - HU09)
                  </label>
                  <div className="flex flex-wrap gap-1.5 mb-3">
                    {selectedProject.tech_stack.map((tech, idx) => (
                      <span
                        key={idx}
                        className="inline-flex items-center px-2.5 py-1 bg-blue-50 text-blue-700 border border-blue-200 rounded-md text-xs font-medium"
                      >
                        {tech}
                        <button
                          type="button"
                          onClick={() => handleRemoveTag(tech)}
                          className="ml-1.5 text-blue-400 hover:text-red-600 font-bold"
                          title="Eliminar etiqueta"
                        >
                          &times;
                        </button>
                      </span>
                    ))}
                  </div>

                  <div className="flex space-x-2">
                    <input
                      type="text"
                      placeholder="Añadir tecnología faltante..."
                      value={newTag}
                      onChange={(e) => setNewTag(e.target.value)}
                      className="px-3 py-1.5 border border-slate-300 rounded-lg text-xs w-full focus:outline-none focus:ring-2 focus:ring-blue-600 text-slate-800"
                    />
                    <button
                      type="button"
                      onClick={handleAddTag}
                      className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-medium transition-colors"
                    >
                      Agregar
                    </button>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-600 uppercase mb-1">
                    Observaciones / Retroalimentación (Obligatorio para observar)
                  </label>
                  <textarea
                    rows={3}
                    placeholder="Escriba comentarios para el estudiante..."
                    value={feedback}
                    onChange={(e) => setFeedback(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-xs focus:ring-2 focus:ring-blue-600 focus:outline-none text-slate-800"
                  />
                </div>

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
                    {actionLoading ? 'Procesando...' : 'Validar y Emitir Sello (HU10)'}
                  </button>
                </div>
              </div>
            ) : (
              <div className="h-full flex flex-col items-center justify-center p-12 bg-white rounded-xl border border-dashed border-slate-300 text-center">
                <p className="text-sm font-semibold text-slate-600">Ningún proyecto seleccionado</p>
                <p className="text-xs text-slate-400 mt-1 max-w-xs">
                  Seleccione un proyecto de la lista de la izquierda para iniciar la inspección docente y el cronómetro SLA.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}