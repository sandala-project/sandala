import type { TranslationKey } from "../locales";

export type FieldError = {
  keyword: string;
  location: Array<string | number>;
  message: string;
};

export class ApiError extends Error {
  code: string;
  status: number;
  fieldErrors: FieldError[];
  details: Record<string, unknown> | null;
  description: string;
  payload: unknown;

  constructor(args: {
    code: string;
    details: Record<string, unknown> | null;
    fieldErrors: FieldError[];
    message: string;
    payload: unknown;
    status: number;
  }) {
    super(args.message);
    this.code = args.code;
    this.status = args.status;
    this.fieldErrors = args.fieldErrors;
    this.details = args.details;
    this.description = args.message;
    this.payload = args.payload;
  }
}

type ErrorTranslator = (key: TranslationKey) => string;

const fieldErrorTranslations: Partial<Record<string, TranslationKey>> = {
  additionalProperties: "errors.validation.invalid",
  acl_hidden_references: "errors.validation.aclHiddenReferences",
  format: "errors.validation.format",
  maximum: "errors.validation.maximum",
  maxItems: "errors.validation.maxItems",
  maxLength: "errors.validation.maxLength",
  minimum: "errors.validation.minimum",
  minItems: "errors.validation.minItems",
  minLength: "errors.validation.minLength",
  multipleOf: "errors.validation.multipleOf",
  pattern: "errors.validation.pattern",
  required: "errors.validation.required",
  email_already_exists: "errors.validation.emailAlreadyExists",
  email_invalid: "errors.validation.emailInvalid",
  groups_invalid: "errors.validation.groupsInvalid",
  password_invalid: "errors.validation.passwordInvalid",
  primary_group_invalid: "errors.validation.primaryGroupInvalid",
  role_assignment_forbidden: "errors.validation.roleAssignmentForbidden",
  role_invalid: "errors.validation.roleInvalid",
  type: "errors.validation.invalid",
  user_group_not_found: "errors.validation.userGroupNotFound",
  username_already_exists: "errors.validation.usernameAlreadyExists",
  username_invalid: "errors.validation.usernameInvalid",
  uniqueItems: "errors.validation.invalid",
};

const errorCodeTranslations: Partial<Record<string, TranslationKey>> = {
  access_denied: "errors.api.forbidden",
  acl_fields_not_allowed_in_node_patch: "errors.api.validation",
  acl_patch_payload_invalid: "errors.api.validation",
  authentication_error: "errors.api.authentication",
  anonymous_registration_disabled: "errors.api.forbidden",
  conflict: "errors.api.conflict",
  default_group_invalid: "errors.api.validation",
  default_group_not_found: "errors.api.notFound",
  document_validation_failed: "errors.api.validation",
  email_invalid: "errors.api.validation",
  internal_error: "errors.api.unexpected",
  last_superuser_deletion_forbidden: "errors.api.lastSuperuserDeletionForbidden",
  not_found: "errors.api.notFound",
  parameter_invalid: "errors.api.validation",
  password_hash_direct_write_forbidden: "errors.api.validation",
  query_validation_failed: "errors.api.validation",
  request_body_invalid: "errors.api.request",
  role_assignment_forbidden: "errors.api.forbidden",
  sandala_error: "errors.api.unknown",
  schema_validation_failed: "errors.api.validation",
  self_deletion_forbidden: "errors.api.forbidden",
  user_group_not_found: "errors.api.notFound",
  validation_error: "errors.api.validation",
};

const assetErrorCodes = new Set([
  "asset_file_missing",
  "asset_invalid_image_file",
  "asset_storage_key_invalid",
  "asset_target_field_not_found",
  "asset_target_invalid",
  "asset_target_semantic_type_mismatch",
  "asset_transform_format_unsupported",
  "asset_transform_invalid",
  "asset_unsupported_image_format",
]);

export function localizeApiFieldError(fieldError: FieldError, t: ErrorTranslator) {
  const translationKey = fieldErrorTranslations[fieldError.keyword];
  return translationKey === undefined && fieldError.message.trim().length > 0
    ? fieldError.message
    : translationKey === undefined
      ? t("errors.validation.invalid")
      : t(translationKey);
}

export function localizeApiError(error: ApiError, t: ErrorTranslator) {
  const translationKey = errorCodeTranslations[error.code];
  if (translationKey !== undefined) {
    return t(translationKey);
  }

  if (assetErrorCodes.has(error.code)) {
    return t("errors.api.asset");
  }

  if (/(forbidden|denied)/.test(error.code)) {
    return t("errors.api.forbidden");
  }
  if (error.code.includes("not_found")) {
    return t("errors.api.notFound");
  }
  if (/(already_exists|conflict|in_use)/.test(error.code)) {
    return t("errors.api.conflict");
  }
  if (/(invalid|required|validation|missing|not_allowed|cycle|same_as|hidden_references)/.test(error.code)) {
    return t("errors.api.validation");
  }

  return error.description || t("errors.api.unknown");
}

export function localizeUnknownError(error: unknown, t: ErrorTranslator) {
  if (error instanceof ApiError) {
    return localizeApiError(error, t);
  }

  return t("errors.api.unknown");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function normalizeApiError(payload: unknown, status: number) {
  if (!isRecord(payload)) {
    return new ApiError({
      code: "unknown_error",
      details: null,
      fieldErrors: [],
      message: "",
      payload,
      status,
    });
  }

  const details = isRecord(payload.details) ? payload.details : null;
  const rawFieldErrors = Array.isArray(details?.field_errors) ? details.field_errors : [];
  const fieldErrors: FieldError[] = rawFieldErrors.flatMap((item) => {
    if (!isRecord(item)) {
      return [];
    }

    return [
      {
        keyword: typeof item.keyword === "string" ? item.keyword : "unknown",
        location: Array.isArray(item.location)
          ? item.location.filter((segment): segment is string | number => typeof segment === "string" || typeof segment === "number")
          : [],
        message: typeof item.message === "string" ? item.message : "",
      },
    ];
  });

  return new ApiError({
    code: typeof payload.error === "string" ? payload.error : "unknown_error",
    details,
    fieldErrors,
    message: typeof payload.error_description === "string" ? payload.error_description : "",
    payload,
    status,
  });
}
