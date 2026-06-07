import type { ReactNode } from "react";

type AuthLayoutProps = {
  title: string;
  subtitle: string;
  footer: ReactNode;
  children: ReactNode;
};

export default function AuthLayout({ title, subtitle, footer, children }: AuthLayoutProps) {
  return (
    <div className="auth-shell">
      <aside className="auth-brand-panel">
        <div className="auth-brand-inner">
          <div className="auth-logo-mark" aria-hidden>
            <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect width="32" height="32" rx="8" fill="currentColor" fillOpacity="0.15" />
              <path
                d="M10 16.5c0-3.5 2.8-6.3 6.3-6.3 1.4 0 2.7.5 3.7 1.3V9.5c-1-.4-2.1-.6-3.2-.6-5 0-9 4-9 9s4 9 9 9c1.1 0 2.2-.2 3.2-.6v-1.8c-1 .8-2.3 1.3-3.7 1.3-3.5 0-6.3-2.8-6.3-6.3Z"
                fill="currentColor"
              />
              <path
                d="M22.5 16.5c0 3.5-2.8 6.3-6.3 6.3-1.4 0-2.7-.5-3.7-1.3v1.8c1 .4 2.1.6 3.2.6 5 0 9-4 9-9s-4-9-9-9c-1.1 0-2.2.2-3.2.6v1.8c1-.8 2.3-1.3 3.7-1.3 3.5 0 6.3 2.8 6.3 6.3Z"
                fill="currentColor"
                fillOpacity="0.55"
              />
            </svg>
          </div>
          <p className="auth-brand-name">Stripe Installer</p>
          <h2 className="auth-brand-headline">Stripe setup without exposing secrets.</h2>
          <p className="auth-brand-copy">
            Encrypted vault, live verification, automated provisioning, and deploy readiness — built for
            production billing apps.
          </p>
          <ul className="auth-brand-features">
            <li>Write-only secret vault</li>
            <li>Live pipeline with real-time logs</li>
            <li>Codegen for Django, Next.js, and more</li>
          </ul>
        </div>
      </aside>

      <main className="auth-main">
        <div className="auth-card">
          <header className="auth-card-header">
            <h1>{title}</h1>
            <p className="muted">{subtitle}</p>
          </header>
          {children}
          <footer className="auth-footer">{footer}</footer>
        </div>
      </main>
    </div>
  );
}
