export type ReferenceValue = string | Record<string, unknown>;

export function getReferenceId(value: unknown) {
  if (typeof value === "string") {
    return value.trim();
  }
  if (isRecord(value) && typeof value.id === "string") {
    return value.id.trim();
  }
  return "";
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
