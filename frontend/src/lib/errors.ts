import type { ApiRequestError } from "../api/client";

export interface ErrorPresentation {
  title: string;
  hint: string | null;
  /** Show a button leading to the Premium screen (402 premium_required). */
  showPremiumCta: boolean;
  /** Show retry button (network/5xx). */
  retryable: boolean;
}

/**
 * Maps real backend error codes / HTTP statuses (see backend/app/core/errors.py
 * and services/domain.py) to user-facing guidance. No fake success states.
 */
export function presentApiError(err: ApiRequestError): ErrorPresentation {
  switch (err.code) {
    case "unauthorized": {
      const reason = typeof err.details.reason === "string" ? err.details.reason : "";
      return {
        title: err.message || "Требуется авторизация через Telegram",
        hint:
          reason === "auth_date_expired" || reason === "invalid_signature"
            ? "Сессия Telegram устарела. Закройте и снова откройте приложение из чата с ботом."
            : "Откройте приложение через бота в Telegram — данные авторизации приходят вместе с Mini App.",
        showPremiumCta: false,
        retryable: true,
      };
    }
    case "forbidden":
      return { title: err.message || "Доступ ограничен", hint: null, showPremiumCta: false, retryable: false };
    case "premium_required":
      return {
        title: err.message || "Расклад доступен в премиум-версии",
        hint: "Оформите Premium, чтобы открыть Кельтский крест и снять дневные лимиты.",
        showPremiumCta: true,
        retryable: false,
      };
    case "limit_reached":
      return {
        title: err.message || "Бесплатный лимит на сегодня исчерпан",
        hint: "Лимит сбрасывается в полночь по часовому поясу сервиса. Premium снимает ограничения.",
        showPremiumCta: true,
        retryable: false,
      };
    case "payments_disabled":
      return {
        title: err.message || "Оплата временно недоступна",
        hint: "Платёжный сервис ещё не подключён на сервере. Мы не имитируем оплату.",
        showPremiumCta: false,
        retryable: false,
      };
    case "payment_failed":
      return {
        title: err.message || "Не удалось создать счёт",
        hint: "Попробуйте позже. Если не получится — обратитесь к боту в Telegram.",
        showPremiumCta: false,
        retryable: true,
      };
    case "not_found":
    case "spread_not_found":
    case "theme_not_found":
      return { title: err.message || "Не найдено", hint: null, showPremiumCta: false, retryable: false };
    case "validation_failed":
      return { title: err.message || "Проверьте переданные данные", hint: null, showPremiumCta: false, retryable: false };
    case "network_error":
    case "unavailable":
    case "internal_error":
    case "http_error":
      return {
        title: err.message || "Сервис временно недоступен",
        hint: "Проверьте соединение и попробуйте ещё раз.",
        showPremiumCta: false,
        retryable: true,
      };
    default:
      return {
        title: err.message || `Ошибка ${err.status}`,
        hint: null,
        showPremiumCta: false,
        retryable: err.status >= 500 || err.status === 0,
      };
  }
}

export function isAuthError(err: unknown): boolean {
  return (err as ApiRequestError)?.code === "unauthorized";
}
