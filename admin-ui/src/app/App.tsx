import { RouterProvider } from "@tanstack/react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { router } from "../router/router";
import { AuthProvider, useAuth } from "../providers/AuthProvider";
import { I18nProvider, useI18n } from "../providers/I18nProvider";
import { ThemeProvider, useTheme } from "../providers/ThemeProvider";

function AppProviders() {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            refetchOnWindowFocus: false,
            retry: false,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <I18nProvider>
          <AuthProvider>
            <RoutedApp />
          </AuthProvider>
        </I18nProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

function RoutedApp() {
  const auth = useAuth();
  const theme = useTheme();
  const i18n = useI18n();

  return <RouterProvider router={router} context={{ auth, theme, i18n }} />;
}

export function App() {
  return <AppProviders />;
}
