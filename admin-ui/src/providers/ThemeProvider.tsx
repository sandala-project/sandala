import { createContext, useContext, useEffect, useMemo, useState, type PropsWithChildren } from "react";

type ThemeName = "light" | "dark";

type ThemeContextValue = {
  setTheme: (theme: ThemeName) => void;
  theme: ThemeName;
  toggleTheme: () => void;
};

const storageKey = "sandala-admin-ui.theme";

const ThemeContext = createContext<ThemeContextValue | null>(null);

function getInitialTheme(): ThemeName {
  const saved = window.localStorage.getItem(storageKey);
  return saved === "dark" ? "dark" : "light";
}

export function ThemeProvider({ children }: PropsWithChildren) {
  const [theme, setTheme] = useState<ThemeName>(() => getInitialTheme());

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem(storageKey, theme);
  }, [theme]);

  const value = useMemo<ThemeContextValue>(
    () => ({
      setTheme,
      theme,
      toggleTheme: () => setTheme((current) => (current === "light" ? "dark" : "light")),
    }),
    [theme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (context === null) {
    throw new Error("ThemeProvider is missing");
  }
  return context;
}
