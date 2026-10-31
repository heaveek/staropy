import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../App";
import type { Catalog, HistoryPage as HistoryPageType, Me, ReadingDetail } from "../types/api";

const me: Me = {
  user_id: 1, telegram_id: 42, username: "u", first_name: "Анна", is_blocked: false,
  premium: { is_premium: false, active_until: null },
  quota: { free_readings_per_day: 1, free_readings_used_today: 0, free_readings_remaining: 1, resets_at_timezone: "Europe/Moscow" },
  history_limit: 3,
  preferences: { daily_reminder_enabled: false, subscription_reminder_enabled: false, timezone: null },
};

const catalog: Catalog = {
  themes: [{ code: "love", name_ru: "Любовь", description: "Отношения", sort_order: 1 }],
  spreads: [
    { code: "daily_card", name_ru: "Карта дня", description: "Одна карта", card_count: 1, is_premium: false, positions: [] },
    { code: "celtic_cross", name_ru: "Кельтский крест", description: "10 позиций", card_count: 10, is_premium: true, positions: [] },
  ],
  question_max_length: 500,
};

const reading: ReadingDetail = {
  reading_id: "r-1", created_at: "2026-01-01T10:00:00Z", content_version: "v1", is_free: true,
  spread_code: "daily_card", spread_name: "Карта дня", theme_code: "love", theme_name: "Любовь",
  question: null, opening: "Расклад на сегодня.", summary: "Итоговый текст расклада.",
  combinations: ["Шут и Маг вместе"], advice: "Действуйте спокойно.", disclaimer: "Развлекательный контент.",
  cards: [{ position_number: 1, position_code: "card", position_name: "Основная позиция", card_id: 0,
            card_code: "major_00_fool", card_name_ru: "Шут", orientation: "upright", rendered_text: "Новое начало." }],
  snapshot: {},
};

function jsonOk(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

function errBody(code: string, message: string, details: Record<string, unknown> = {}) {
  return JSON.stringify({ error: { code, message, details } });
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const path = url.replace("/api/v1", "");
    if (path.startsWith("/auth/me")) return jsonOk(me);
    if (path.startsWith("/catalog")) return jsonOk(catalog);
    if (path === "/readings" && init?.method === "POST") return jsonOk({ reading_id: "r-1", replayed: false });
    if (path.startsWith("/readings/r-1")) return jsonOk(reading);
    if (path.startsWith("/readings?")) {
      const page: HistoryPageType = { items: [], next_cursor: null, limited_by_plan: false };
      return jsonOk(page);
    }
    if (path.startsWith("/premium/products")) {
      return jsonOk({ payments_enabled: false, provider: "telegram_stars", products: [] });
    }
    return new Response(errBody("not_found", "nope"), { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("App bootstrap", () => {
  it("shows loading state, then the home screen with real catalog data", async () => {
    render(<App />);
    expect(screen.getByRole("status")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Таро-расклады")).toBeInTheDocument());
    expect(screen.getByText("Карта дня")).toBeInTheDocument();
    expect(screen.getByText("Кельтский крест")).toBeInTheDocument();
    // Premium badge comes from the backend spread flag
    expect(screen.getAllByText("Premium").length).toBeGreaterThan(0);
    // initData header used for auth requests
    const calls = fetchMock.mock.calls as unknown as [string, RequestInit][];
    const meCall = calls.find(([u]) => String(u).includes("/auth/me"));
    expect(meCall).toBeDefined();
  });

  it("renders unauthorized error when /auth/me returns 401 and offers retry", async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes("/auth/me")) {
        return new Response(errBody("unauthorized", "Требуется авторизация через Telegram Mini App", { reason: "missing_init_data" }), { status: 401 });
      }
      return jsonOk(catalog);
    });
    render(<App />);
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    // The alert contains the server message + code; hint mentions reopening via the bot.
    expect(screen.getByText("Требуется авторизация через Telegram Mini App")).toBeInTheDocument();
    expect(screen.getByText(/через бота/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Повторить" })).toBeInTheDocument();
  });

  it("creates a reading via POST /readings and shows the result screen", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(screen.getByText("Таро-расклады")).toBeInTheDocument());
    await user.click(screen.getByText("Карта дня"));
    await user.click(await screen.findByRole("button", { name: /Сделать расклад/ }));
    await waitFor(() => expect(screen.getByText("Итоговый текст расклада.")).toBeInTheDocument());
    const post = (fetchMock.mock.calls as unknown as [string, RequestInit][]).find(
      ([u, i]) => String(u).endsWith("/readings") && i?.method === "POST",
    );
    expect(post).toBeDefined();
    const body = JSON.parse(String(post![1].body));
    expect(body.spread_code).toBe("daily_card");
    expect(body.theme_code).toBe("love");
    expect(typeof body.idempotencyKey).toBe("string");
    // Result renders server texts only
    expect(screen.getByText("Новое начало.")).toBeInTheDocument();
    expect(screen.getByText("Развлекательный контент.")).toBeInTheDocument();
  });

  it("surfaces premium_required 402 with a Premium CTA instead of fake success", async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      const path = String(url).replace("/api/v1", "");
      if (path.startsWith("/auth/me")) return jsonOk(me);
      if (path.startsWith("/catalog")) return jsonOk(catalog);
      if (path === "/readings" && init?.method === "POST") {
        return new Response(errBody("premium_required", "Расклад доступен в премиум-версии", { spread_code: "celtic_cross" }), { status: 402 });
      }
      return jsonOk({});
    });
    render(<App />);
    await waitFor(() => expect(screen.getByText("Таро-расклады")).toBeInTheDocument());
    await user.click(screen.getByText("Кельтский крест"));
    await user.click(await screen.findByRole("button", { name: /Сделать расклад/ }));
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.getByText("Расклад доступен в премиум-версии")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Открыть Premium" }));
    await waitFor(() => expect(screen.getByText("Что входит в Premium")).toBeInTheDocument());
    // Payments disabled on backend -> honest notice, no fake purchase
    expect(await screen.findByText(/не имитируем платежи/)).toBeInTheDocument();
  });

  it("history tab loads GET /readings and shows empty state", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(screen.getByText("Таро-расклады")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /История/ }));
    await waitFor(() => expect(screen.getByText("Пока пусто")).toBeInTheDocument());
    const histCall = (fetchMock.mock.calls as unknown as [string][]).find(([u]) => String(u).includes("/readings?"));
    expect(histCall).toBeDefined();
  });
});
