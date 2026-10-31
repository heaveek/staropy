// Minimal typed wrapper around the Telegram WebApp SDK (window.Telegram.WebApp).
// In tests / outside Telegram it degrades to a safe stub.

export interface TelegramWebApp {
  ready(): void;
  initData: string;
  initDataUnsafe?: { user?: { id: number; first_name?: string; username?: string } };
  colorScheme?: "light" | "dark";
  themeParams?: Record<string, string>;
  setHeaderColor?(color: string): void;
  setBackgroundColor?(color: string): void;
  HapticFeedback?: { impactOccurred?(style: string): void };
  openInvoice?(url: string, cb?: (status: string) => void): void;
  close?(): void;
}

declare global {
  interface Window { Telegram?: { WebApp?: TelegramWebApp } }
}

export function getTelegram(): TelegramWebApp | null {
  return window.Telegram?.WebApp ?? null;
}

export function getInitData(): string {
  return getTelegram()?.initData ?? "";
}

export function initTelegram(): void {
  const tg = getTelegram();
  if (!tg) return;
  tg.ready();
  try {
    tg.setHeaderColor?.("#131a2b");
    tg.setBackgroundColor?.("#131a2b");
  } catch {
    /* optional APIs */
  }
}
