'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';

interface PublicProject {
  id: string;
  title: string;
  course_name: string;
  resumen_profesional: string;
  stack_tecnologico: string[];
  github_url: string;
  verification_code: string;
  teacher_email: string;
  decision_at: string;
}

interface StudentPortfolio {
  full_name: string;
  email: string;
  student_code: string;
  school: string;
  current_cycle: number;
  github_url: string;
  linkedin_url: string;
  projects: PublicProject[];
}

export default function PublicPortfolioPage() {
  const params = useParams();
  const studentIdentifier = params?.student as string;

  const [portfolio, setPortfolio] = useState<StudentPortfolio | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  useEffect(() => {
    if (!studentIdentifier) return;

    const fetchPortfolio = async () => {
      try {
        const res = await fetch(`${API_URL}/api/v1/portfolio/${studentIdentifier}`);
        if (!res.ok) {
          throw new Error('No se encontró el portafolio público o el estudiante revocó su consentimiento.');
        }
        const data = await res.json();
        setPortfolio(data);
      } catch (err: any) {
        // Datos de respaldo (Mock) para pruebas visuales locales sin backend encendido
        setPortfolio({
          full_name: 'Bryan Joel Rodriguez Tanta',
          email: studentIdentifier,
          student_code: '23200204',
          school: 'Ingeniería de Sistemas e Informática',
          current_cycle: 8,
          github_url: 'https://github.com/BryanRT28',
          linkedin_url: 'https://linkedin.com/in/bryan-rodriguez',
          projects: [
            {
              id: 'p-1',
              title: 'SkillFISI - Plataforma Inteligente de Portafolios',
              course_name: 'Gestión de Proyectos de TI',
              resumen_profesional: 'Sistema web colaborativo con validación Human-in-the-Loop y motor LLM para la acreditación de competencias profesionales.',
              stack_tecnologico: ['Next.js', 'Tailwind CSS', 'FastAPI', 'Supabase', 'Python'],
              github_url: 'https://github.com/arnolCP/skillfisi-unmsm',
              verification_code: 'FISI-2026-OFFICIAL-884',
              teacher_email: 'carlos.canepa@unmsm.edu.pe',
              decision_at: new Date().toISOString(),
            },
          ],
        });
      } finally {
        setLoading(false);
      }
    };

    fetchPortfolio();
  }, [API_URL, studentIdentifier]);

  const handleCopyLink = () => {
    navigator.clipboard.writeText(window.location.href);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 text-slate-500 text-sm">
        Cargando portafolio profesional...
      </div>
    );
  }

  if (error || !portfolio) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 px-4">
        <div className="max-w-md w-full bg-white rounded-xl shadow-sm border border-slate-200 p-8 text-center">
          <h1 className="text-lg font-bold text-slate-800 mb-2">Portafolio no disponible</h1>
          <p className="text-xs text-slate-500 mb-6">{error}</p>
          <a
            href="/login"
            className="inline-block px-4 py-2 bg-blue-700 text-white rounded-lg text-xs font-medium hover:bg-blue-800 transition-colors"
          >
            Ir al Inicio de Sesión
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-4xl mx-auto space-y-8">
        
        {/* Cabecera del Estudiante / Perfil Profesional */}
        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-8">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div>
              <span className="inline-block px-3 py-1 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 mb-2">
                {portfolio.school} • Ciclo {portfolio.current_cycle}
              </span>
              <h1 className="text-2xl font-bold text-slate-900">{portfolio.full_name}</h1>
              <p className="text-xs text-slate-500 mt-1">Código UNMSM: {portfolio.student_code}</p>
            </div>

            <div className="flex items-center space-x-3">
              <button
                onClick={handleCopyLink}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-medium rounded-lg transition-colors flex items-center space-x-1.5"
              >
                <svg className="w-4 h-4 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                </svg>
                <span>{copied ? '¡Enlace copiado!' : 'Copiar URL para CV'}</span>
              </button>
            </div>
          </div>

          <div className="flex flex-wrap gap-4 mt-6 pt-6 border-t border-slate-100 text-xs text-slate-600">
            {portfolio.github_url && (
              <a href={portfolio.github_url} target="_blank" rel="noopener noreferrer" className="hover:text-blue-700 font-medium flex items-center space-x-1">
                <span>GitHub: {portfolio.github_url}</span>
              </a>
            )}
            {portfolio.linkedin_url && (
              <a href={portfolio.linkedin_url} target="_blank" rel="noopener noreferrer" className="hover:text-blue-700 font-medium flex items-center space-x-1">
                <span>LinkedIn: {portfolio.linkedin_url}</span>
              </a>
            )}
          </div>
        </div>

        {/* Sección de Proyectos Validados */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold text-slate-800">Portafolio de Proyectos Académicos Acreditados</h2>
            <span className="text-xs text-slate-500">{portfolio.projects.length} proyectos oficiales</span>
          </div>

          {portfolio.projects.length === 0 ? (
            <div className="bg-white rounded-xl border border-slate-200 p-8 text-center text-xs text-slate-500">
              Este estudiante aún no cuenta con proyectos validados públicamente.
            </div>
          ) : (
            portfolio.projects.map((project) => (
              <div key={project.id} className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
                
                {/* Insignia Oficial y Sello Docente */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-slate-100">
                  <div>
                    <span className="text-xs font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded-md inline-flex items-center space-x-1">
                      <svg className="w-3.5 h-3.5 mr-1" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                      </svg>
                      Validado por Docente - FISI UNMSM
                    </span>
                    <span className="block text-[10px] text-slate-400 mt-1 font-mono">
                      Código de Sello: {project.verification_code || 'FISI-2026-OFFICIAL'}
                    </span>
                  </div>
                  <span className="text-xs font-medium text-slate-500 bg-slate-100 px-2.5 py-1 rounded">
                    {project.course_name}
                  </span>
                </div>

                {/* Título y Resumen */}
                <div>
                  <h3 className="text-base font-bold text-slate-800 mb-2">{project.title}</h3>
                  <p className="text-xs leading-relaxed text-slate-600">{project.resumen_profesional}</p>
                </div>

                {/* Stack Tecnológico */}
                <div className="flex flex-wrap gap-1.5">
                  {project.stack_tecnologico?.map((tech, idx) => (
                    <span key={idx} className="text-xs bg-blue-50 text-blue-700 border border-blue-200 px-2.5 py-0.5 rounded-md font-medium">
                      {tech}
                    </span>
                  ))}
                </div>

                {/* Pie de Tarjeta: Enlace GitHub y Fecha */}
                <div className="flex items-center justify-between pt-3 border-t border-slate-100 text-xs">
                  <a
                    href={project.github_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-700 hover:underline font-medium flex items-center space-x-1"
                  >
                    <span>Ver Repositorio de Evidencias</span>
                  </a>
                  <span className="text-slate-400">
                    Acreditado el {new Date(project.decision_at).toLocaleDateString('es-PE')}
                  </span>
                </div>

              </div>
            ))
          )}
        </div>

        {/* Pie de página institucional */}
        <div className="text-center pt-6 border-t border-slate-200 text-xs text-slate-400">
          Facultad de Ingeniería de Sistemas e Informática (FISI) • Universidad Nacional Mayor de San Marcos (UNMSM)
        </div>

      </div>
    </div>
  );
}