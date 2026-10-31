import { describe, expect, it } from "vitest";
import { ApiRequestError } from "../api/client";
import { presentApiError } from "./errors";

const err = (code: string, status: number, details: Record<string, unknown> = {}, message = "") =>
  new ApiRequestError(code, message || `msg:${code}`, status, details);

describe("presentApiError", () => {
  it("maps premium_required (402) to a Premium CTA", () => {
    const p = presentApiError(err("premium_required", 402));
    expect(p.showPremiumCta).toBe(true);
    expect(p.retryable).toBe(false);
  });

  it("maps limit_reached (402) to quota explanation + Premium CTA", () => {
    const p = presentApiError(err("limit_reached", 402, { free_readings_per_day: 1 }));
    expect(p.showPremiumCta).toBe(true);
    expect(p.hint?.toLowerCase()).toContain("лимит");
  });

  it("maps unauthorized with expired signature reason to reopen guidance", () => {
    const p = presentApiError(new ApiRequestError("unauthorized", "Требуется авторизация через Telegram Mini App", 401, { reason: "auth_date_expired" }));
    expect(p.title.toLowerCase()).toContain("авторизац");
    expect(p.hint).toContain("бот");
    expect(p.showPremiumCta).toBe(false);
  });

  it("payments_disabled (503) states honestly that payments are not connected", () => {
    const p = presentApiError(err("payments_disabled", 503));
    expect(p.hint).toContain("не имитируем");
    expect(p.retryable).toBe(false);
  });

  it("network errors are retryable", () => {
    const p = presentApiError(err("network_error", 0));
    expect(p.retryable).toBe(true);
  });

  it("forbidden is terminal and shows the server message", () => {
    const p = presentApiError(err("forbidden", 403, {}, "Доступ ограничен"));
    expect(p.title).toBe("Доступ ограничен");
    expect(p.retryable).toBe(false);
    expect(p.showPremiumCta).toBe(false);
  });

  it("unknown 5xx defaults to retryable", () => {
    const p = presentApiError(err("http_error", 502));
    expect(p.retryable).toBe(true);
  });
});
