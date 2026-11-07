import type { JsonSchema } from "../entities/api";
import { NodesTableView } from "./NodesTableView";
import type { NodesTableState } from "./useNodeTableState";

export function NodesTableScene(args: {
  moduleName: string;
  state: NodesTableState;
  tableSchema: JsonSchema | null;
}) {
  return <NodesTableView moduleName={args.moduleName} state={args.state} tableSchema={args.tableSchema} />;
}
