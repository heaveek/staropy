import { useEffect, useState } from "react";
import { api, ApiRequestError } from "../api/client";
import type { Catalog, Me } from "../types/api";

export interface AuthState {
  me: Me | null;
  catalog: Catalog | null;
  loading: boolean;
  error: string | null;
  errorCode: string | null;
  reload: () => void;
}

/** Loads /auth/me and /catalog on mount. Real endpoints — no mock data. */
export function useBootstrap(): AuthState {
  const [me, setMe] = useState<Me | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setErrorCode(null);
    Promise.all([api.me(), api.catalog()])
      .then(([meRes, catRes]) => {
        if (cancelled) return;
        setMe(meRes);
        setCatalog(catRes);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        const err = e as ApiRequestError;
        setError(err.message ?? "Ошибка загрузки");
        setErrorCode(err.code ?? "unknown");
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [tick]);

  return { me, catalog, loading, error, errorCode, reload: () => setTick((t) => t + 1) };
}
