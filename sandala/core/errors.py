from __future__ import annotations

from typing import Any


class SandalaError(Exception):
    """Base domain error."""

    default_code = "sandala_error"
    default_message = "Sandala error"

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = self.default_code
        self.message = message if message is not None else self.default_message
        self.details = details
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message


class ValidationError(SandalaError):
    default_code = "validation_error"
    default_message = "Validation failed"


class RequestBodyInvalidError(ValidationError):
    default_code = "request_body_invalid"
    default_message = "Request body is invalid"


class ParameterInvalidError(ValidationError):
    default_code = "parameter_invalid"
    default_message = "Parameter is invalid"


class EmailInvalidError(ParameterInvalidError):
    default_code = "email_invalid"
    default_message = "Email is invalid"


class PasswordHashDirectWriteForbiddenError(ParameterInvalidError):
    default_code = "password_hash_direct_write_forbidden"
    default_message = "Password hash cannot be provided directly"


class UserGroupNotFoundError(ParameterInvalidError):
    default_code = "user_group_not_found"
    default_message = "User group not found"


class DefaultGroupNotFoundError(ParameterInvalidError):
    default_code = "default_group_not_found"
    default_message = "Default group not found"


class DefaultGroupInvalidError(ParameterInvalidError):
    default_code = "default_group_invalid"
    default_message = "Default group is invalid"


class DocumentValidationError(ValidationError):
    default_code = "document_validation_failed"
    default_message = "Document validation failed"


class SchemaValidationError(ValidationError):
    default_code = "schema_validation_failed"
    default_message = "Schema validation failed"


class QueryValidationError(ValidationError):
    default_code = "query_validation_failed"
    default_message = "Query validation failed"


class AclFieldsNotAllowedInNodePatchError(ParameterInvalidError):
    default_code = "acl_fields_not_allowed_in_node_patch"
    default_message = "ACL fields must be changed through the ACL endpoint"


class AclPatchPayloadInvalidError(ParameterInvalidError):
    default_code = "acl_patch_payload_invalid"
    default_message = "ACL patch payload is invalid"


class AssetFileMissingError(ParameterInvalidError):
    default_code = "asset_file_missing"
    default_message = "Uploaded asset file is missing"


class AssetTargetInvalidError(ParameterInvalidError):
    default_code = "asset_target_invalid"
    default_message = "Asset target is invalid"


class AssetTargetFieldNotFoundError(ValidationError):
    default_code = "asset_target_field_not_found"
    default_message = "Asset target field not found"


class AssetTargetSemanticTypeMismatchError(ValidationError):
    default_code = "asset_target_semantic_type_mismatch"
    default_message = "Asset target field has incompatible semantic type"


class AssetUnsupportedImageFormatError(ValidationError):
    default_code = "asset_unsupported_image_format"
    default_message = "Image format is not supported"


class AssetInvalidImageFileError(ValidationError):
    default_code = "asset_invalid_image_file"
    default_message = "Image file is invalid or corrupted"


class AssetTransformInvalidError(ParameterInvalidError):
    default_code = "asset_transform_invalid"
    default_message = "Asset transform is invalid"


class AssetTransformFormatUnsupportedError(ValidationError):
    default_code = "asset_transform_format_unsupported"
    default_message = "Requested transform output format is not supported"


class AssetStorageKeyInvalidError(ParameterInvalidError):
    default_code = "asset_storage_key_invalid"
    default_message = "Asset storage key is invalid"


class AuthenticationError(SandalaError):
    default_code = "authentication_error"
    default_message = "Authentication failed"


class AuthorizationError(SandalaError):
    default_code = "access_denied"
    default_message = "Access denied"


class AnonymousRegistrationDisabledError(AuthorizationError):
    default_code = "anonymous_registration_disabled"
    default_message = "Anonymous registration is disabled"


class RoleAssignmentForbiddenError(AuthorizationError):
    default_code = "role_assignment_forbidden"
    default_message = "Role assignment is forbidden"


