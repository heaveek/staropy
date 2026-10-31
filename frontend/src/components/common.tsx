import type { ReactNode } from "react";
import type { ApiRequestError } from "../api/client";
import { presentApiError } from "../lib/errors";

export function Loading({ label = "Загрузка…" }: { label?: string }) {
  return (
    <div className="center-state" role="status" aria-live="polite">
      <div className="spinner" aria-hidden="true" />
      <div>{label}</div>
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="center-state">
      <div style={{ fontSize: 30, marginBottom: 8 }}>🕯️</div>
      <div style={{ color: "var(--text)", fontWeight: 600 }}>{title}</div>
      {hint ? <div style={{ marginTop: 6 }}>{hint}</div> : null}
    </div>
  );
}

interface ErrorStateProps {
  error: ApiRequestError | Error | null;
  onRetry?: () => void;
  onPremium?: () => void;
}

/** Renders real API errors with guidance per code/status. Never hides failures behind fake data. */
export function ErrorState({ error, onRetry, onPremium }: ErrorStateProps) {
  if (!error) return null;
  const apiErr = error as ApiRequestError;
  const p = presentApiError(apiErr);
  const canRetry = p.retryable && onRetry;
  return (
    <div className="error-banner" role="alert">
      <div>{p.title}</div>
      {typeof apiErr.code === "string" ? <div className="err-code">{apiErr.code}</div> : null}
      {p.hint ? <div className="muted" style={{ marginTop: 6 }}>{p.hint}</div> : null}
      <div className="btn-row" style={{ marginTop: 10 }}>
        {canRetry ? (
          <button className="btn secondary" onClick={onRetry}>Повторить</button>
        ) : null}
        {p.showPremiumCta && onPremium ? (
          <button className="btn" onClick={onPremium}>Открыть Premium</button>
        ) : null}
      </div>
    </div>
  );
}

export function Screen({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <section>
      <h1>{title}</h1>
      {subtitle ? <p className="subtitle">{subtitle}</p> : null}
      {children}
    </section>
  );
}
