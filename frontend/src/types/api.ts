// Types mirroring backend/app/schemas/schemas.py (source of truth: OpenAPI)

export interface Theme { code: string; name_ru: string; description: string | null; sort_order: number }
export interface Position { number: number; code: string; name_ru: string; description: string | null }
export interface Spread {
  code: string; name_ru: string; description: string | null;
  card_count: number; is_premium: boolean; positions: Position[];
}
export interface Catalog { themes: Theme[]; spreads: Spread[]; question_max_length: number }

export interface Quota {
  free_readings_per_day: number; free_readings_used_today: number;
  free_readings_remaining: number; resets_at_timezone: string;
}
export interface PremiumStatus { is_premium: boolean; active_until: string | null }
export interface Preferences { daily_reminder_enabled: boolean; subscription_reminder_enabled: boolean; timezone: string | null }
export interface Me {
  user_id: number; telegram_id: number; username: string | null; first_name: string | null;
  is_blocked: boolean; premium: PremiumStatus; quota: Quota;
  history_limit: number | null; preferences: Preferences;
}

export interface ReadingCardOut {
  position_number: number; position_code: string; position_name: string;
  card_id: number; card_code: string; card_name_ru: string;
  orientation: string; rendered_text: string;
}
export interface ReadingDetail {
  reading_id: string; created_at: string; content_version: string; is_free: boolean;
  spread_code: string; spread_name: string; theme_code: string; theme_name: string;
  question: string | null; cards: ReadingCardOut[]; opening: string | null;
  summary: string; combinations: string[]; advice: string | null; disclaimer: string;
  snapshot: Record<string, unknown>;
}
export interface HistoryItem {
  reading_id: string; created_at: string; spread_code: string; spread_name: string;
  theme_code: string; theme_name: string; summary_text: string; card_names: string[];
}
export interface HistoryPage { items: HistoryItem[]; next_cursor: string | null; limited_by_plan: boolean }

export interface Product {
  product_code: string; name: string; description: string | null;
  entitlement_type: string; duration_days: number | null; price_amount: number; currency: string;
}
export interface ProductsResponse { payments_enabled: boolean; provider: string; products: Product[] }
export interface PaymentCreate {
  payment_id: number; status: string; invoice_payload: string;
  bot_invoice_url: string | null; message: string | null;
}
export interface ApiErrorBody { error: { code: string; message: string; details: Record<string, unknown> } }
