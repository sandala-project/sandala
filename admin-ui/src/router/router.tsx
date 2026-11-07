import {
  Navigate,
  Outlet,
  createRootRouteWithContext,
  createRoute,
  createRouter,
  redirect,
} from "@tanstack/react-router";
import { AppShell } from "../components/AppShell";
import { appConfig } from "../lib/config";
import { LoginPage } from "../pages/LoginPage";
import { EntitiesPage } from "../pages/EntitiesPage";
import { NodesPage } from "../pages/NodesPage";
import { SettingsPage } from "../pages/SettingsPage";
import { useAuth } from "../providers/AuthProvider";
import type { useI18n } from "../providers/I18nProvider";
import type { useTheme } from "../providers/ThemeProvider";
import { APP_ROUTE_PREFIX } from "./routeConfig";

type RouterContext = {
  auth: ReturnType<typeof useAuth>;
  i18n: ReturnType<typeof useI18n>;
  theme: ReturnType<typeof useTheme>;
};

const rootRoute = createRootRouteWithContext<RouterContext>()({
  component: Outlet,
});

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: `${APP_ROUTE_PREFIX}/login`,
  component: LoginPage,
  validateSearch: (search): { redirect?: string } => ({
    redirect: typeof search.redirect === "string" ? search.redirect : undefined,
  }),
});

const protectedRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "protected",
  component: ProtectedRoute,
});

function ProtectedRoute() {
  const auth = useAuth();
  const currentHref = getCurrentAppHref();

  if (
    !auth.isBootstrapping &&
    auth.user === null &&
    (auth.error === null || auth.error.status === 401)
  ) {
    return <Navigate replace search={{ redirect: currentHref }} to={`${APP_ROUTE_PREFIX}/login`} />;
  }

  return <AppShell />;
}

const indexRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: "/",
  beforeLoad: () => {
    throw redirect({ to: `${APP_ROUTE_PREFIX}/nodes` });
  },
});

const nodesRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: `${APP_ROUTE_PREFIX}/nodes`,
  component: () => <Navigate to={`${APP_ROUTE_PREFIX}/nodes/tree`} />,
});

const nodesTreeRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: `${APP_ROUTE_PREFIX}/nodes/tree`,
  component: () => <NodesPage mode="tree" />,
});

const nodesTreeModuleRoute = createRoute({
  getParentRoute: () => nodesTreeRoute,
  path: "$module",
  component: () => null,
});

const nodesTreeNodeRoute = createRoute({
  getParentRoute: () => nodesTreeModuleRoute,
  path: "$nodeId",
  component: () => null,
});

const nodesTableRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: `${APP_ROUTE_PREFIX}/nodes/table`,
  component: () => <NodesPage mode="table" />,
});

const nodesTableModuleRoute = createRoute({
  getParentRoute: () => nodesTableRoute,
  path: "$module",
  component: () => null,
});

const nodesTableEntityRoute = createRoute({
  getParentRoute: () => nodesTableModuleRoute,
  path: "$entity",
  component: () => null,
});

const entitiesRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: `${APP_ROUTE_PREFIX}/entities`,
  component: EntitiesPage,
});

const entitiesModuleRoute = createRoute({
  getParentRoute: () => entitiesRoute,
  path: "$module",
  component: () => null,
});

const entitiesEntityRoute = createRoute({
  getParentRoute: () => entitiesModuleRoute,
  path: "$entity",
  component: () => null,
});

const settingsRoute = createRoute({
  getParentRoute: () => protectedRoute,
  path: `${APP_ROUTE_PREFIX}/settings`,
  component: SettingsPage,
});

const routeTree = rootRoute.addChildren([
  loginRoute,
  protectedRoute.addChildren([
    indexRoute,
    nodesRoute,
    nodesTreeRoute.addChildren([
      nodesTreeModuleRoute.addChildren([nodesTreeNodeRoute]),
    ]),
    nodesTableRoute.addChildren([nodesTableModuleRoute.addChildren([nodesTableEntityRoute])]),
    entitiesRoute.addChildren([
      entitiesModuleRoute.addChildren([entitiesEntityRoute]),
    ]),
    settingsRoute,
  ]),
]);

export const router = createRouter({
  routeTree,
  basepath: appConfig.basePath,
  context: {
    auth: undefined!,
    i18n: undefined!,
    theme: undefined!,
  },
  defaultPreload: "intent",
});

function getCurrentAppHref() {
  const { hash, pathname, search } = window.location;
  const basePath = appConfig.basePath === "/" ? "" : appConfig.basePath.replace(/\/$/, "");
  const appPath = basePath.length > 0 && (pathname === basePath || pathname.startsWith(`${basePath}/`))
    ? pathname.slice(basePath.length) || "/"
    : pathname;

  return `${appPath}${search}${hash}`;
}

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