class NotFoundError(SandalaError):
    default_code = "not_found"
    default_message = "Resource not found"


class ConflictError(SandalaError):
    default_code = "conflict"
    default_message = "Resource conflict"


class NodeIdAlreadyExistsError(ConflictError):
    default_code = "node_id_already_exists"
    default_message = "Node id already exists"


class UsernameAlreadyExistsError(ConflictError):
    default_code = "username_already_exists"
    default_message = "Username already exists"


class EmailAlreadyExistsError(ConflictError):
    default_code = "email_already_exists"
    default_message = "Email already exists"


class IdentityInUseError(ConflictError):
    default_code = "identity_in_use"
    default_message = "User or group is still referenced"


class LastSuperuserDeletionForbiddenError(ConflictError):
    default_code = "last_superuser_deletion_forbidden"
    default_message = "The last superuser cannot be deleted"


class DefaultGroupDeletionForbiddenError(ConflictError):
    default_code = "default_group_deletion_forbidden"
    default_message = "The default group cannot be deleted"


class SelfDeletionForbiddenError(AuthorizationError):
    default_code = "self_deletion_forbidden"
    default_message = "User cannot delete themselves"


class ParentNodeNotFoundError(ValidationError):
    default_code = "parent_node_not_found"
    default_message = "Parent node not found"


class ParentWriteForbiddenError(ValidationError):
    default_code = "parent_write_forbidden"
    default_message = "Write to parent node is not allowed"


class DescendantWriteForbiddenError(ValidationError):
    default_code = "descendant_write_forbidden"
    default_message = "Write to one or more descendants is not allowed"


class ParentSameAsCurrentError(ValidationError):
    default_code = "parent_same_as_current"
    default_message = "Parent node cannot be the same as current node"


class ParentCycleDetectedError(ValidationError):
    default_code = "parent_cycle_detected"
    default_message = "Parent node cannot be a descendant of current node"


class EntityNotAllowedInRootError(ValidationError):
    default_code = "entity_not_allowed_in_root"
    default_message = "Entity cannot be added to module root"


class EntityNotAllowedUnderParentError(ValidationError):
    default_code = "entity_not_allowed_under_parent"
    default_message = "Entity cannot be added under parent entity"


class RootCreateForbiddenError(ValidationError):
    default_code = "root_create_forbidden"
    default_message = "Root create is not allowed"


class FieldWriteForbiddenError(ValidationError):
    default_code = "field_write_forbidden"
    default_message = "Field is not writable for current actor"


class LinkPatchAclHiddenReferencesMissingError(ValidationError):
    default_code = "link_patch_acl_hidden_references_missing"
    default_message = "Patch must retain ACL-hidden references"


class OwnerRequiredError(ValidationError):
    default_code = "owner_required"
    default_message = "Owner must be provided"


class OwnerMustMatchActorError(ValidationError):
    default_code = "owner_must_match_actor"
    default_message = "Owner must match actor user id"


class GroupRequiredError(ValidationError):
    default_code = "group_required"
    default_message = "Group must be provided"


class GroupNotInActorGroupsError(ValidationError):
    default_code = "group_not_in_actor_groups"
    default_message = "Group must be one of actor groups"


class OwnerNotFoundError(ValidationError):
    default_code = "owner_not_found"
    default_message = "Owner not found"


class GroupNotFoundError(ValidationError):
    default_code = "group_not_found"
    default_message = "Group not found"


class OwnerChangeForbiddenError(ValidationError):
    default_code = "owner_change_forbidden"
    default_message = "Owner can only be changed by superuser"


class PermChangeForbiddenError(ValidationError):
    default_code = "perm_change_forbidden"
    default_message = "Permissions can only be changed by superuser or node owner"


class GroupChangeForbiddenError(ValidationError):
    default_code = "group_change_forbidden"
    default_message = "Group can only be changed by superuser or node owner"
