import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { ReadingCardOut } from "../types/api";
import { SpreadStage } from "./SpreadStage";
import { cardImage } from "./CardVisual";

function makeCards(n: number): ReadingCardOut[] {
  return Array.from({ length: n }, (_, i) => ({
    position_number: i + 1,
    position_code: `p${i + 1}`,
    position_name: `Позиция ${i + 1}`,
    card_id: i + 1,
    card_code: `major_0${i}_test`,
    card_name_ru: `Карта ${i + 1}`,
    orientation: "upright",
    rendered_text: "текст",
  }));
}

describe("SpreadStage", () => {
  it("renders exactly the cards received from backend (no self-picked cards)", () => {
    const cards = makeCards(3);
    render(<SpreadStage cards={cards} spreadCode="past_present_future" autoStart={false} onRevealed={() => {}} />);
    // idle phase shows the button; slots exist for every backend card
    expect(screen.getByRole("button", { name: /Раскрыть карты/i })).toBeTruthy();
    const imgs = document.querySelectorAll(".tcard__front img");
    expect(imgs.length).toBe(3);
    imgs.forEach((img, i) => {
      expect((img as HTMLImageElement).getAttribute("src")).toBe(`/cards/major_0${i}_test.webp`);
    });
  });

  it("shows cards instantly under reduced motion and calls onRevealed", () => {
    const mq = vi.spyOn(window, "matchMedia").mockImplementation((q: string) => ({
      matches: q.includes("prefers-reduced-motion"),
      media: q, onchange: null, addListener: vi.fn(), removeListener: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
    }) as unknown as MediaQueryList);
    const onRevealed = vi.fn();
    render(<SpreadStage cards={makeCards(1)} spreadCode="daily_card" onRevealed={onRevealed} />);
    expect(onRevealed).toHaveBeenCalled();
    expect(document.querySelectorAll(".slot--flipped").length).toBe(1);
    mq.mockRestore();
  });

  it("uses celtic layout class only for celtic_cross", () => {
    const a = render(<SpreadStage cards={makeCards(10)} spreadCode="celtic_cross" autoStart={false} onRevealed={() => {}} />);
    expect(document.querySelector(".spread-layout--celtic")).toBeTruthy();
    a.unmount();
    render(<SpreadStage cards={makeCards(3)} spreadCode="situation_advice_outcome" autoStart={false} onRevealed={() => {}} />);
    expect(document.querySelector(".spread-layout--row")).toBeTruthy();
  });

  it("maps card code to public/cards image path", () => {
    expect(cardImage("major_00_fool")).toBe("/cards/major_00_fool.webp");
  });
});
