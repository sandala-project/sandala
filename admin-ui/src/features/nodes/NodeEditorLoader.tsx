import { useQuery } from "@tanstack/react-query";
import { Spinner } from "../../components/Spinner";
import { localizeUnknownError } from "../../lib/errors";
import { EPHEMERAL_NODE_QUERY_OPTIONS, SCHEMA_QUERY_OPTIONS } from "../../lib/queryOptions";
import { structureKeys } from "../../lib/queryKeys";
import type { JsonSchema } from "../entities/api";
import { getEntitySchema } from "../entities/api";
import { getNode, type NodeDocument } from "./api";
import { NodeEditor } from "./NodeEditor";
import { useI18n } from "../../providers/I18nProvider";

export function NodeEditorLoader(args: {
  moduleName: string;
  nodeId: string;
  onSaved: (node: NodeDocument) => void;
  onUpdated?: (node: NodeDocument) => void;
  schema?: JsonSchema;
  variant?: "full" | "embedded";
}) {
  const { t } = useI18n();
  const nodeQuery = useQuery({
    ...EPHEMERAL_NODE_QUERY_OPTIONS,
    queryKey: ["nodes", "editor", args.moduleName, args.nodeId],
    queryFn: ({ signal }) => getNode(args.moduleName, args.nodeId, signal),
  });
  const entityName = typeof nodeQuery.data?.entity === "string" ? nodeQuery.data.entity : "";
  const schemaQuery = useQuery({
    ...SCHEMA_QUERY_OPTIONS,
    enabled: args.schema === undefined && entityName.length > 0,
    queryKey: structureKeys.schema(args.moduleName, entityName),
    queryFn: ({ signal }) => getEntitySchema(args.moduleName, entityName, signal),
  });

  if (nodeQuery.isError) {
    return <div className="panel panel-centered" role="alert">{localizeUnknownError(nodeQuery.error, t)}</div>;
  }

  if (nodeQuery.isFetching || nodeQuery.data === undefined) {
    return <div className="panel panel-centered"><Spinner /></div>;
  }

  const schema = args.schema ?? schemaQuery.data;
  if (schemaQuery.isError) {
    return <div className="panel panel-centered" role="alert">{localizeUnknownError(schemaQuery.error, t)}</div>;
  }

  if (schema === undefined) {
    return <div className="panel panel-centered"><Spinner /></div>;
  }

  return (
    <NodeEditor
      moduleName={args.moduleName}
      node={nodeQuery.data}
      onUpdated={args.onUpdated}
      onSaved={args.onSaved}
      schema={schema}
      variant={args.variant ?? "embedded"}
    />
  );
}
