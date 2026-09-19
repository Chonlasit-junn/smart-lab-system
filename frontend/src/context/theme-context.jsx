import { useEffect, useMemo, useState } from "react";
import { ThemeContext } from "./theme-context.js";

const THEME_STORAGE_KEY = "smart-lab-theme";

function getInitialTheme() {
  if (typeof window === "undefined") return "light";

  const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
  if (storedTheme === "light" || storedTheme === "dark") return storedTheme;

  return window.matchMedia?.("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

export function ThemeProvider({ children }) {
  const [mode, setMode] = useState(getInitialTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = mode;
    document.documentElement.style.colorScheme = mode;
    window.localStorage.setItem(THEME_STORAGE_KEY, mode);
  }, [mode]);

  const value = useMemo(
    () => ({
      mode,
      isDark: mode === "dark",
      setMode,
      toggleTheme: () => setMode((currentMode) => (currentMode === "dark" ? "light" : "dark")),
    }),
    [mode],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
