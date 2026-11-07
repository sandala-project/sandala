import { Navigate, useSearch } from "@tanstack/react-router";
import { LoginForm } from "../features/auth/LoginForm";
import { Spinner } from "../components/Spinner";
import { useAuth } from "../providers/AuthProvider";
import { APP_ROUTE_PREFIX } from "../router/routeConfig";

export function LoginPage() {
  const auth = useAuth();
  const { redirect } = useSearch({ from: `${APP_ROUTE_PREFIX}/login` });

  if (auth.isBootstrapping) {
    return (
      <div className="fullscreen">
        <Spinner />
      </div>
    );
  }

  if (auth.user !== null) {
    return <Navigate to={getInternalRedirect(redirect)} />;
  }

  return (
    <div className="fullscreen auth-screen">
      <LoginForm />
    </div>
  );
}

function getInternalRedirect(redirect: string | undefined) {
  return redirect !== undefined && redirect.startsWith("/") && !redirect.startsWith("//")
    ? redirect
    : `${APP_ROUTE_PREFIX}/nodes`;
}
