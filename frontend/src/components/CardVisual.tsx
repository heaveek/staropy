import type { ReadingCardOut } from "../types/api";

/** Map card code -> image path under public/cards (backend contract: /cards/<code>.webp). */
export function cardImage(code: string): string {
  return `/cards/${encodeURIComponent(code)}.webp`;
}

interface CardFaceProps {
  card: ReadingCardOut;
  size?: "md" | "sm";
}

/** A single card with a CSS-drawn back and the real artwork on the front. */
export function TarotCard({ card, size = "md" }: CardFaceProps) {
  return (
    <div className={`tcard tcard--${size}`}>
      <div className="tcard__inner">
        <div className="tcard__face tcard__back" aria-hidden="true">
          <div className="tcard__back-frame">
            <span className="tcard__star">✦</span>
          </div>
        </div>
        <div className="tcard__face tcard__front">
          <img
            src={cardImage(card.card_code)}
            alt={card.card_name_ru}
            loading="lazy"
            draggable={false}
          />
          {card.orientation === "reversed" ? (
            <span className="tcard__rev-badge">↓</span>
          ) : null}
        </div>
      </div>
    </div>
  );
}
