import { useState } from "react";
import type { Spread, Theme } from "./types/api";
import { useBootstrap } from "./hooks/useBootstrap";
import { initTelegram } from "./lib/telegram";
import { ErrorState, Loading, Screen } from "./components/common";
import { HomePage } from "./components/HomePage";
import { NewReadingPage } from "./components/NewReadingPage";
import { ReadingResultPage } from "./components/ReadingResultPage";
import { HistoryPage } from "./components/HistoryPage";
import { PremiumPage } from "./components/PremiumPage";

initTelegram();

type Tab = "home" | "history" | "premium";
type Route =
  | { tab: Tab }
  | { tab: "new"; spread: Spread; theme: Theme }
  | { tab: "result"; readingId: string };

const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: "home", label: "Расклад", icon: "🃏" },
  { id: "history", label: "История", icon: "🕰" },
  { id: "premium", label: "Premium", icon: "⭐" },
];

export default function App() {
  const boot = useBootstrap();
  const [route, setRoute] = useState<Route>({ tab: "home" });

  // Global loading / error states — real API outcomes only.
  if (boot.loading) {
    return (
      <div className="app-shell">
        <main className="app-main"><Loading label="Подключаемся к Telegram…" /></main>
      </div>
    );
  }
  if (boot.error || !boot.me || !boot.catalog) {
    return (
      <div className="app-shell">
        <main className="app-main">
          <Screen title="Таро">
            <ErrorState
              error={boot.error ? Object.assign(new Error(boot.error), { code: boot.errorCode ?? "unknown", status: 0, details: {} }) : null}
              onRetry={boot.reload}
            />
          </Screen>
        </main>
      </div>
    );
  }

  const me = boot.me;
  const catalog = boot.catalog;
  const activeTab: Tab = route.tab === "new" || route.tab === "result" ? "home" : route.tab;

  return (
    <div className="app-shell">
      <main className="app-main">
        {route.tab === "home" && (
          <HomePage
            me={me}
            catalog={catalog}
            onStart={(spread, theme) => setRoute({ tab: "new", spread, theme })}
          />
        )}
        {route.tab === "new" && (
          <NewReadingPage
            spread={route.spread}
            theme={route.theme}
            maxLength={catalog.question_max_length}
            onDone={(readingId) => setRoute({ tab: "result", readingId })}
            onBack={() => setRoute({ tab: "home" })}
            onPremium={() => setRoute({ tab: "premium" })}
            onMeStale={boot.reload}
          />
        )}
        {route.tab === "result" && (
          <ReadingResultPage
            readingId={route.readingId}
            onBack={() => setRoute({ tab: "home" })}
            onPremium={() => setRoute({ tab: "premium" })}
          />
        )}
        {route.tab === "history" && (
          <HistoryPage
            onOpen={(readingId) => setRoute({ tab: "result", readingId })}
            onPremium={() => setRoute({ tab: "premium" })}
          />
        )}
        {route.tab === "premium" && <PremiumPage me={me} onMeRefresh={boot.reload} />}
      </main>

      <nav className="tabbar" aria-label="Основная навигация">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={activeTab === t.id ? "active" : ""}
            onClick={() => setRoute({ tab: t.id })}
            aria-current={activeTab === t.id ? "page" : undefined}
          >
            <span className="tab-icon" aria-hidden="true">{t.icon}</span>
            <span>{t.label}</span>
          </button>
        ))}
      </nav>
    </div>
  );
}
