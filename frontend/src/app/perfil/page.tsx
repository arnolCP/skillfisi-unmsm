'use client';

import { useState, useEffect } from 'react';

interface UserProfile {
  full_name: string;
  email: string;
  student_code: string;
  school: string;
  current_cycle: number;
  linkedin_url: string;
  github_url: string;
}

export default function ProfilePage() {
  const [profile, setProfile] = useState<UserProfile>({
    full_name: '',
    email: '',
    student_code: '',
    school: 'Ingeniería de Sistemas',
    current_cycle: 7,
    linkedin_url: '',
    github_url: '',
  });

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  useEffect(() => {
    const fetchProfile = async () => {
      const userId = localStorage.getItem('user_id');
      const token = localStorage.getItem('token');
      
      if (!userId) {
        setLoading(false);
        return;
      }

      try {
        const res = await fetch(`${API_URL}/api/v1/profile/${userId}`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (res.ok) {
          const data = await res.json();
          setProfile(data);
        }
      } catch (err) {
        setMessage({ type: 'error', text: 'Error al conectar con el servidor' });
      } finally {
        setLoading(false);
      }
    };

    fetchProfile();
  }, [API_URL]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setMessage(null);

    const userId = localStorage.getItem('user_id');
    const token = localStorage.getItem('token');

    try {
      const res = await fetch(`${API_URL}/api/v1/profile/${userId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(profile),
      });

      if (!res.ok) throw new Error('No se pudo actualizar el perfil');

      setMessage({ type: 'success', text: 'Perfil actualizado exitosamente' });
    } catch (err: any) {
      setMessage({ type: 'error', text: err.message || 'Error al guardar cambios' });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center text-slate-500">Cargando perfil...</div>;
  }

  return (
    <div className="min-h-screen bg-slate-50 py-10 px-4">
      <div className="max-w-2xl mx-auto bg-white rounded-xl shadow-sm border border-slate-200 p-8">
        <h2 className="text-xl font-bold text-slate-800 mb-6">Mi Perfil Académico</h2>

        {message && (
          <div className={`mb-6 p-4 rounded-lg text-sm ${message.type === 'success' ? 'bg-emerald-50 text-emerald-800 border border-emerald-200' : 'bg-red-50 text-red-800 border border-red-200'}`}>
            {message.text}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">Nombre Completo</label>
              <input
                type="text"
                disabled
                value={profile.full_name}
                className="w-full px-3 py-2 border border-slate-200 bg-slate-100 rounded-lg text-sm text-slate-600 cursor-not-allowed"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">Correo Institucional</label>
              <input
                type="email"
                disabled
                value={profile.email}
                className="w-full px-3 py-2 border border-slate-200 bg-slate-100 rounded-lg text-sm text-slate-600 cursor-not-allowed"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">Código de Estudiante</label>
              <input
                type="text"
                required
                value={profile.student_code || ''}
                onChange={(e) => setProfile({ ...profile, student_code: e.target.value })}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-600 focus:outline-none text-slate-800"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">Escuela Profesional</label>
              <input
                type="text"
                value={profile.school || 'Ingeniería de Sistemas'}
                onChange={(e) => setProfile({ ...profile, school: e.target.value })}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-600 focus:outline-none text-slate-800"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">Ciclo Actual</label>
              <select
                value={profile.current_cycle || 7}
                onChange={(e) => setProfile({ ...profile, current_cycle: parseInt(e.target.value) })}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-600 focus:outline-none text-slate-800"
              >
                {[...Array(10)].map((_, i) => (
                  <option key={i + 1} value={i + 1}>
                    Ciclo {i + 1}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="border-t border-slate-100 pt-4 space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">Perfil de GitHub</label>
              <input
                type="url"
                placeholder="https://github.com/usuario"
                value={profile.github_url || ''}
                onChange={(e) => setProfile({ ...profile, github_url: e.target.value })}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-600 focus:outline-none text-slate-800"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">Perfil de LinkedIn</label>
              <input
                type="url"
                placeholder="https://linkedin.com/in/usuario"
                value={profile.linkedin_url || ''}
                onChange={(e) => setProfile({ ...profile, linkedin_url: e.target.value })}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-600 focus:outline-none text-slate-800"
              />
            </div>
          </div>

          <div className="flex justify-end pt-4">
            <button
              type="submit"
              disabled={saving}
              className="px-6 py-2 bg-blue-700 hover:bg-blue-800 text-white font-medium rounded-lg text-sm transition-colors duration-200 disabled:opacity-50"
            >
              {saving ? 'Guardando...' : 'Guardar Perfil'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}