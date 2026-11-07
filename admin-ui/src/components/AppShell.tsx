import { Link, Outlet } from "@tanstack/react-router";
import sandalaIcon from "../assets/sandala-icon.svg";
import { DropdownMenu } from "./DropdownMenu";
import { EmptyState } from "./EmptyState";
import { Icon } from "./Icon";
import { Panel } from "./Panel";
import { Button } from "./Button";
import { CompactOptionMenu } from "./CompactOptionMenu";
import { TopbarContentProvider, TopbarContentTarget } from "./TopbarContent";
import { useAuth } from "../providers/AuthProvider";
import { useI18n } from "../providers/I18nProvider";
import { useTheme } from "../providers/ThemeProvider";
import { appConfig } from "../lib/config";
import { canEditEntities, hasAdminAccess } from "../lib/session";
import { localeOptions } from "../locales";
import { APP_ROUTE_PREFIX } from "../router/routeConfig";

export function AppShell() {
  const auth = useAuth();
  const { t, locale, setLocale } = useI18n();
  const { theme, toggleTheme } = useTheme();

  if (auth.isBootstrapping) {
    return <ShellMessage message={t("common.loading")} />;
  }

  if (auth.error !== null && auth.error.status !== 401) {
    return <ShellMessage message={t("errors.session")} />;
  }

  if (!hasAdminAccess(auth.user)) {
    return (
      <ShellMessage
        action={
          <Button kind="ghost" onClick={() => void auth.logout()}>
            {t("errors.forbidden.switchAccount")}
          </Button>
        }
        message={t("errors.forbidden")}
      />
    );
  }

  const accountLabel = auth.user?.username ?? auth.user?.login ?? t("common.account");
  const userInitials = accountLabel.slice(0, 2).toUpperCase() || "??";
  const avatarUrl = getAvatarUrl(auth.user?.avatar);
  const entitiesMeta = canEditEntities(auth.user) ? "" : t("nav.entities.readOnly");
  const localeLabel = t(localeOptions.find((option) => option.value === locale)?.label ?? "locale.english");
  const themeValue = theme === "light" ? t("theme.light") : t("theme.dark");

  return (
    <TopbarContentProvider>
      <div className="app-shell">
        <header className="topbar">
          <Link aria-label={appConfig.appName} className="brand" title={appConfig.appName} to={`${APP_ROUTE_PREFIX}/nodes`}>
            <img alt="" className="brand-mark" height={38} src={sandalaIcon} width={38} />
          </Link>

          <TopbarContentTarget />

          <div className="topbar-right">
            <DropdownMenu
              footer={
                <div className="menu-preferences">
                  <div className="menu-section-title">{t("menu.preferences")}</div>
                  <CompactOptionMenu
                    buttonLabel={t("menu.language")}
                    className="menu-language-options"
                    onChange={setLocale}
                    options={localeOptions.map((option) => ({ label: t(option.label), value: option.value }))}
                    portal
                    triggerContent={
                      <>
                        <span>{t("menu.language")}</span>
                        <span className="dropdown-meta">{localeLabel}</span>
                      </>
                    }
                    value={locale}
                  />
                  <button className="dropdown-item" onClick={toggleTheme} type="button">
                    <span>{t("menu.theme")}</span>
                    <span className="dropdown-meta">{themeValue}</span>
                  </button>
                  <button className="dropdown-item dropdown-divider" onClick={() => void auth.logout()} type="button">
                    <span>{t("common.logout")}</span>
                  </button>
                </div>
              }
              label={accountLabel}
              items={[
                { label: t("nav.nodes"), to: `${APP_ROUTE_PREFIX}/nodes` },
                { label: t("nav.entities"), meta: entitiesMeta, to: `${APP_ROUTE_PREFIX}/entities` },
                { label: t("nav.settings"), to: `${APP_ROUTE_PREFIX}/settings` },
              ]}
              trigger={
                <button aria-label={accountLabel} className="account-trigger" title={accountLabel} type="button">
                  <span className="avatar">
                    {avatarUrl ? <img alt="" className="avatar-image" src={avatarUrl} /> : userInitials}
                  </span>
                  <Icon className="account-chevron-icon" name="chevron-down" size="small" weight="strong" />
                </button>
              }
            />
          </div>
        </header>

        <main className="workspace">
          <Outlet />
        </main>
      </div>
    </TopbarContentProvider>
  );
}

function getAvatarUrl(value: unknown) {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }

  const url = (value as { url?: unknown }).url;
  return typeof url === "string" && url.trim().length > 0 ? url.trim() : null;
}

function ShellMessage({ action, message }: { action?: React.ReactNode; message: string }) {
  return (
    <div className="fullscreen">
      <Panel>
        <EmptyState description={message} title={appConfig.appName} />
        {action ? <div className="shell-message-action">{action}</div> : null}
      </Panel>
    </div>
  );
}
