import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useMemo, useState, type PropsWithChildren } from "react";
import { ApiError } from "../lib/errors";
import { getCurrentUser, hasAdminAccess, login, logout, type AuthenticatedUser } from "../lib/session";

type AuthStatus = "anonymous" | "authenticated";

type AuthContextValue = {
  error: ApiError | null;
  isBootstrapping: boolean;
  isLoggingIn: boolean;
  login: (credentials: { login: string; password: string }) => Promise<void>;
  logout: () => Promise<void>;
  status: AuthStatus;
  user: AuthenticatedUser | null;
};

const sessionQueryKey = ["session", "current-user"] as const;

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: PropsWithChildren) {
  const queryClient = useQueryClient();
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const sessionQuery = useQuery({
    queryKey: sessionQueryKey,
    queryFn: ({ signal }) => getCurrentUser(signal),
  });

  const value = useMemo<AuthContextValue>(() => {
    const user = sessionQuery.data ?? null;
    const error = sessionQuery.error instanceof ApiError ? sessionQuery.error : null;

    return {
      error,
      isBootstrapping: sessionQuery.isPending,
      isLoggingIn,
      async login(credentials) {
        setIsLoggingIn(true);
        try {
          const user = await login(credentials);
          queryClient.removeQueries({
            predicate: (query) => query.queryKey[0] !== "session",
          });
          queryClient.setQueryData(sessionQueryKey, user);
        } finally {
          setIsLoggingIn(false);
        }
      },
      async logout() {
        await logout();
        await queryClient.cancelQueries();
        queryClient.removeQueries({
          predicate: (query) => query.queryKey[0] !== "session",
        });
        queryClient.setQueryData(sessionQueryKey, null);
      },
      status: hasAdminAccess(user) ? "authenticated" : "anonymous",
      user,
    };
  }, [isLoggingIn, queryClient, sessionQuery.data, sessionQuery.error, sessionQuery.isPending]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error("AuthProvider is missing");
  }
  return context;
}
