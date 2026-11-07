import { useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { Card } from "../components/Card";
import { SplitPane } from "../components/SplitPane";
import { NodeEditorLoader } from "../features/nodes/NodeEditorLoader";
import { PatSection } from "../features/settings/PatSection";
import { useAuth } from "../providers/AuthProvider";
import { useI18n } from "../providers/I18nProvider";
import { APP_ROUTE_PREFIX } from "../router/routeConfig";

type SettingsSection = "profile" | "pat";

export function SettingsPage() {
  const auth = useAuth();
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [section, setSection] = useState<SettingsSection>("profile");

  return (
    <section className="settings-screen">
      <SplitPane
        className="settings-layout"
        defaultSidebarWidth={240}
        minMainWidth={560}
        storageKey="sandala.admin-ui.settings.split-pane"
      >
        <aside className="settings-sidebar">
          <Card title={<strong>{t("pages.settings.title")}</strong>}>
            <nav aria-label={t("pages.settings.navigation")} className="settings-nav">
              <button
                aria-current={section === "profile" ? "page" : undefined}
                className={`settings-nav-item ${section === "profile" ? "is-active" : ""}`.trim()}
                onClick={() => setSection("profile")}
                type="button"
              >
                {t("pages.settings.profile")}
              </button>
              <Link className="settings-nav-item settings-nav-link" params={{ entity: "user", module: "users" }} to={`${APP_ROUTE_PREFIX}/nodes/table/$module/$entity`}>
                {t("pages.settings.users")}
              </Link>
              <Link className="settings-nav-item settings-nav-link" params={{ entity: "group", module: "users" }} to={`${APP_ROUTE_PREFIX}/nodes/table/$module/$entity`}>
                {t("pages.settings.groups")}
              </Link>
              <button
                aria-current={section === "pat" ? "page" : undefined}
                className={`settings-nav-item ${section === "pat" ? "is-active" : ""}`.trim()}
                onClick={() => setSection("pat")}
                type="button"
              >
                {t("pages.settings.pat")}
              </button>
            </nav>
          </Card>
        </aside>

        <div className="settings-main">
          {section === "profile" && auth.user !== null ? (
            <NodeEditorLoader
              moduleName="users"
              nodeId={auth.user.id}
              onSaved={() => {
                void queryClient.invalidateQueries({ queryKey: ["session", "current-user"] });
              }}
              variant="full"
            />
          ) : section === "pat" ? (
            <PatSection />
          ) : null}
        </div>
      </SplitPane>
    </section>
  );
}
