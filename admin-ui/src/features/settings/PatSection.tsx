import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { CheckboxField, TextField } from "../../components/Field";
import { ApiErrorBanner } from "../../components/Form";
import { IconButton } from "../../components/IconButton";
import { NodeLinkSelect } from "../nodes/NodeLinkSelect";
import { OverlayCloseButton } from "../../components/OverlayCloseButton";
import { OverlayDialog } from "../../components/OverlayDialog";
import { ApiError } from "../../lib/api";
import { fromUtcDateTimeLocalValue, formatUtcDateTimeForDisplay } from "../../lib/dateTime";
import { getReferenceId } from "../../lib/references";
import { localizeUnknownError } from "../../lib/errors";
import { EPHEMERAL_NODE_QUERY_OPTIONS } from "../../lib/queryOptions";
import type { AuthenticatedUser } from "../../lib/session";
import type { TranslationKey } from "../../locales";
import { useI18n } from "../../providers/I18nProvider";
import { useAuth } from "../../providers/AuthProvider";
import { getLinkableNodesByIds, type NodeDocument } from "../nodes/api";
import {
  createPat,
  listPats,
  revokePat,
  rotatePat,
  type CreatePatPayload,
  type PatActionResult,
  type PatDocument,
} from "./patApi";

type PatAction = "revoke" | "rotate";

export function PatSection() {
  const auth = useAuth();
  const { locale, t } = useI18n();
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [action, setAction] = useState<{ kind: PatAction; pat: PatDocument } | null>(null);
  const [newToken, setNewToken] = useState<string | null>(null);
  const patsQuery = useQuery({
    ...EPHEMERAL_NODE_QUERY_OPTIONS,
    queryKey: ["auth", "pats"],
    queryFn: ({ signal }) => listPats(signal),
  });
  const subjectIds = [...new Set((patsQuery.data ?? []).map((pat) => pat.subject_id))];
  const subjectsQuery = useQuery({
    ...EPHEMERAL_NODE_QUERY_OPTIONS,
    enabled: subjectIds.length > 0,
    queryKey: ["auth", "pat-subjects", subjectIds.join("|")],
    queryFn: ({ signal }) => getLinkableNodesByIds({
      entityNames: ["user"],
      ids: subjectIds,
      moduleName: "users",
      signal,
    }),
  });
  const isSuperuser = auth.user?.role === "superuser" || Boolean(auth.user?.superuser);
  const apiError = patsQuery.error instanceof ApiError ? patsQuery.error : undefined;
  const error = patsQuery.error === null ? null : patsQuery.error === undefined ? null : localizeUnknownError(patsQuery.error, t);
  const subjectLabels = new Map(
    (subjectsQuery.data ?? []).flatMap((node) => {
      const id = typeof node.id === "string" ? node.id : "";
      const username = typeof node.username === "string" ? node.username : "";
      return id.length > 0 && username.length > 0 ? [[id, username] as const] : [];
    }),
  );

  function reloadPats() {
    void patsQuery.refetch();
  }

  return (
    <div className="settings-pat-page">
      <Card
        title={
          <div className="panel-header-actions">
            <strong>{t("pages.settings.pat.title")}</strong>
            <Button onClick={() => setIsCreateOpen(true)} type="button">{t("pages.settings.pat.create")}</Button>
          </div>
        }
      >
        <p className="card-subtitle">{t("pages.settings.pat.description")}</p>
        {error ? <ApiErrorBanner error={apiError} message={error} /> : null}
        {patsQuery.isPending ? (
          <div className="settings-pat-message">{t("common.loading")}</div>
        ) : patsQuery.data === undefined ? null : patsQuery.data.length === 0 ? (
          <div className="settings-pat-message">{t("pages.settings.pat.empty")}</div>
        ) : (
          <PatTable
            locale={locale}
            onAction={setAction}
            pats={patsQuery.data}
            subjectLabels={subjectLabels}
            t={t}
          />
        )}
      </Card>

      {isCreateOpen ? (
        <PatCreateOverlay
          isSuperuser={isSuperuser}
          onClose={() => setIsCreateOpen(false)}
          onCreated={(pat) => {
            setIsCreateOpen(false);
            setNewToken(pat.token ?? null);
            reloadPats();
          }}
          user={auth.user}
        />
      ) : null}
      {action !== null ? (
        <PatActionOverlay
          action={action.kind}
          onClose={() => setAction(null)}
          onCompleted={(pat) => {
            setAction(null);
            if (action.kind === "rotate") {
              setNewToken(pat.token ?? null);
            }
            reloadPats();
          }}
          pat={action.pat}
        />
      ) : null}
      {newToken !== null ? <PatTokenOverlay onClose={() => setNewToken(null)} token={newToken} /> : null}
    </div>
  );
}

