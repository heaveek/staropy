import { useEffect, useRef, useState } from "react";
import { api, ApiRequestError, uuid } from "../api/client";
import type { Me, Spread, Theme } from "../types/api";
import { ErrorState, Loading, Screen } from "./common";

interface Props {
  spread: Spread;
  theme: Theme;
  maxLength: number;
  onDone: (readingId: string) => void;
  onBack: () => void;
  onPremium: () => void;
  /** Optional hook so parent can refresh quota/premium state after a 402. */
  onMeStale?: () => void;
}

/**
 * Configure & create a reading. Calls POST /readings with a fresh idempotency key.
 * The key is generated once per screen mount and reused on retries, so a failed
 * network attempt cannot consume the quota twice (backend replays by key).
 */
export function NewReadingPage({ spread, theme, maxLength, onDone, onBack, onPremium, onMeStale }: Props) {
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiRequestError | null>(null);
  const keyRef = useRef<string>(uuid());
  const started = useRef(false);

  useEffect(() => {
    // Reset the idempotency key when the target spread/theme changes.
    keyRef.current = uuid();
    setError(null);
    started.current = false;
  }, [spread.code, theme.code]);

  async function submit() {
    if (busy || started.current) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.createReading({
        spread_code: spread.code,
        theme_code: theme.code,
        question: question.trim() ? question.trim() : null,
        idempotencyKey: keyRef.current,
      });
      started.current = true;
      onDone(res.reading_id);
    } catch (e) {
      const err = e as ApiRequestError;
      setError(err);
      if (err.status === 402 && onMeStale) onMeStale();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen title={spread.name_ru} subtitle={`Тема: ${theme.name_ru}`}>
      <button className="back-link" onClick={onBack}>← Назад</button>

      <label className="muted" htmlFor="question">Вопрос (необязательно)</label>
      <textarea
        id="question"
        className="question-input"
        value={question}
        maxLength={maxLength}
        placeholder="Например: как мне двигаться в текущей ситуации?"
        onChange={(e) => setQuestion(e.target.value)}
      />
      <div className="char-counter">{question.length}/{maxLength}</div>

      {error ? <div style={{ marginTop: 12 }}><ErrorState error={error} onRetry={submit} onPremium={onPremium} /></div> : null}

      <div style={{ marginTop: 16 }}>
        {busy ? (
          <Loading label="Перемешиваем карты…" />
        ) : (
          <button className="btn" onClick={submit}>
            Сделать расклад{spread.is_premium ? " (Premium)" : ""}
          </button>
        )}
      </div>
    </Screen>
  );
}
