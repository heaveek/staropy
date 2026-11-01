import "@testing-library/jest-dom/vitest";

// jsdom does not implement matchMedia. Tests that need reduced-motion behavior
// override this with vi.spyOn(window, "matchMedia").
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});
