import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'SkillFISI - Plataforma de Portafolios Académicos',
  description: 'Gestión y validación de evidencias académicas FISI - UNMSM',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es">
      <body className="bg-slate-50 text-slate-900 antialiased">
        {children}
      </body>
    </html>
  );
}