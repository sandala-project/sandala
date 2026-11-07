import { useMutation } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Button } from "../../components/Button";
import { ApiError } from "../../lib/api";
import { localizeApiError } from "../../lib/errors";
import type { TranslationKey } from "../../locales";
import {
  type FileDescriptor,
  type ImageDescriptor,
  type VideoDescriptor,
  uploadFileAsset,
  uploadImageAsset,
  uploadVideoAsset,
} from "./api";
import type { NodeEditorField } from "./editorSchema";
import {
  asFileDescriptor,
  asImageDescriptor,
  asVideoDescriptor,
  extractFileName,
  formatBytes,
  getSemanticTypeFromSchema,
  resolveAssetUrl,
} from "./nodeFieldUtils";

type SharedProps = {
  canWrite: boolean;
  entityName: string;
  error?: string;
  field: NodeEditorField;
  flat?: boolean;
  helperText: string;
  hideLabel?: boolean;
  moduleName: string;
  onBlur?: () => void;
  t: (key: TranslationKey) => string;
  value: unknown;
};

export function AssetArrayItemControl({
  canWrite,
  entityName,
  error,
  field,
  moduleName,
  onBlur,
  onChange,
  t,
  value,
}: {
  canWrite: boolean;
  entityName: string;
  error?: string;
  field: NodeEditorField;
  moduleName: string;
  onBlur: () => void;
  onChange: (value: FileDescriptor | ImageDescriptor | VideoDescriptor | undefined) => void;
  t: (key: TranslationKey) => string;
  value: unknown;
}) {
  const itemSemanticType = field.itemSchema ? getSemanticTypeFromSchema(field.itemSchema) : null;

  if (itemSemanticType === "Image") {
    return (
      <ImageFieldControl
        canWrite={canWrite}
        entityName={entityName}
        error={error}
        field={field}
        helperText=""
        hideLabel
        moduleName={moduleName}
        onBlur={onBlur}
        onChange={onChange}
        value={value}
        t={t}
      />
    );
  }

  if (itemSemanticType === "File") {
    return (
      <FileFieldControl
        canWrite={canWrite}
        entityName={entityName}
        error={error}
        field={field}
        helperText=""
        hideLabel
        moduleName={moduleName}
        onBlur={onBlur}
        onChange={onChange}
        value={value}
        t={t}
      />
    );
  }

  if (itemSemanticType === "Video") {
    return (
      <VideoFieldControl
        canWrite={canWrite}
        entityName={entityName}
        error={error}
        field={field}
        helperText=""
        hideLabel
        moduleName={moduleName}
        onBlur={onBlur}
        onChange={onChange}
        value={value}
        t={t}
      />
    );
  }

  return null;
}

