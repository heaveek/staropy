import { useState } from "react";
import type { Catalog, Me, Spread, Theme } from "../types/api";
import { Screen } from "./common";

interface Props {
  me: Me;
  catalog: Catalog;
  onStart: (spread: Spread, theme: Theme) => void;
}

/** Home: spread picker with real backend data + quota strip. */
export function HomePage({ me, catalog, onStart }: Props) {
  const [themeCode, setThemeCode] = useState<string>(catalog.themes[0]?.code ?? "");
  const theme = catalog.themes.find((t) => t.code === themeCode) ?? null;

  return (
    <Screen title="Таро-расклады" subtitle={`Выберите тему и расклад. ${me.first_name ? `Привет, ${me.first_name}.` : ""}`}>
      <div className="quota-strip">
        {me.premium.is_premium ? (
          <span className="badge premium">Premium</span>
        ) : (
          <span className="badge">
            Бесплатно сегодня: {me.quota.free_readings_remaining} из {me.quota.free_readings_per_day}
          </span>
        )}
      </div>

      <h2>Тема</h2>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {catalog.themes.map((t) => (
          <button
            key={t.code}
            className={t.code === themeCode ? "btn secondary" : "btn ghost"}
            style={{ width: "auto", padding: "8px 14px", minWidth: 0 }}
            onClick={() => setThemeCode(t.code)}
            aria-pressed={t.code === themeCode}
          >
            {t.name_ru}
          </button>
        ))}
      </div>
      {theme?.description ? <p className="muted" style={{ marginTop: 8 }}>{theme.description}</p> : null}

      <h2>Расклад</h2>
      {catalog.spreads.map((s) => (
        <div
          key={s.code}
          className={`card selectable${!s.is_premium || me.premium.is_premium ? "" : ""}`}
          role="button"
          tabIndex={0}
          onClick={() => theme && onStart(s, theme)}
          onKeyDown={(e) => {
            if ((e.key === "Enter" || e.key === " ") && theme) onStart(s, theme);
          }}
        >
          <div className="card-title">
            {s.name_ru}
            <span className="badge">{s.card_count} {cardWord(s.card_count)}</span>
            {s.is_premium ? <span className="badge premium">Premium</span> : null}
          </div>
          {s.description ? <div className="card-desc">{s.description}</div> : null}
        </div>
      ))}
    </Screen>
  );
}

function cardWord(n: number): string {
  if (n === 1) return "карта";
  if (n >= 2 && n <= 4) return "карты";
  return "карт";
}