function PatTable(args: {
  locale: string;
  onAction: (action: { kind: PatAction; pat: PatDocument }) => void;
  pats: PatDocument[];
  subjectLabels: Map<string, string>;
  t: (key: TranslationKey) => string;
}) {
  return (
    <div className="settings-pat-table-wrap">
      <table className="settings-pat-table">
        <thead>
          <tr>
            <th scope="col">{args.t("pages.settings.pat.name")}</th>
            <th scope="col">{args.t("pages.settings.pat.subject")}</th>
            <th scope="col">{args.t("pages.settings.pat.expires")}</th>
            <th scope="col">{args.t("pages.settings.pat.status")}</th>
            <th scope="col"><span className="visually-hidden">{args.t("pages.settings.pat.actions")}</span></th>
          </tr>
        </thead>
        <tbody>
          {args.pats.map((pat) => (
            <tr key={pat.id}>
              <th scope="row">{pat.name}</th>
              <td>{args.subjectLabels.get(pat.subject_id) ?? pat.subject_id}</td>
              <td>{formatPatDate(pat.expires_at, args.locale, args.t("pages.settings.pat.never"))}</td>
              <td><PatStatus pat={pat} t={args.t} /></td>
              <td>
                <div className="settings-pat-actions">
                  <IconButton
                    disabled={pat.revoked_at !== null}
                    icon="nodes-reload"
                    label={args.t("pages.settings.pat.rotate")}
                    onClick={() => args.onAction({ kind: "rotate", pat })}
                    size="regular"
                  />
                  <IconButton
                    disabled={pat.revoked_at !== null}
                    icon="trash"
                    label={args.t("pages.settings.pat.revoke")}
                    onClick={() => args.onAction({ kind: "revoke", pat })}
                    size="regular"
                  />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PatStatus(args: { pat: PatDocument; t: (key: TranslationKey) => string }) {
  const { t } = args;
  const status = args.pat.revoked_at !== null
    ? "revoked"
    : args.pat.expires_at !== null && Date.parse(args.pat.expires_at) <= Date.now()
      ? "expired"
      : "active";
  return <span className={`settings-pat-status is-${status}`}>{t(`pages.settings.pat.status.${status}`)}</span>;
}

function PatCreateOverlay(args: {
  isSuperuser: boolean;
  onClose: () => void;
  onCreated: (pat: PatDocument) => void;
  user: AuthenticatedUser | null;
}) {
  const { t } = useI18n();
  const [name, setName] = useState("");
  const [subject, setSubject] = useState<NodeDocument | null>(() => toUserNode(args.user));
  const [expiresAt, setExpiresAt] = useState("");
  const [neverExpires, setNeverExpires] = useState(false);
  const [nameError, setNameError] = useState<string | undefined>();
  const [subjectError, setSubjectError] = useState<string | undefined>();
  const [expiresError, setExpiresError] = useState<string | undefined>();
  const mutation = useMutation({
    mutationFn: (payload: CreatePatPayload) => createPat(payload),
    onSuccess: args.onCreated,
  });
  const apiError = mutation.error instanceof ApiError ? mutation.error : undefined;
  const error = mutation.error === null ? null : mutation.error === undefined ? null : localizeUnknownError(mutation.error, t);
  const subjectId = args.isSuperuser ? getReferenceId(subject) : getReferenceId(args.user?.id);

  function submit() {
    setNameError(undefined);
    setSubjectError(undefined);
    setExpiresError(undefined);
    if (name.trim().length === 0) {
      setNameError(t("pages.settings.pat.validation.name"));
      return;
    }
    if (subjectId.length === 0) {
      setSubjectError(t("pages.settings.pat.validation.subject"));
      return;
    }

    let expiresAtPayload: string | null | undefined;
    if (neverExpires) {
      expiresAtPayload = null;
    } else if (expiresAt.length > 0) {
      const normalizedExpiresAt = fromUtcDateTimeLocalValue(expiresAt);
      if (normalizedExpiresAt.length === 0) {
        setExpiresError(t("pages.settings.pat.validation.expires"));
        return;
      }
      expiresAtPayload = normalizedExpiresAt;
    }

    mutation.mutate({
      ...(expiresAtPayload === undefined ? {} : { expires_at: expiresAtPayload }),
      name: name.trim(),
      subject_id: subjectId,
    });
  }

  return (
    <OverlayDialog ariaLabel={t("pages.settings.pat.createTitle")} className="overlay-dialog-field" onClose={args.onClose}>
      <div className="field-overlay-header">
        <strong>{t("pages.settings.pat.createTitle")}</strong>
        <OverlayCloseButton onClick={args.onClose} />
      </div>
      <div className="field-overlay-body settings-pat-form">
        <TextField autoFocus error={nameError} label={t("pages.settings.pat.name")} onChange={(event) => { setName(event.target.value); setNameError(undefined); }} value={name} />
        {args.isSuperuser ? (
          <NodeLinkSelect
            canWrite
            error={subjectError}
            label={t("pages.settings.pat.subject")}
            mode="single"
            onBlur={() => undefined}
            onChange={(value) => {
              setSubject(Array.isArray(value) ? null : value);
              setSubjectError(undefined);
            }}
            placeholder={t("pages.nodes.editor.linkPlaceholder")}
            targetEntities={["user"]}
            targetModule="users"
            value={subject}
          />
        ) : (
          <TextField label={t("pages.settings.pat.subject")} readOnly value={args.user?.username ?? args.user?.id ?? ""} />
        )}
        <label className="field">
          <span className="field-label">{t("pages.settings.pat.expires")}</span>
          <div className="datetime-control">
            <input
              className="field-control"
              disabled={neverExpires}
              onChange={(event) => {
                setExpiresAt(event.target.value);
                setExpiresError(undefined);
              }}
              step={60}
              type="datetime-local"
              value={expiresAt}
            />
            <span className="datetime-zone">{t("common.utc")}</span>
          </div>
          {expiresError ? <span className="field-error">{expiresError}</span> : null}
        </label>
        <CheckboxField checked={neverExpires} label={t("pages.settings.pat.neverExpires")} onChange={(event) => setNeverExpires(event.target.checked)} />
        <p className="settings-pat-hint">{t("pages.settings.pat.defaultExpiry")}</p>
      </div>
      <div className="field-overlay-footer">
        {error ? <ApiErrorBanner error={apiError} message={error} /> : null}
        <div className="field-overlay-actions">
          <Button kind="ghost" onClick={args.onClose} type="button">{t("common.cancel")}</Button>
          <Button disabled={mutation.isPending} onClick={submit} type="button">{mutation.isPending ? t("pages.settings.pat.creating") : t("common.create")}</Button>
        </div>
      </div>
    </OverlayDialog>
  );
}

function PatActionOverlay(args: {
  action: PatAction;
  onClose: () => void;
  onCompleted: (pat: PatActionResult) => void;
  pat: PatDocument;
}) {
  const { t } = useI18n();
  const mutation = useMutation({
    mutationFn: () => args.action === "revoke" ? revokePat(args.pat.id) : rotatePat(args.pat.id),
    onSuccess: args.onCompleted,
  });
  const apiError = mutation.error instanceof ApiError ? mutation.error : undefined;
  const error = mutation.error === null ? null : mutation.error === undefined ? null : localizeUnknownError(mutation.error, t);
  const title = t(args.action === "revoke" ? "pages.settings.pat.revokeTitle" : "pages.settings.pat.rotateTitle");

  return (
    <OverlayDialog ariaLabel={title} className="overlay-dialog-field" onClose={args.onClose}>
      <div className="field-overlay-header">
        <strong>{title}</strong>
        <OverlayCloseButton onClick={args.onClose} />
      </div>
      <div className="field-overlay-body">
        <p>{t(args.action === "revoke" ? "pages.settings.pat.revokeConfirm" : "pages.settings.pat.rotateConfirm")} <strong>{args.pat.name}</strong></p>
      </div>
      <div className="field-overlay-footer">
        {error ? <ApiErrorBanner error={apiError} message={error} /> : null}
        <div className="field-overlay-actions">
          <Button kind="ghost" onClick={args.onClose} type="button">{t("common.cancel")}</Button>
          <Button className={args.action === "revoke" ? "ui-button-danger" : ""} disabled={mutation.isPending} onClick={() => mutation.mutate()} type="button">
            {mutation.isPending ? t("pages.settings.pat.processing") : t(args.action === "revoke" ? "pages.settings.pat.revoke" : "pages.settings.pat.rotate")}
          </Button>
        </div>
      </div>
    </OverlayDialog>
  );
}

function PatTokenOverlay(args: { onClose: () => void; token: string }) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);

  async function copyToken() {
    try {
      await navigator.clipboard.writeText(args.token);
      setCopied(true);
      setCopyError(false);
    } catch {
      setCopyError(true);
    }
  }

  return (
    <OverlayDialog ariaLabel={t("pages.settings.pat.tokenTitle")} className="overlay-dialog-field" onClose={args.onClose}>
      <div className="field-overlay-header">
        <strong>{t("pages.settings.pat.tokenTitle")}</strong>
        <OverlayCloseButton onClick={args.onClose} />
      </div>
      <div className="field-overlay-body settings-pat-token-body">
        <p>{t("pages.settings.pat.tokenWarning")}</p>
        <code className="settings-pat-token">{args.token}</code>
        <Button kind="ghost" onClick={() => void copyToken()} type="button">{copied ? t("pages.settings.pat.copied") : t("pages.settings.pat.copy")}</Button>
        {copyError ? <span className="field-error">{t("pages.settings.pat.copyError")}</span> : null}
      </div>
      <div className="field-overlay-footer">
        <div className="field-overlay-actions">
          <Button onClick={args.onClose} type="button">{t("common.close")}</Button>
        </div>
      </div>
    </OverlayDialog>
  );
}

function formatPatDate(value: string | null, locale: string, neverLabel: string) {
  if (value === null) {
    return neverLabel;
  }
  return formatUtcDateTimeForDisplay(value, locale);
}

function toUserNode(user: AuthenticatedUser | null): NodeDocument | null {
  if (user === null || user.id.length === 0) {
    return null;
  }
  return { entity: "user", id: user.id, username: user.username ?? user.login };
}
