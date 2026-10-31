import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiRequestError } from "../api/client";
import type { HistoryItem, HistoryPage } from "../types/api";
import { EmptyState, ErrorState, Loading, Screen } from "./common";
import { formatDate } from "./ReadingResultPage";

interface Props {
  onOpen: (readingId: string) => void;
  onPremium?: () => void;
}

/** History screen with cursor pagination backed by GET /readings?limit&cursor. */
export function HistoryPage({ onOpen, onPremium }: Props) {
  const [page, setPage] = useState<HistoryPage | null>(null);
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<ApiRequestError | null>(null);
  const cursorRef = useRef<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    cursorRef.current = null;
    try {
      const p = await api.history(null);
      setPage(p);
      setItems(p.items);
      cursorRef.current = p.next_cursor;
    } catch (e) {
      setError(e as ApiRequestError);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function loadMore() {
    if (!cursorRef.current || loadingMore) return;
    setLoadingMore(true);
    try {
      const p = await api.history(cursorRef.current);
      setItems((prev) => [...prev, ...p.items]);
      cursorRef.current = p.next_cursor;
      setPage(p);
    } catch (e) {
      setError(e as ApiRequestError);
    } finally {
      setLoadingMore(false);
    }
  }

  if (loading) return <Loading label="Ищем ваши расклады…" />;
  if (error && items.length === 0) return <ErrorState error={error} onRetry={load} onPremium={onPremium} />;

  return (
    <Screen title="История">
      {page?.limited_by_plan ? (
        <div className="card muted">
          Бесплатный план показывает недавние расклады. Premium открывает всю историю.
        </div>
      ) : null}

      {items.length === 0 ? (
        <EmptyState title="Пока пусто" hint="Сделайте первый расклад — он появится здесь." />
      ) : (
        items.map((it) => (
          <div
            key={it.reading_id}
            className="card selectable history-item"
            role="button"
            tabIndex={0}
            onClick={() => onOpen(it.reading_id)}
            onKeyDown={(e) => { if (e.key === "Enter") onOpen(it.reading_id); }}
          >
            <div className="row">
              <strong>{it.spread_name}</strong>
              <span className="meta">{formatDate(it.created_at)}</span>
            </div>
            <div className="meta">{it.theme_name}{it.card_names.length ? ` · ${it.card_names.join(", ")}` : ""}</div>
            <div className="summary">{it.summary_text}</div>
          </div>
        ))
      )}

      {error ? <ErrorState error={error} onRetry={loadMore} onPremium={onPremium} /> : null}

      {cursorRef.current ? (
        <button className="btn secondary" onClick={loadMore} disabled={loadingMore}>
          {loadingMore ? "Загружаем…" : "Загрузить ещё"}
        </button>
      ) : null}
    </Screen>
  );
}