export function ImageFieldControl({
  canWrite,
  entityName,
  error,
  field,
  flat = false,
  helperText,
  hideLabel = false,
  moduleName,
  onBlur,
  onChange,
  t,
  value,
}: SharedProps & {
  onChange: (value: ImageDescriptor | undefined) => void;
}) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const image = asImageDescriptor(value);
  const previewUrl = image ? resolveAssetUrl(image.url) : null;

  const uploadMutation = useMutation({
    mutationFn: async (file: File) =>
      uploadImageAsset({
        entityName,
        fieldPath: field.path.join("."),
        file,
        moduleName,
      }),
    onSuccess: (descriptor) => {
      setUploadError(null);
      onChange(descriptor);
    },
    onError: (nextError) => {
      if (nextError instanceof ApiError) {
        setUploadError(localizeApiError(nextError, t));
        return;
      }

      setUploadError(t("pages.nodes.editor.image.uploadFailed"));
    },
  });

  const clearValue = () => {
    setUploadError(null);
    onChange(undefined);
  };

  return (
    <div className={`node-field-block ${flat ? "node-field-block-flat" : ""}`.trim()}>
      {!hideLabel ? <div className="field-label">{field.label}</div> : null}
      <div className="node-structured-control">
        {helperText ? <div className="node-structured-helper">{helperText}</div> : null}
        <div className="node-image-field">
          {previewUrl ? (
            <a className="node-image-preview-link" href={previewUrl} rel="noreferrer" target="_blank">
              <img alt={field.label} className="node-image-preview" src={previewUrl} />
            </a>
          ) : (
            <div className="node-image-empty">{t("pages.nodes.editor.image.empty")}</div>
          )}
          <div className="node-media-side">
            <div className="node-image-meta">
              {image ? (
                <>
                  {image["mime-type"] ? <div className="node-image-meta-row">{image["mime-type"]}</div> : null}
                  {typeof image.width === "number" && typeof image.height === "number"
                    ? <div className="node-image-meta-row">{`${image.width} × ${image.height}`}</div>
                    : null}
                  {typeof image.size === "number" ? <div className="node-image-meta-row">{formatBytes(image.size)}</div> : null}
                </>
              ) : (
                <div className="node-image-meta-row">{t("pages.nodes.editor.image.noImage")}</div>
              )}
            </div>
            <div className="node-media-actions">
              <input
                accept="image/jpeg,image/png,image/gif,image/webp"
                className="visually-hidden"
                onBlur={onBlur}
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  event.target.value = "";
                  if (file === undefined) {
                    return;
                  }
                  void uploadMutation.mutateAsync(file);
                }}
                ref={inputRef}
                type="file"
              />
              {canWrite ? (
                <div className="node-media-button-row">
                  <Button
                    disabled={uploadMutation.isPending}
                    kind="ghost"
                    onClick={() => inputRef.current?.click()}
                    type="button"
                  >
                    {uploadMutation.isPending
                      ? t("pages.nodes.editor.image.uploading")
                      : image
                        ? t("pages.nodes.editor.image.replace")
                        : t("pages.nodes.editor.image.upload")}
                  </Button>
                  {image ? (
                    <Button kind="ghost" onClick={clearValue} type="button">
                      {t("pages.nodes.editor.asset.clear")}
                    </Button>
                  ) : null}
                </div>
              ) : null}
            </div>
          </div>
        </div>
        {uploadError ? <div className="field-error">{uploadError}</div> : null}
        {error ? <div className="field-error">{error}</div> : null}
      </div>
    </div>
  );
}

export function FileFieldControl({
  canWrite,
  entityName,
  error,
  field,
  flat = false,
  helperText,
  hideLabel = false,
  moduleName,
  onBlur,
  onChange,
  t,
  value,
}: SharedProps & {
  onChange: (value: FileDescriptor | undefined) => void;
}) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const file = asFileDescriptor(value);
  const fileUrl = file ? resolveAssetUrl(file.url) : null;

  const uploadMutation = useMutation({
    mutationFn: async (nextFile: File) =>
      uploadFileAsset({
        entityName,
        fieldPath: field.path.join("."),
        file: nextFile,
        moduleName,
      }),
    onSuccess: (descriptor) => {
      setUploadError(null);
      onChange(descriptor);
    },
    onError: (nextError) => {
      if (nextError instanceof ApiError) {
        setUploadError(localizeApiError(nextError, t));
        return;
      }

      setUploadError(t("pages.nodes.editor.file.uploadFailed"));
    },
  });

  const clearValue = () => {
    setUploadError(null);
    onChange(undefined);
  };

  return (
    <div className={`node-field-block ${flat ? "node-field-block-flat" : ""}`.trim()}>
      {!hideLabel ? <div className="field-label">{field.label}</div> : null}
      <div className="node-structured-control">
        {helperText ? <div className="node-structured-helper">{helperText}</div> : null}
        <div className="node-file-field">
          {fileUrl && file ? (
            <a className="node-file-card" href={fileUrl} rel="noreferrer" target="_blank">
              <div className="node-file-title">{extractFileName(file.url)}</div>
              {file["mime-type"] || typeof file.size === "number" ? (
                <div className="node-file-meta">
                  {file["mime-type"] ? <div className="node-file-meta-row">{file["mime-type"]}</div> : null}
                  {typeof file.size === "number" ? <div className="node-file-meta-row">{formatBytes(file.size)}</div> : null}
                </div>
              ) : null}
            </a>
          ) : (
            <div className="node-file-empty">
              <div className="node-file-title">{t("pages.nodes.editor.file.noFile")}</div>
            </div>
          )}
        </div>
        <div className="node-structured-actions">
          <input
            className="visually-hidden"
            onBlur={onBlur}
            onChange={(event) => {
              const nextFile = event.target.files?.[0];
              event.target.value = "";
              if (nextFile === undefined) {
                return;
              }
              void uploadMutation.mutateAsync(nextFile);
            }}
            ref={inputRef}
            type="file"
          />
          {canWrite ? (
            <Button
              disabled={uploadMutation.isPending}
              kind="ghost"
              onClick={() => inputRef.current?.click()}
              type="button"
            >
              {uploadMutation.isPending
                ? t("pages.nodes.editor.file.uploading")
                : file
                  ? t("pages.nodes.editor.file.replace")
                  : t("pages.nodes.editor.file.upload")}
            </Button>
          ) : null}
          {canWrite && file ? (
            <Button kind="ghost" onClick={clearValue} type="button">
              {t("pages.nodes.editor.asset.clear")}
            </Button>
          ) : null}
        </div>
        {uploadError ? <div className="field-error">{uploadError}</div> : null}
        {error ? <div className="field-error">{error}</div> : null}
      </div>
    </div>
  );
}

