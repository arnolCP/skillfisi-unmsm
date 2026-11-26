'use client';

import { useState, useEffect, useCallback } from 'react';

interface TechRankingItem {
  technology: string;
  category: string;
  count: number;
  percentage: number;
}

interface CourseSummaryItem {
  course_name: string;
  cycle: string;
  semester: string;
  validated_count: number;
  approval_rate: number;
  avg_review_seconds: number;
  top_technology: string;
}

interface DashboardAnalytics {
  total_registered_projects: number;
  total_validated_projects: number;
  teacher_approval_rate: number;
  avg_review_seconds: number;
  public_portfolio_rate: number;
  top_technologies: TechRankingItem[];
  courses_summary: CourseSummaryItem[];
}

const MOCK_COURSES_DATA: CourseSummaryItem[] = [
  {
    course_name: 'Gestión de Proyectos de TI',
    cycle: '8',
    semester: '2026-2',
    validated_count: 14,
    approval_rate: 93.3,
    avg_review_seconds: 142,
    top_technology: 'Next.js',
  },
  {
    course_name: 'Arquitectura de Software',
    cycle: '7',
    semester: '2026-2',
    validated_count: 12,
    approval_rate: 85.7,
    avg_review_seconds: 168,
    top_technology: 'FastAPI',
  },
  {
    course_name: 'Ingeniería de Software II',
    cycle: '6',
    semester: '2026-2',
    validated_count: 11,
    approval_rate: 91.7,
    avg_review_seconds: 155,
    top_technology: 'PostgreSQL',
  },
  {
    course_name: 'Inteligencia Artificial',
    cycle: '8',
    semester: '2026-1',
    validated_count: 9,
    approval_rate: 90.0,
    avg_review_seconds: 194,
    top_technology: 'Python',
  },
  {
    course_name: 'Desarrollo de Sistemas Móviles',
    cycle: '7',
    semester: '2026-1',
    validated_count: 8,
    approval_rate: 88.9,
    avg_review_seconds: 176,
    top_technology: 'Kotlin',
  },
];

const MOCK_TECH_RANKING: TechRankingItem[] = [
  { technology: 'Python', category: 'Lenguajes de Programación', count: 34, percentage: 63.0 },
  { technology: 'Next.js', category: 'Frameworks Web', count: 29, percentage: 53.7 },
  { technology: 'FastAPI', category: 'Frameworks Web', count: 25, percentage: 46.3 },
  { technology: 'PostgreSQL', category: 'Bases de Datos', count: 23, percentage: 42.6 },
  { technology: 'TypeScript', category: 'Lenguajes de Programación', count: 21, percentage: 38.9 },
  { technology: 'Docker', category: 'Cloud y DevOps', count: 16, percentage: 29.6 },
];

