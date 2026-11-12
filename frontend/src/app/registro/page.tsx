'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

const INSTITUTIONAL_DOMAIN = 'unmsm.edu.pe';
const MIN_NAME_LENGTH = 3;
const MAX_NAME_LENGTH = 255;
const MIN_PASSWORD_LENGTH = 8;
const MAX_PASSWORD_LENGTH = 72;

const DOMAIN_ERROR = 'Acceso restringido: debes usar tu correo institucional (@unmsm.edu.pe).';
const CONNECTION_ERROR = 'Error al conectar con el servidor. Intenta nuevamente.';

type Field = 'fullName' | 'email' | 'password' | 'confirmPassword';
type FieldErrors = Partial<Record<Field, string>>;

interface ServerError {
  status: number;
  text: string;
}

interface ValidationIssue {
  loc?: (string | number)[];
}

// Mensajes para los errores 422 de validación de FastAPI, según el campo del backend.
const VALIDATION_MESSAGES: Record<string, string> = {
  full_name: `El nombre completo debe tener entre ${MIN_NAME_LENGTH} y ${MAX_NAME_LENGTH} caracteres.`,
  email: 'El correo electrónico no es válido.',
  password: `La contraseña debe tener entre ${MIN_PASSWORD_LENGTH} y ${MAX_PASSWORD_LENGTH} caracteres.`,
};

// Mismo criterio que is_institutional_email del backend: un solo @ y dominio exacto unmsm.edu.pe.
function isInstitutionalEmail(value: string): boolean {
  const normalized = value.trim().toLowerCase();
  const at = normalized.lastIndexOf('@');
  if (at <= 0) return false;
  return !normalized.slice(0, at).includes('@') && normalized.slice(at + 1) === INSTITUTIONAL_DOMAIN;
}

function serverErrorMessage(status: number, detail: unknown): string {
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = (detail as ValidationIssue[]).map((issue) => {
      const loc = issue.loc ?? [];
      const field = loc[loc.length - 1];
      return (typeof field === 'string' && VALIDATION_MESSAGES[field]) || 'Revisa los datos del formulario.';
    });
    return Array.from(new Set(messages)).join(' ');
  }
  if (status === 403) return DOMAIN_ERROR;
  if (status === 409) return 'El correo ya está registrado.';
  if (status === 400) return 'No se pudo crear la cuenta. Revisa el correo y la contraseña.';
  return 'No se pudo crear la cuenta. Intenta nuevamente en unos minutos.';
}

