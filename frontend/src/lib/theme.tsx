import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

type Theme = "dark" | "light";
const KEY = "agentCoachTheme"; // same key as v2, so saved preferences carry over

function initial(): Theme {
  const attr = document.documentElement.getAttribute("data-theme");
  if (attr === "dark" || attr === "light") return attr;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

const Ctx = createContext<{ theme: Theme; toggle: () => void }>({ theme: "dark", toggle: () => {} });

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(initial);
  const toggle = useCallback(() => {
    setTheme((t) => {
      const next: Theme = t === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      try { localStorage.setItem(KEY, next); } catch { /* storage blocked */ }
      return next;
    });
  }, []);
  return <Ctx.Provider value={{ theme, toggle }}>{children}</Ctx.Provider>;
}

export const useTheme = () => useContext(Ctx);

/** Chart palette read from the live CSS variables (v2's PAL()). */
export function palette(theme: Theme) {
  const css = getComputedStyle(document.documentElement);
  const g = (n: string) => css.getPropertyValue(n).trim();
  const dark = theme === "dark";
  return {
    people: g("--people-dark"), process: g("--process-dark"), green: g("--green"), amber: g("--amber"), red: g("--red"),
    om: g("--om-dark"), ink: g("--ink"), muted: g("--ink-muted"), faint: g("--ink-faint"),
    grid: dark ? "rgba(255,255,255,.08)" : "rgba(11,11,11,.08)", tick: g("--ink-faint"),
    tooltipBg: dark ? "#14201c" : "#ffffff", track: dark ? "rgba(255,255,255,.08)" : "rgba(11,11,11,.08)",
  };
}
