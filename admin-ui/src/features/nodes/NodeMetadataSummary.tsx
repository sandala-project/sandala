import { IconButton } from "../../components/IconButton";
import { formatUtcDateTimeForDisplay } from "../../lib/dateTime";
import type { TranslationKey } from "../../locales";
import type { NodeDocument } from "./api";

export function NodeMetadataSummary(args: { locale: string; node: NodeDocument; t: (key: TranslationKey) => string }) {
  return (
    <div className="node-editor-metadata">
      <div className="node-editor-metadata-grid">
        <MetadataValue copyLabel={args.t("pages.nodes.editor.copyId")} label={args.t("nodes.systemFields.id")} value={args.node.id} />
        <MetadataValue label={args.t("nodes.systemFields.cdate")} value={formatUtcDateTimeForDisplay(args.node.cdate, args.locale)} />
        <MetadataValue label={args.t("nodes.systemFields.mdate")} value={formatUtcDateTimeForDisplay(args.node.mdate, args.locale)} />
      </div>
    </div>
  );
}

function MetadataValue(args: { copyLabel?: string; label: string; value: string | undefined }) {
  const hasValue = typeof args.value === "string" && args.value.length > 0;

  return (
    <div className="node-editor-metadata-value">
      <div className="field-label">{args.label}</div>
      <div className="node-editor-metadata-value-row">
        <div className="node-editor-metadata-text">{args.value || "—"}</div>
        {args.copyLabel !== undefined && hasValue ? (
          <IconButton
            className="node-editor-metadata-copy"
            icon="copy"
            label={args.copyLabel}
            onClick={() => {
              void copyToClipboard(args.value!);
            }}
            variant="bare"
          />
        ) : null}
      </div>
    </div>
  );
}

async function copyToClipboard(value: string) {
  try {
    await navigator.clipboard.writeText(value);
  } catch {
    // Clipboard access is unavailable in some non-secure browser contexts.
  }
}