export default function RegistroPage() {
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPasswords, setShowPasswords] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [serverError, setServerError] = useState<ServerError | null>(null);
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  const validate = (): FieldErrors => {
    const errors: FieldErrors = {};
    const name = fullName.trim();
    if (name.length < MIN_NAME_LENGTH || name.length > MAX_NAME_LENGTH) {
      errors.fullName = `Ingresa tu nombre completo (entre ${MIN_NAME_LENGTH} y ${MAX_NAME_LENGTH} caracteres).`;
    }
    if (!isInstitutionalEmail(email)) {
      errors.email = DOMAIN_ERROR;
    }
    if (password.length < MIN_PASSWORD_LENGTH) {
      errors.password = `La contraseña debe tener al menos ${MIN_PASSWORD_LENGTH} caracteres.`;
    } else if (password.length > MAX_PASSWORD_LENGTH) {
      errors.password = `La contraseña no puede superar los ${MAX_PASSWORD_LENGTH} caracteres.`;
    }
    if (confirmPassword !== password) {
      errors.confirmPassword = 'Las contraseñas no coinciden.';
    }
    return errors;
  };

  const clearFieldError = (field: Field) => {
    setFieldErrors((current) => (current[field] ? { ...current, [field]: undefined } : current));
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setServerError(null);

    const errors = validate();
    setFieldErrors(errors);
    if (Object.values(errors).some(Boolean)) {
      return;
    }

    setLoading(true);
    let redirecting = false;

    try {
      const res = await fetch(`${API_URL}/api/v1/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ full_name: fullName.trim(), email: email.trim(), password }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => null);
        setServerError({ status: res.status, text: serverErrorMessage(res.status, data?.detail) });
        return;
      }

      redirecting = true;
      router.push('/login?registro=exitoso');
    } catch {
      setServerError({ status: 0, text: CONNECTION_ERROR });
    } finally {
      if (!redirecting) {
        setLoading(false);
      }
    }
  };

  const inputClass = (field: Field) =>
    `w-full px-3 py-2 border rounded-lg text-base sm:text-sm focus:outline-none focus:ring-2 focus:ring-blue-600 text-slate-800 ${
      fieldErrors[field] ? 'border-red-400' : 'border-slate-300'
    }`;
  const labelClass = 'block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1';

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 px-4 py-8">
      <div className="max-w-md w-full bg-white rounded-xl shadow-lg border border-slate-100 p-6 sm:p-8">
        <div className="text-center mb-6">
          <h1 className="text-2xl font-bold text-slate-800">SkillFISI</h1>
          <p className="text-sm text-slate-500 mt-1">Crea tu cuenta de estudiante</p>
        </div>

        {serverError && (
          <div role="alert" className="mb-4 p-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg">
            {serverError.text}
            {serverError.status === 409 && (
              <>
                {' '}
                <Link href="/login" className="font-semibold underline">
                  Inicia sesión
                </Link>
              </>
            )}
          </div>
        )}

        <form onSubmit={handleRegister} noValidate className="space-y-4">
          <div>
            <label htmlFor="full_name" className={labelClass}>
              Nombre completo
            </label>
            <input
              id="full_name"
              type="text"
              required
              autoComplete="name"
              maxLength={MAX_NAME_LENGTH}
              placeholder="Nombres y apellidos"
              value={fullName}
              onChange={(e) => {
                setFullName(e.target.value);
                clearFieldError('fullName');
              }}
              aria-invalid={Boolean(fieldErrors.fullName)}
              aria-describedby={fieldErrors.fullName ? 'full_name-error' : undefined}
              className={inputClass('fullName')}
            />
            {fieldErrors.fullName && (
              <p id="full_name-error" className="mt-1 text-xs text-red-600">
                {fieldErrors.fullName}
              </p>
            )}
          </div>

          <div>
            <label htmlFor="email" className={labelClass}>
              Correo institucional
            </label>
            <input
              id="email"
              type="email"
              required
              inputMode="email"
              autoComplete="email"
              autoCapitalize="none"
              spellCheck={false}
              maxLength={255}
              placeholder="tu.nombre@unmsm.edu.pe"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                clearFieldError('email');
              }}
              aria-invalid={Boolean(fieldErrors.email)}
              aria-describedby={fieldErrors.email ? 'email-error' : undefined}
              className={inputClass('email')}
            />
            {fieldErrors.email && (
              <p id="email-error" className="mt-1 text-xs text-red-600">
                {fieldErrors.email}
              </p>
            )}
          </div>

          <div>
            <label htmlFor="password" className={labelClass}>
              Contraseña
            </label>
            <input
              id="password"
              type={showPasswords ? 'text' : 'password'}
              required
              autoComplete="new-password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                clearFieldError('password');
              }}
              aria-invalid={Boolean(fieldErrors.password)}
              aria-describedby={fieldErrors.password ? 'password-error' : 'password-hint'}
              className={inputClass('password')}
            />
            {fieldErrors.password ? (
              <p id="password-error" className="mt-1 text-xs text-red-600">
                {fieldErrors.password}
              </p>
            ) : (
              <p id="password-hint" className="mt-1 text-xs text-slate-500">
                Mínimo {MIN_PASSWORD_LENGTH} caracteres. Combina letras y números.
              </p>
            )}
          </div>

          <div>
            <label htmlFor="confirm_password" className={labelClass}>
              Confirmar contraseña
            </label>
            <input
              id="confirm_password"
              type={showPasswords ? 'text' : 'password'}
              required
              autoComplete="new-password"
              placeholder="••••••••"
              value={confirmPassword}
              onChange={(e) => {
                setConfirmPassword(e.target.value);
                clearFieldError('confirmPassword');
              }}
              aria-invalid={Boolean(fieldErrors.confirmPassword)}
              aria-describedby={fieldErrors.confirmPassword ? 'confirm_password-error' : undefined}
              className={inputClass('confirmPassword')}
            />
            {fieldErrors.confirmPassword && (
              <p id="confirm_password-error" className="mt-1 text-xs text-red-600">
                {fieldErrors.confirmPassword}
              </p>
            )}
          </div>

          <label className="flex items-center gap-2 text-sm text-slate-600 select-none">
            <input
              type="checkbox"
              checked={showPasswords}
              onChange={(e) => setShowPasswords(e.target.checked)}
              className="h-4 w-4 rounded border-slate-300 text-blue-700 focus:ring-blue-600"
            />
            Mostrar contraseñas
          </label>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-blue-700 hover:bg-blue-800 text-white font-medium rounded-lg text-sm transition-colors duration-200 disabled:opacity-50"
          >
            {loading ? 'Creando cuenta...' : 'Crear cuenta'}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-slate-600">
          ¿Ya tienes una cuenta?{' '}
          <Link href="/login" className="font-medium text-blue-700 hover:text-blue-800 hover:underline">
            Inicia sesión
          </Link>
        </p>
        <p className="mt-2 text-center text-xs text-slate-400">
          Las cuentas de docente las crea el equipo del proyecto.
        </p>

        <div className="mt-6 border-t border-slate-100 pt-4 text-center">
          <p className="text-xs text-slate-400">
            Facultad de Ingeniería de Sistemas e Informática - UNMSM
          </p>
        </div>
      </div>
    </div>
  );
}
