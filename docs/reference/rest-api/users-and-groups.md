# Users and groups

Sandala includes the built-in `users` module with the `user` and `group`
entities. They are ordinary nodes: create, read, patch, soft-delete, and ACL
operations use the [Nodes](nodes.md) endpoints with `module` set to `users`.
Their protected schemas and built-in hooks add the rules documented here.

All paths on this page are below `/api/v1/`. Authentication endpoints,
sessions, and personal access tokens are documented in
[Authentication](authentication.md).

## Built-in schemas

Both built-in entities have the common system fields described in
[Entity schemas](entity-schemas.md#system-fields-in-submitted-schemas). Integrators may add fields
to either schema, but cannot remove the fields below or change their
definitions, requiredness, visibility mode, or write mode. Their descriptions
may be changed.

### `users/user`

| Field | Type | Required | Visibility | Write mode | Meaning |
| --- | --- | --- | --- | --- | --- |
| `username` | `String` | Yes | `all` | `all` | Unique local login name. |
| `email` | nullable `String` | No | `admin` | `admin` | Optional, unique email login address. |
| `primary_group` | `Link` to `users/group` | Yes | `admin` | `superuser` | User's primary group. |
| `groups` | `LinkArray` to `users/group` | Yes | `admin` | `superuser` | Groups to which the user belongs; it always includes `primary_group`. |
| `password` | `Password` | No | `all` | `all` | Transient local-password input. It is not stored in the user node. |
| `password_hash` | nullable `String` | No | `none` | `none` | Internal credential value managed by the built-in hook. |
| `role` | `String` enum | Yes | `admin` | `admin` | One of `all`, `admin`, or `superuser`. |
| `active` | `Boolean` | Yes | `admin` | `admin` | Whether the user can authenticate. |

Usernames and non-empty email addresses are normalized to lowercase and are
unique across all users, including soft-deleted users. A deleted identity
therefore cannot be replaced by a different user with the same username or
email address.

The initial schema takes `username` and `password` constraints from the
bootstrap configuration. See [Configuration](../configuration.md) for
`AUTH_USERNAME_*` and `AUTH_PASSWORD_*`.

### `users/group`

| Field | Type | Required | Visibility | Write mode | Meaning |
| --- | --- | --- | --- | --- | --- |
| `groupname` | `String` | Yes | `all` | `admin` | Human-readable group name. It is not unique. |
| `is_default` | `Boolean` | Yes | `admin` | `admin` | Marks the built-in default group. |

The bootstrap process creates one default group. Creating another group always
sets `is_default` to `false`; patching a group ignores an `is_default` value.
The default group cannot be deleted.

## Creating users and groups

Create either entity through `POST /nodes/users/`. The generic create payload
and node-ACL rules are described in [Create a node](nodes.md#create-a-node).

For a user, `username` is required. If `primary_group` is omitted, Sandala
assigns the default group and adds it to `groups`. A supplied primary group is
also added to `groups` when it is absent there. Every selected group must be an
active `users/group` node.

A user may be created without `password`. Such a user cannot use local
password login until a non-empty password is set in a later PATCH. A supplied
password is first processed by the built-in `before_create` hook, which
derives the internal password hash. The resulting node candidate then passes
schema validation, including the `Password` field's constraints. The clear-text
password is removed before storage.

Only a superuser may create a user with the `admin` or `superuser` role, or
choose `primary_group` or `groups` through the ordinary API. Normal node
permission checks still apply to all creates.

### Anonymous registration

An anonymous `POST /nodes/users/` with `entity: "user"` uses the same create
endpoint. It is available only when `ALLOW_ANONYMOUS_USER_REGISTRATION` is
enabled and the users-module root ACL permits the create.

For an accepted registration, Sandala sets the new user as the node owner,
uses the default group as the node group, and creates an `all`-role user. An
anonymous caller cannot select a group or assign a higher role.

## Reading users and groups

Read built-in users and groups with the ordinary GET and query endpoints from
[Nodes](nodes.md#reading-and-querying-nodes). Field visibility applies exactly
as it does to any other node. For example, the bootstrap schema lets an `all`
actor see `username`, but reserves `email`, group membership, `role`, and
`active` for `admin` and `superuser` actors.

When the default projection is used with `GET /nodes/users/{id}/` or
`POST /nodes/users/entity/{entity}/query/`, visible `Link` and `LinkArray` values,
including the user-group fields, resolve one level. The `user` returned by
successful login and `GET /auth/me/` uses this same ordinary node
representation and visibility rules.

## Updating users and groups

Patch a user or group through `PATCH /nodes/users/{id}/`; use
`PATCH /nodes/users/{id}/acl/` for ACL changes. The generic patch contract,
including protected system fields, is documented in [Nodes](nodes.md#patch-a-node).

Changing a user's `primary_group` or `groups` requires a superuser. Sandala
always preserves the invariant that `primary_group` is included in `groups`.
A non-superuser cannot assign an `admin` or `superuser` role.

For a user PATCH, a non-empty `password` replaces the local password. An empty
string means no password change; it does not remove an existing password. The
ordinary API never accepts `password_hash` directly.

## Deleting users and groups

Delete through `DELETE /nodes/users/{id}/` or the ordinary subtree-delete
operation. The operation is a soft delete, subject to the generic node rules
and to the additional protections in the [Errors](#errors) section below.

## Errors

All failures use the [common error contract](errors.md). In addition to the
applicable errors in [Nodes](nodes.md#errors), built-in hooks can return the
following errors for the stated entities.

### Create or patch `users/user`

| Status | Error code | Meaning |
| --- | --- | --- |
| `400` | `validation_error` | A submitted `username` is empty or not a string. The response has a field error at `username` with keyword `username_invalid`. `username` is required when creating a user. |
| `400` | `parameter_invalid` | A hook-validated `password`, `role`, `primary_group`, or `groups` value is malformed. The response identifies the field with `details.field_errors`. An empty `password` in a PATCH is ignored and does not change the password. |
| `400` | `email_invalid` | `email` is not a valid email address. The response has a field error at `email`. |
| `400` | `user_group_not_found` | The selected primary group or one of the selected groups does not exist or is soft-deleted. The response has a field error at `primary_group` or `groups`. |
| `400` | `default_group_not_found` | A new user omitted `primary_group`, but the built-in default group is unavailable. |
| `400` | `default_group_invalid` | A new user omitted `primary_group`, but the stored default group has an invalid ID. |
| `403` | `role_assignment_forbidden` | A non-superuser attempts to assign the `admin` or `superuser` role. The response has a field error at `role`. |
| `403` | `anonymous_registration_disabled` | An anonymous request attempts to create a user while anonymous registration is disabled. |
| `409` | `username_already_exists` | The normalized username is already used by a `users/user` node, including a soft-deleted one. The response has a field error at `username`. |
| `409` | `email_already_exists` | The normalized non-empty email address is already used by a `users/user` node, including a soft-deleted one. The response has a field error at `email`. |

Some malformed values also fail ordinary node document validation, for example
the configured pattern or length constraints for `username` and `password`.
Those responses use `document_validation_failed` as described in
[Nodes](nodes.md#errors).

### Delete `users/user` or `users/group`

| Status | Error code | Meaning |
| --- | --- | --- |
| `403` | `self_deletion_forbidden` | A user attempts to delete their own `users/user` node. |
| `409` | `last_superuser_deletion_forbidden` | The deletion would remove the last active superuser, whether that user is the requested node or an active descendant. |
| `409` | `default_group_deletion_forbidden` | The requested `users/group` node is the built-in default group. |
| `409` | `identity_in_use` | The user or group is still used by an active node, a module root, or a user's group membership. |

`identity_in_use` has these `details` members:

| Member | Type | Meaning |
| --- | --- | --- |
| `identity_type` | `"user"` or `"group"` | Entity of the identity that cannot be deleted. |
| `identity_id` | string | ID of that identity. |
| `reference_type` | string | The blocking reference: `node.owner`, `node.group`, `module.root_owner`, `module.root_group`, `user.primary_group`, or `user.groups`. |
| `module` | string | Module that contains the blocking reference. |
| `node_id` | string, optional | ID of the blocking node. It is absent for a module-root reference. |
