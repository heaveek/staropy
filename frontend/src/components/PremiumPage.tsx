import { useCallback, useEffect, useState } from "react";
import { api, ApiRequestError } from "../api/client";
import type { Me, PaymentCreate, Product, ProductsResponse } from "../types/api";
import { getTelegram } from "../lib/telegram";
import { ErrorState, Loading, Screen } from "./common";

interface Props {
  me: Me;
  onMeRefresh: () => void;
}

/**
 * Premium screen. Tariffs and availability come from the backend
 * (GET /premium/products). Purchase opens a real Telegram invoice via
 * WebApp.openInvoice when the server provides one; payments are never imitated —
 * if PAYMENTS_ENABLED=false the backend answers 503 and we say so plainly.
 */
export function PremiumPage({ me, onMeRefresh }: Props) {
  const [products, setProducts] = useState<ProductsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiRequestError | null>(null);
  const [busyCode, setBusyCode] = useState<string | null>(null);
  const [invoiceNote, setInvoiceNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setProducts(await api.products());
    } catch (e) {
      setError(e as ApiRequestError);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function buy(p: Product) {
    if (busyCode) return;
    setBusyCode(p.product_code);
    setError(null);
    setInvoiceNote(null);
    try {
      const res: PaymentCreate = await api.createPayment(p.product_code);
      if (res.bot_invoice_url) {
        const tg = getTelegram();
        if (tg?.openInvoice) {
          tg.openInvoice(res.bot_invoice_url, (status) => {
            if (status === "paid") {
              // Poll owner-scoped status; premium is granted only after the
              // verified Telegram event on the backend, not here.
              void pollPaid(res.payment_id);
            } else {
              setInvoiceNote(status === "cancelled" ? "Оплата отменена." : `Статус счёта: ${status}`);
            }
          });
        } else {
          setInvoiceNote("Счёт создан, но откройте его в Telegram-боте — вне Mini App оплата недоступна.");
        }
      } else {
        setInvoiceNote(res.message ?? "Счёт создан, но ссылка на оплату не вернулась.");
      }
    } catch (e) {
      setError(e as ApiRequestError);
    } finally {
      setBusyCode(null);
    }
  }

  async function pollPaid(paymentId: number) {
    for (let i = 0; i < 10; i++) {
      try {
        const s = await api.paymentStatus(paymentId);
        if (s.status === "paid") {
          onMeRefresh();
          setInvoiceNote("Оплата подтверждена — Premium активирован ✨");
          return;
        }
      } catch {
        /* transient */
      }
      await new Promise((r) => setTimeout(r, 1000));
    }
    setInvoiceNote("Платёж ещё обрабатывается — обновите страницу через минуту.");
  }

  const premiumActive = me.premium.is_premium;

  return (
    <Screen title="Premium">
      <div className="card status-card">
        <div>
          <div className="card-title">
            {premiumActive ? "Premium активен ✨" : "Бесплатный план"}
          </div>
          <div className="muted">
            {premiumActive && me.premium.active_until
              ? `Действует до ${new Date(me.premium.active_until).toLocaleDateString("ru-RU")}`
              : `Бесплатно: ${me.quota.free_readings_remaining}/${me.quota.free_readings_per_day} раскладов в день`}
          </div>
        </div>
        <span className={premiumActive ? "badge ok" : "badge"}>{premiumActive ? "ON" : "OFF"}</span>
      </div>

      <h2>Что входит в Premium</h2>
      <ul className="combo-list muted">
        <li>Расклад «Кельтский крест» (10 карт)</li>
        <li>Без дневных лимитов бесплатных раскладов</li>
        <li>Полная история раскладов без ограничений плана</li>
      </ul>

      {loading ? <Loading label="Загружаем тарифы…" /> : null}
      {!loading && error ? <ErrorState error={error} onRetry={load} /> : null}

      {!loading && products && !products.payments_enabled ? (
        <div className="card muted">
          Оплата пока отключена на сервере (ожидает подключения Telegram Stars).
          Мы не имитируем платежи — покупка станет доступна после включения платёжного режима.
        </div>
      ) : null}

      {!loading && products?.payments_enabled ? (
        products.products.length === 0 ? (
          <div className="card muted">Активных тарифов сейчас нет.</div>
        ) : (
          products.products.map((p) => (
            <div className="card" key={p.product_code}>
              <div className="card-title">{p.name}</div>
              {p.description ? <div className="card-desc">{p.description}</div> : null}
              <div className="price-line">
                {p.price_amount} <span className="muted small">{currencyLabel(p.currency)}</span>
                {p.duration_days ? <span className="muted small"> · {durationLabel(p.duration_days)}</span> : <span className="muted small"> · навсегда</span>}
              </div>
              <button
                className="btn"
                style={{ marginTop: 10 }}
                disabled={busyCode !== null || premiumActive}
                onClick={() => buy(p)}
              >
                {busyCode === p.product_code ? "Создаём счёт…" : premiumActive ? "Premium уже активен" : "Купить"}
              </button>
            </div>
          ))
        )
      ) : null}

      {invoiceNote ? <div className="card muted">{invoiceNote}</div> : null}
    </Screen>
  );
}

function currencyLabel(c: string): string {
  return c === "XTR" ? "Stars" : c;
}

function durationLabel(days: number): string {
  if (days >= 365) return `${Math.round(days / 365)} год`;
  if (days >= 30) return `${Math.round(days / 30)} мес.`;
  return `${days} дн.`;
}
