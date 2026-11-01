import { useEffect, useMemo, useRef, useState } from "react";
import type { ReadingCardOut } from "../types/api";
import { TarotCard } from "./CardVisual";

export type SpreadPhase = "idle" | "shuffling" | "dealing" | "revealed";

const SHUFFLE_MS = 1400;   // deck shuffle ritual
const DEAL_MS = 650;       // travel time of one card into its slot
const REVEAL_STEP_MS = 380; // interval between consecutive flips

interface Props {
  cards: ReadingCardOut[];
  spreadCode: string;
  /** Start the ritual (usually right after the API result is received). */
  autoStart?: boolean;
  onRevealed: () => void;
}

/**
 * Visualizes the reading returned by the backend: the cards shown here are
 * exactly the cards from the API response — the stage never picks cards itself.
 * Sequence: deck appears -> shuffle -> cards fly to layout slots -> sequential flip.
 * Honors prefers-reduced-motion (everything shows instantly).
 */
export function SpreadStage({ cards, spreadCode, autoStart = true, onRevealed }: Props) {
  const [phase, setPhase] = useState<SpreadPhase>(autoStart ? "shuffling" : "idle");
  const [placed, setPlaced] = useState(false);   // cards moved into their slots
  const [flipCount, setFlipCount] = useState(0); // how many cards are face-up
  const timers = useRef<number[]>([]);
  const doneRef = useRef(false);

  const reduced = useMemo(
    () => typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches,
    []
  );

  function clearTimers() {
    timers.current.forEach((t) => window.clearTimeout(t));
    timers.current = [];
  }

  function runRitual() {
    if (doneRef.current) return;
    clearTimers();
    if (reduced) {
      setPhase("revealed");
      setPlaced(true);
      setFlipCount(cards.length);
      doneRef.current = true;
      onRevealed();
      return;
    }
    setPhase("shuffling");
    setPlaced(false);
    setFlipCount(0);
    timers.current.push(
      window.setTimeout(() => {
        setPhase("dealing");
        // next frame -> cards translate into slots via CSS transition
        requestAnimationFrame(() => setPlaced(true));
        // start flipping once the last card has arrived
        timers.current.push(
          window.setTimeout(() => {
            cards.forEach((_, i) => {
              timers.current.push(
                window.setTimeout(() => setFlipCount((n) => Math.max(n, i + 1)), i * REVEAL_STEP_MS)
              );
            });
            const total = (cards.length - 1) * REVEAL_STEP_MS + 700;
            timers.current.push(
              window.setTimeout(() => {
                doneRef.current = true;
                setPhase("revealed");
                onRevealed();
              }, total)
            );
          }, DEAL_MS)
        );
      }, SHUFFLE_MS)
    );
  }

  useEffect(() => {
    if (autoStart) runRitual();
    return clearTimers;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cards, spreadCode]);

  const layoutClass =
    spreadCode === "celtic_cross"
      ? "spread-layout spread-layout--celtic"
      : cards.length === 1
        ? "spread-layout spread-layout--single"
        : "spread-layout spread-layout--row";

  return (
    <div className="spread-stage" data-phase={phase}>
      {phase !== "revealed" && phase !== "dealing" ? (
        <div className="deck" aria-hidden="true">
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className={`deck__card deck__card--${i}`} style={{ animationDelay: `${i * 90}ms` }} />
          ))}
        </div>
      ) : null}

      <div className={layoutClass}>
        {cards.map((c, i) => (
          <div
            key={c.position_number}
            className={[
              "slot",
              `slot--p${c.position_number}`,
              placed ? "slot--placed" : "slot--in-deck",
              i < flipCount ? "slot--flipped" : "",
            ].join(" ")}
            style={{ transitionDelay: placed ? `${i * 90}ms` : "0ms" }}
          >
            <div className="slot__card">
              <TarotCard card={c} size={spreadCode === "celtic_cross" ? "sm" : "md"} />
            </div>
            {phase === "revealed" || i < flipCount ? (
              <div className="slot__label">{c.position_number}. {c.position_name}</div>
            ) : null}
          </div>
        ))}
      </div>

      {phase === "idle" ? (
        <button className="btn" onClick={runRitual}>Раскрыть карты</button>
      ) : null}
    </div>
  );
}