export default function AutoridadDashboardPage() {
  const [courseFilter, setCourseFilter] = useState('');
  const [cycleFilter, setCycleFilter] = useState('');
  const [semesterFilter, setSemesterFilter] = useState('');

  const [analytics, setAnalytics] = useState<DashboardAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [usingFallback, setUsingFallback] = useState(false);

  const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  const buildFallbackData = useCallback((): DashboardAnalytics => {
    const filteredCourses = MOCK_COURSES_DATA.filter((c) => {
      const matchCourse = !courseFilter || c.course_name === courseFilter;
      const matchCycle = !cycleFilter || c.cycle === cycleFilter;
      const matchSemester = !semesterFilter || c.semester === semesterFilter;
      return matchCourse && matchCycle && matchSemester;
    });

    const totalValidated = filteredCourses.reduce((acc, c) => acc + c.validated_count, 0);
    const totalRegistered = totalValidated > 0 ? Math.ceil(totalValidated / 0.9) : 0;
    const avgApproval =
      filteredCourses.length > 0
        ? Number(
            (
              filteredCourses.reduce((acc, c) => acc + c.approval_rate, 0) / filteredCourses.length
            ).toFixed(1)
          )
        : 0;
    const avgSla =
      filteredCourses.length > 0
        ? Math.round(
            filteredCourses.reduce((acc, c) => acc + c.avg_review_seconds, 0) /
              filteredCourses.length
          )
        : 0;

    const scaleFactor = totalValidated > 0 ? totalValidated / 54 : 0;
    const scaledTech = MOCK_TECH_RANKING.map((item) => {
      const scaledCount = Math.max(1, Math.round(item.count * scaleFactor));
      const pct = totalValidated > 0 ? Number(((scaledCount / totalValidated) * 100).toFixed(1)) : 0;
      return {
        ...item,
        count: totalValidated === 0 ? 0 : scaledCount,
        percentage: Math.min(100, pct),
      };
    }).filter((t) => t.count > 0);

    return {
      total_registered_projects: totalRegistered,
      total_validated_projects: totalValidated,
      teacher_approval_rate: avgApproval,
      avg_review_seconds: avgSla,
      public_portfolio_rate: totalValidated > 0 ? 87.5 : 0,
      top_technologies: scaledTech,
      courses_summary: filteredCourses,
    };
  }, [courseFilter, cycleFilter, semesterFilter]);

  const fetchDashboardData = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (courseFilter) params.append('course_name', courseFilter);
      if (cycleFilter) params.append('cycle', cycleFilter);
      if (semesterFilter) params.append('semester', semesterFilter);

      const queryString = params.toString();
      const url = `${API_URL}/api/v1/analytics/dashboard${queryString ? `?${queryString}` : ''}`;

      const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
      const res = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });

      if (!res.ok) throw new Error('Backend no disponible');

      const data = await res.json();
      setAnalytics({
        total_registered_projects: data.total_registered_projects ?? data.total_validated_projects ?? 0,
        total_validated_projects: data.total_validated_projects ?? 0,
        teacher_approval_rate: data.teacher_approval_rate ?? 0,
        avg_review_seconds: data.avg_review_seconds ?? 0,
        public_portfolio_rate: data.public_portfolio_rate ?? 85.0,
        top_technologies: data.top_technologies ?? [],
        courses_summary: data.courses_summary ?? [],
      });
      setUsingFallback(false);
    } catch {
      setAnalytics(buildFallbackData());
      setUsingFallback(true);
    } finally {
      setLoading(false);
    }
  }, [API_URL, courseFilter, cycleFilter, semesterFilter, buildFallbackData]);

  useEffect(() => {
    fetchDashboardData();
  }, [fetchDashboardData]);

  const handleResetFilters = () => {
    setCourseFilter('');
    setCycleFilter('');
    setSemesterFilter('');
  };

  return (
    <div className="min-h-screen bg-slate-50 py-8 px-4 sm:px-6 lg:px-8">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Cabecera Institucional */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between pb-4 border-b border-slate-200 gap-4">
          <div>
            <span className="inline-block px-2.5 py-0.5 rounded text-xs font-semibold bg-blue-100 text-blue-800 mb-1">
              Decanato y Dirección de Escuela • FISI - UNMSM
            </span>
            <h1 className="text-2xl font-bold text-slate-900">
              Panel Analítico y Gerencial de Competencias TI
            </h1>
            <p className="text-xs text-slate-500 mt-1">
              Consolidado curricular de proyectos acreditados (estado Validado) para actualización de sílabos (HU12 / HU13)
            </p>
          </div>

          <div className="flex items-center space-x-2">
            {usingFallback && (
              <span className="text-[11px] font-medium px-2.5 py-1 rounded-md bg-amber-50 text-amber-700 border border-amber-200">
                Vista previa analítica (Datos simulados)
              </span>
            )}
            <span className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-emerald-50 text-emerald-700 border border-emerald-200">
              100% Proyectos Validados
            </span>
          </div>
        </div>

        {/* Barra Superior de Filtros Curriculares Dinámicos (HU13) */}
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 items-end">
            <div>
              <label className="block text-xs font-semibold text-slate-600 uppercase mb-1">
                Asignatura / Curso
              </label>
              <select
                value={courseFilter}
                onChange={(e) => setCourseFilter(e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-xs text-slate-800 bg-white focus:outline-none focus:ring-2 focus:ring-blue-600"
              >
                <option value="">Todos los cursos FISI</option>
                <option value="Gestión de Proyectos de TI">Gestión de Proyectos de TI</option>
                <option value="Arquitectura de Software">Arquitectura de Software</option>
                <option value="Ingeniería de Software II">Ingeniería de Software II</option>
                <option value="Inteligencia Artificial">Inteligencia Artificial</option>
                <option value="Desarrollo de Sistemas Móviles">Desarrollo de Sistemas Móviles</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-600 uppercase mb-1">
                Ciclo Académico
              </label>
              <select
                value={cycleFilter}
                onChange={(e) => setCycleFilter(e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-xs text-slate-800 bg-white focus:outline-none focus:ring-2 focus:ring-blue-600"
              >
                <option value="">Todos los ciclos</option>
                <option value="6">VI Ciclo</option>
                <option value="7">VII Ciclo</option>
                <option value="8">VIII Ciclo</option>
                <option value="9">IX Ciclo</option>
                <option value="10">X Ciclo</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-600 uppercase mb-1">
                Semestre Académico
              </label>
              <select
                value={semesterFilter}
                onChange={(e) => setSemesterFilter(e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-xs text-slate-800 bg-white focus:outline-none focus:ring-2 focus:ring-blue-600"
              >
                <option value="">Todos los semestres</option>
                <option value="2026-2">2026-2 (Actual)</option>
                <option value="2026-1">2026-1</option>
                <option value="2025-2">2025-2</option>
              </select>
            </div>

            <div className="flex space-x-2">
              <button
                type="button"
                onClick={handleResetFilters}
                className="w-full px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium rounded-lg text-xs transition-colors"
              >
                Limpiar Filtros
              </button>
            </div>
          </div>
        </div>

        {loading || !analytics ? (
          <div className="bg-white rounded-xl border border-slate-200 p-12 text-center text-sm text-slate-500">
            Consolidando métricas curriculares de la FISI...
          </div>
        ) : (
          <>
            {/* Cuatro Tarjetas de KPIs Ejecutivos (HU12) */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
                <span className="text-xs font-semibold text-slate-500 uppercase">
                  Total Proyectos Validados
                </span>
                <div className="mt-2 flex items-baseline justify-between">
                  <span className="text-3xl font-bold text-slate-900">
                    {analytics.total_validated_projects}
                  </span>
                  <span className="text-xs font-medium text-blue-700 bg-blue-50 px-2 py-0.5 rounded">
                    de {analytics.total_registered_projects} envíos
                  </span>
                </div>
                <p className="text-[11px] text-slate-400 mt-2">
                  Excluye borradores y proyectos observados
                </p>
              </div>

              <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
                <span className="text-xs font-semibold text-slate-500 uppercase">
                  Tasa de Aprobación Docente
                </span>
                <div className="mt-2 flex items-baseline justify-between">
                  <span className="text-3xl font-bold text-emerald-700">
                    {analytics.teacher_approval_rate}%
                  </span>
                  <span className="text-xs font-medium text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded">
                    Sello Oficial
                  </span>
                </div>
                <p className="text-[11px] text-slate-400 mt-2">
                  Proyectos acreditados con código FISI-2026
                </p>
              </div>

              <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
                <span className="text-xs font-semibold text-slate-500 uppercase">
                  Tiempo Activo Promedio SLA
                </span>
                <div className="mt-2 flex items-baseline justify-between">
                  <span className="text-3xl font-bold text-slate-900">
                    {analytics.avg_review_seconds}s
                  </span>
                  <span
                    className={`text-xs font-medium px-2 py-0.5 rounded ${
                      analytics.avg_review_seconds <= 300
                        ? 'bg-emerald-50 text-emerald-700'
                        : 'bg-red-50 text-red-700'
                    }`}
                  >
                    {analytics.avg_review_seconds <= 300 ? 'Meta ≤ 300s OK' : 'Sobre SLA'}
                  </span>
                </div>
                <p className="text-[11px] text-slate-400 mt-2">
                  Esfuerzo docente promedio por evaluación
                </p>
              </div>

              <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
                <span className="text-xs font-semibold text-slate-500 uppercase">
                  Portafolios Públicos Activos
                </span>
                <div className="mt-2 flex items-baseline justify-between">
                  <span className="text-3xl font-bold text-blue-700">
                    {analytics.public_portfolio_rate}%
                  </span>
                  <span className="text-xs font-medium text-blue-700 bg-blue-50 px-2 py-0.5 rounded">
                    Ley N.° 29733
                  </span>
                </div>
                <p className="text-[11px] text-slate-400 mt-2">
                  Con consentimiento informado vigente
                </p>
              </div>
            </div>

            {/* Sección Inferior: Ranking de Tecnologías (Barras de Progreso) + Tabla Comparativa por Asignatura */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              {/* Top de Tecnologías Aplicadas en Aula (5 columnas) */}
              <div className="lg:col-span-5 bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
                <div className="pb-3 border-b border-slate-100">
                  <h2 className="text-sm font-bold text-slate-800 uppercase tracking-wide">
                    Top Tecnologías Aplicadas en Aula
                  </h2>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Frecuencia real extraída y validada por docentes
                  </p>
                </div>

                {analytics.top_technologies.length === 0 ? (
                  <p className="text-xs text-slate-500 py-8 text-center">
                    No existen registros validados para los filtros seleccionados.
                  </p>
                ) : (
                  <div className="space-y-4">
                    {analytics.top_technologies.map((tech, index) => (
                      <div key={index} className="space-y-1.5">
                        <div className="flex items-center justify-between text-xs">
                          <div>
                            <span className="font-bold text-slate-800">{tech.technology}</span>
                            <span className="ml-2 text-[10px] text-slate-400">
                              ({tech.category})
                            </span>
                          </div>
                          <span className="font-semibold text-blue-700">
                            {tech.count} proy. ({tech.percentage}%)
                          </span>
                        </div>
                        <div className="w-full bg-slate-100 rounded-full h-2.5 overflow-hidden">
                          <div
                            className="bg-blue-600 h-2.5 rounded-full transition-all duration-300"
                            style={{ width: `${Math.min(100, tech.percentage)}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Tabla Comparativa por Asignatura para Actualización de Sílabos (7 columnas) */}
              <div className="lg:col-span-7 bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
                <div className="pb-3 border-b border-slate-100 flex items-center justify-between">
                  <div>
                    <h2 className="text-sm font-bold text-slate-800 uppercase tracking-wide">
                      Consolidado Curricular por Asignatura (Sílabos)
                    </h2>
                    <p className="text-xs text-slate-500 mt-0.5">
                      Comparativa de adopción tecnológica y eficiencia de validación por curso
                    </p>
                  </div>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="border-b border-slate-200 text-[11px] font-semibold text-slate-500 uppercase bg-slate-50">
                        <th className="py-2.5 px-3">Asignatura</th>
                        <th className="py-2.5 px-2 text-center">Ciclo</th>
                        <th className="py-2.5 px-2 text-center">Sem.</th>
                        <th className="py-2.5 px-2 text-center">Validados</th>
                        <th className="py-2.5 px-2 text-center">SLA Prom.</th>
                        <th className="py-2.5 px-3">Tech Líder</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 text-xs">
                      {analytics.courses_summary.length === 0 ? (
                        <tr>
                          <td colSpan={6} className="py-8 text-center text-slate-500">
                            Sin asignaturas coincidentes con el filtro aplicado.
                          </td>
                        </tr>
                      ) : (
                        analytics.courses_summary.map((row, idx) => (
                          <tr key={idx} className="hover:bg-slate-50 transition-colors">
                            <td className="py-3 px-3 font-semibold text-slate-800">
                              {row.course_name}
                            </td>
                            <td className="py-3 px-2 text-center text-slate-600">
                              {row.cycle}°
                            </td>
                            <td className="py-3 px-2 text-center text-slate-500">
                              {row.semester}
                            </td>
                            <td className="py-3 px-2 text-center">
                              <span className="inline-block px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700">
                                {row.validated_count}
                              </span>
                            </td>
                            <td className="py-3 px-2 text-center font-mono text-slate-700">
                              {row.avg_review_seconds}s
                            </td>
                            <td className="py-3 px-3">
                              <span className="inline-block px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200 text-[11px] font-medium">
                                {row.top_technology}
                              </span>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}