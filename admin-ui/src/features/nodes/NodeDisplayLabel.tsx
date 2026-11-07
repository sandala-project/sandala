import { useQuery } from "@tanstack/react-query";
import { SCHEMA_QUERY_OPTIONS } from "../../lib/queryOptions";
import { structureKeys } from "../../lib/queryKeys";
import { getEntitySchema } from "../entities/api";
import type { NodeDocument } from "./api";
import { buildNodeEntityPresentation, resolveNodeDisplayLabel } from "./presentation";

export function NodeDisplayLabel(args: {
  moduleName: string | null;
  node: NodeDocument;
  purpose: "reference" | "tree";
}) {
  const entityName = typeof args.node.entity === "string" ? args.node.entity : "";
  const schemaQuery = useQuery({
    ...SCHEMA_QUERY_OPTIONS,
    enabled: args.moduleName !== null && args.moduleName.length > 0 && entityName.length > 0,
    queryKey: structureKeys.schema(args.moduleName ?? "", entityName),
    queryFn: ({ signal }) => getEntitySchema(args.moduleName!, entityName, signal),
  });
  const presentation = schemaQuery.data === undefined
    ? null
    : buildNodeEntityPresentation(schemaQuery.data);

  return <>{resolveNodeDisplayLabel(args.node, presentation, args.purpose)}</>;
}