export function VideoFieldControl({
  canWrite,
  entityName,
  error,
  field,
  flat = false,
  helperText,
  hideLabel = false,
  moduleName,
  onBlur,
  onChange,
  t,
  value,
}: SharedProps & {
  onChange: (value: VideoDescriptor | undefined) => void;
}) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const video = asVideoDescriptor(value);
  const videoUrl = video ? resolveAssetUrl(video.url) : null;

  const uploadMutation = useMutation({
    mutationFn: async (nextFile: File) =>
      uploadVideoAsset({
        entityName,
        fieldPath: field.path.join("."),
        file: nextFile,
        moduleName,
      }),
    onSuccess: (descriptor) => {
      setUploadError(null);
      onChange(descriptor);
    },
    onError: (nextError) => {
      if (nextError instanceof ApiError) {
        setUploadError(localizeApiError(nextError, t));
        return;
      }

      setUploadError(t("pages.nodes.editor.video.uploadFailed"));
    },
  });

  const clearValue = () => {
    setUploadError(null);
    onChange(undefined);
  };

  return (
    <div className={`node-field-block ${flat ? "node-field-block-flat" : ""}`.trim()}>
      {!hideLabel ? <div className="field-label">{field.label}</div> : null}
      <div className="node-structured-control">
        {helperText ? <div className="node-structured-helper">{helperText}</div> : null}
        <div className="node-video-field">
          {videoUrl && video ? (
            <div className="node-video-frame">
              <video className="node-video-preview" controls preload="metadata" src={videoUrl} />
            </div>
          ) : (
            <div className="node-image-empty">{t("pages.nodes.editor.video.noVideo")}</div>
          )}
          <div className="node-media-side">
            <div className="node-image-meta">
              {video ? (
                <>
                  <div className="node-image-meta-row">{extractFileName(video.url)}</div>
                  {video["mime-type"] ? <div className="node-image-meta-row">{video["mime-type"]}</div> : null}
                  {typeof video.size === "number" ? <div className="node-image-meta-row">{formatBytes(video.size)}</div> : null}
                </>
              ) : (
                <div className="node-image-meta-row">{t("pages.nodes.editor.video.noVideo")}</div>
              )}
            </div>
            <div className="node-media-actions">
              <input
                className="visually-hidden"
                onBlur={onBlur}
                onChange={(event) => {
                  const nextFile = event.target.files?.[0];
                  event.target.value = "";
                  if (nextFile === undefined) {
                    return;
                  }
                  void uploadMutation.mutateAsync(nextFile);
                }}
                ref={inputRef}
                type="file"
              />
              {videoUrl ? (
                <a className="node-video-link" href={videoUrl} rel="noreferrer" target="_blank">
                  {t("pages.nodes.editor.asset.open")}
                </a>
              ) : null}
              {canWrite ? (
                <div className="node-media-button-row">
                  <Button
                    disabled={uploadMutation.isPending}
                    kind="ghost"
                    onClick={() => inputRef.current?.click()}
                    type="button"
                  >
                    {uploadMutation.isPending
                      ? t("pages.nodes.editor.video.uploading")
                      : video
                        ? t("pages.nodes.editor.video.replace")
                        : t("pages.nodes.editor.video.upload")}
                  </Button>
                  {video ? (
                    <Button kind="ghost" onClick={clearValue} type="button">
                      {t("pages.nodes.editor.asset.clear")}
                    </Button>
                  ) : null}
                </div>
              ) : null}
            </div>
          </div>
        </div>
        {uploadError ? <div className="field-error">{uploadError}</div> : null}
        {error ? <div className="field-error">{error}</div> : null}
      </div>
    </div>
  );
}
