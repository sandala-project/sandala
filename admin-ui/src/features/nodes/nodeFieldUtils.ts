import type { JsonSchema } from "../entities/api";
import { getReferenceId } from "../../lib/references";
import type { FileDescriptor, ImageDescriptor, VideoDescriptor } from "./api";

export function asImageDescriptor(value: unknown): ImageDescriptor | null {
  if (!isRecord(value)) {
    return null;
  }

  if (typeof value.url !== "string") {
    return null;
  }
  if (
    (value["mime-type"] !== undefined && typeof value["mime-type"] !== "string")
    || (value.width !== undefined && typeof value.width !== "number")
    || (value.height !== undefined && typeof value.height !== "number")
    || (value.size !== undefined && typeof value.size !== "number")
  ) {
    return null;
  }

  const descriptor: ImageDescriptor = { url: value.url };
  if (typeof value["mime-type"] === "string") descriptor["mime-type"] = value["mime-type"];
  if (typeof value.width === "number") descriptor.width = value.width;
  if (typeof value.height === "number") descriptor.height = value.height;
  if (typeof value.size === "number") descriptor.size = value.size;
  return descriptor;
}

export function asFileDescriptor(value: unknown): FileDescriptor | null {
  if (!isRecord(value)) {
    return null;
  }

  if (typeof value.url !== "string") {
    return null;
  }
  if (
    (value["mime-type"] !== undefined && typeof value["mime-type"] !== "string")
    || (value.size !== undefined && typeof value.size !== "number")
  ) {
    return null;
  }

  const descriptor: FileDescriptor = { url: value.url };
  if (typeof value["mime-type"] === "string") descriptor["mime-type"] = value["mime-type"];
  if (typeof value.size === "number") descriptor.size = value.size;
  return descriptor;
}

export function asVideoDescriptor(value: unknown): VideoDescriptor | null {
  if (!isRecord(value)) {
    return null;
  }

  if (typeof value.url !== "string") {
    return null;
  }
  if (
    (value["mime-type"] !== undefined && typeof value["mime-type"] !== "string")
    || (value.size !== undefined && typeof value.size !== "number")
  ) {
    return null;
  }

  const descriptor: VideoDescriptor = { url: value.url };
  if (typeof value["mime-type"] === "string") descriptor["mime-type"] = value["mime-type"];
  if (typeof value.size === "number") descriptor.size = value.size;
  return descriptor;
}

export function resolveAssetUrl(url: string) {
  return url;
}

export function formatBytes(size: number) {
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function extractFileName(url: string) {
  const trimmed = url.split("?")[0] ?? url;
  const segments = trimmed.split("/");
  return segments[segments.length - 1] || url;
}

export function isAtomicAssetSemanticType(semanticType: string) {
  return semanticType === "File" || semanticType === "Image" || semanticType === "Video";
}

export function getNodeReferenceId(value: unknown) {
  return getReferenceId(value);
}

export function getSemanticTypeFromSchema(schema: JsonSchema | null) {
  if (schema === null) {
    return null;
  }

  const meta = isRecord(schema["x-meta"]) ? schema["x-meta"] : null;
  return typeof meta?.["semantic-type"] === "string" ? meta["semantic-type"] : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
