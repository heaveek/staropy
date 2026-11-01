import { useEffect, useRef, useState } from "react";
import { api, ApiRequestError } from "../api/client";
import type { ReadingDetail } from "../types/api";
import { ErrorState, Loading, Screen } from "./common";
import { SpreadStage } from "./SpreadStage";

interface Props {
  readingId: string;
  onBack: () => void;
  onPremium?: () => void;
  /** Skip the shuffle/flip ritual (used when opening a card from history). */
  instant?: boolean;
}

/** Result screen: renders the actual GET /readings/{id} payload (cards, positions, interpretation). */
export function ReadingResultPage({ readingId, onBack, onPremium, instant = false }: Props) {
  const [detail, setDetail] = useState<ReadingDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiRequestError | null>(null);
  const [revealed, setRevealed] = useState(instant);
  // The stage must mount exactly once per fetched result; React re-renders must not restart it.
  const stageKeyRef = useRef<string>(readingId);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const d = await api.getReading(readingId);
      setDetail(d);
      stageKeyRef.current = `${d.reading_id}:${d.cards.length}`;
    } catch (e) {
      setError(e as ApiRequestError);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readingId]);

  if (loading) return <Loading label="Загружаем расклад…" />;
  if (error) return <ErrorState error={error} onRetry={load} onPremium={onPremium} />;
  if (!detail) return null;

  return (
    <Screen title={detail.spread_name} subtitle={`${detail.theme_name} · ${formatDate(detail.created_at)}`}>
      <button className="back-link" onClick={onBack}>← Назад</button>

      {detail.question ? <div className="card"><span className="muted">Ваш вопрос:</span> {detail.question}</div> : null}

      {/* Ritual runs on the cards already returned by the backend. */}
      <SpreadStage
        key={stageKeyRef.current}
        cards={detail.cards}
        spreadCode={detail.spread_code}
        autoStart={!instant}
        onRevealed={() => setRevealed(true)}
      />

      {!revealed ? (
        <p className="muted stage-hint">Сосредоточьтесь на вопросе…</p>
      ) : (
        <>
          {detail.opening ? <p className="muted">{detail.opening}</p> : null}

          {detail.cards.map((c) => (
            <div className="card-slot" key={c.position_number}>
              <div className="slot-head">
                <span className="slot-name">{c.position_number}. {c.position_name}</span>
                <span className="orientation">
                  {c.card_name_ru}{c.orientation === "reversed" ? " — перевёрнутая" : ""}
                </span>
              </div>
              <div className="rendered">{c.rendered_text}</div>
            </div>
          ))}
        </>
      )}

      {revealed && detail.summary ? (
        <>
          <h2>Итог</h2>
          <div className="card">{detail.summary}</div>
        </>
      ) : null}

      {detail.combinations.length > 0 ? (
        <>
          <h2>Сочетания</h2>
          <ul className="combo-list">
            {detail.combinations.map((t, i) => <li key={i}>{t}</li>)}
          </ul>
        </>
      ) : null}

      {detail.advice ? (
        <>
          <h2>Совет</h2>
          <div className="card">{detail.advice}</div>
        </>
      ) : null}

      {detail.disclaimer ? <div className="disclaimer">{detail.disclaimer}</div> : null}
    </Screen>
  );
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}
