# Storage

Sandala's storage layer contains MongoDB repositories and binary blob backends.
It executes persistence operations; services and query planning decide which
operations are allowed and which documents belong in a result. The layer
boundary is described in [Architecture](architecture.md#package-responsibilities).
Configuration values belong in [Configuration](../reference/configuration.md),
not in repository implementations.

## Construction and lifetime

`bootstrap.build_container()` resolves configuration, obtains a database from
`create_mongo_database()`, constructs repositories, and injects them into core
services. The database factory creates a PyMongo `MongoClient` from `MONGO_URI`
and selects `MONGO_DB`. It does not create a process-global client at import
time or a new client for each service call.

The container also constructs one configured blob backend. Reuse these
dependencies with their services rather than opening database connections or
constructing storage backends inside routes and hooks. The repositories have
no schema or node-result cache; the query builder's separate schema cache is
limited to one build, as described in [Query builder](query-builder.md#schema-reads-within-one-build).

## MongoDB collections and representations

All entity types in a module share its node collection. The stored `entity`
field distinguishes them; links use the target module's collection and match
the public `id`, not MongoDB's internal `_id`.

| Collection | Stored data |
| --- | --- |
| `{module}` | Complete node documents for that module, including ACL, hierarchy, and lifecycle fields. The built-in `users` module uses this same arrangement. |
| `_modules` | Module metadata, keyed by technical `name`. |
| `_entities` | Entity metadata as `{module, entity, schema}` records. `schema` contains the stored user portion without common node system fields. |
| `_auth_sessions` | Session hashes, user IDs, expiry bounds, revocation, and timestamps. |
| `_pat_tokens` | PAT IDs, token hashes, subjects, names, expiry, revocation, creator IDs, and timestamps. |
| `_assets` | Metadata for uploaded binaries, independent of node documents. |

`IdentityRepository` reads user identities from `users`; it does not maintain
a separate user table. Node UUIDs and date/date-time values are stored as
strings rather than being converted to BSON UUID or date types by a repository.
Authentication timestamps likewise use ISO date-time strings. Preserve this
representation when changing persistence code rather than introducing
transport-dependent conversions.

Repositories suppress `_id` in ordinary returned node documents, while schema
metadata maintenance can still use it internally. Query output projection is
owned by the builder; `NodeRepository.aggregate()` does not add a second
projection or authorization pass.

Deleting module metadata does not drop its node collection. Similarly,
soft-deleting a node sets lifecycle fields rather than physically removing the
document. Schema replacement must therefore still inspect soft-deleted nodes;
`iter_by_entity()` intentionally has no active-node filter. See
[Validation and schema evolution](validation-and-schema-evolution.md#replacing-an-entity-schema).

### Authentication records

`_auth_sessions` stores these application fields:

| Field | Stored type | Meaning |
| --- | --- | --- |
| `session_hash` | string | Hash of the opaque session ID, used for lookup and revocation. The raw ID is not stored. |
| `user_id` | UUID string | User authenticated by this session. |
| `expires_at` | UTC date-time string | Current idle expiry, capped by the absolute limit. |
| `max_expires_at` | UTC date-time string | Absolute expiry fixed at login; renewal does not move it. |
| `revoked_at` | UTC date-time string or `null` | Revocation time; `null` means not revoked, not necessarily unexpired. |
| `cdate` | UTC date-time string | Session creation time. |
| `mdate` | UTC date-time string | Most recent record change, including renewal or revocation. |

`_pat_tokens` stores the persistent fields in the
[PAT representation](../reference/rest-api/authentication.md#pat-representation):
`id`, `subject_id`, `name`, `expires_at`, `revoked_at`, `created_by`, `cdate`,
and `mdate`, with the documented types and meanings. It additionally stores
`token_hash`, a string containing the hash of the secret part of the PAT.
The full `<id>.<secret>` credential and response-only `token` are not stored.
Rotation replaces `token_hash` and updates `mdate`; revocation sets
`revoked_at` and updates `mdate`. Neither operation changes `cdate`.

These are authentication-subsystem records, not entity schemas or nodes. They
are not available through ordinary node CRUD. Services authenticate against
the records and the current user identity; public PAT responses remove
`token_hash`, while session hashes never appear in login responses.

## Index ownership

Indexes are created at explicit initialization points. `ModuleRepository`
creates its module-name index when constructed. The container calls the
identity, session, PAT, and asset repositories' `ensure_indexes()` methods.
`NodeRepository` construction alone does not create indexes for every module.

For an ordinary module, `ModuleService.create_module()` calls
`ensure_module_indexes()` before inserting the module metadata. The users
bootstrap calls the same helper when initializing that module. Node reads and
queries do not create indexes as a side effect.

### Module node indexes

In addition to MongoDB's own `_id` index, Sandala creates these indexes for a
module's node collection:

| Name | Keys in order | Purpose |
| --- | --- | --- |
| `sandala_id_unique` | `id` ascending, unique | Enforce public ID uniqueness across every entity in the module, including soft-deleted nodes. |
| `sandala_entity_deleted_id` | `entity`, `deleted`, `_id` ascending | Support entity-scoped active-node selections and their default ordering. |
| `sandala_parent_deleted_id` | `parent`, `deleted`, `_id` ascending | Support direct-child selections, including lazy tree loading, and their default ordering. |

The compound indexes can narrow a selection even when a different requested
sort requires separate sorting. They do not provide every possible sort
order. There is no built-in `ancestors` index.

The `sandala_` prefix identifies the built-in module and identity indexes.
Integrators can add workload-specific MongoDB indexes directly; keep those
names separate. An extra unique index also introduces a new write constraint,
not merely a performance choice. Do not treat the three module indexes as a
reason to drop other indexes or rebuild a collection during a read.

### User identity indexes

Because `users/user` and `users/group` share a collection, identity uniqueness
uses partial indexes:

| Name | Unique key | Partial filter |
| --- | --- | --- |
| `sandala_user_username_unique` | `username` | `entity` equals `user`. |
| `sandala_user_email_unique` | `email` | `entity` equals `user` and `email` has BSON type `string`. |

The email index excludes absent and null email values. Neither index excludes
soft-deleted users: deletion does not free their username or email for reuse.
The built-in user hooks normalize values and diagnose conflicts, while the
indexes enforce uniqueness when writes race. Group names have no built-in
unique index. Public identity rules are in [Users and groups](../reference/rest-api/users-and-groups.md).

### Other system indexes

The remaining built-in secondary indexes are:

| Collection | Unique indexes | Other indexes |
| --- | --- | --- |
| `_modules` | `name` | None. |
| `_entities` | None. | None created by `EntityRepository`. |
| `_auth_sessions` | `session_hash` | Separate indexes on `user_id`, `expires_at`, `max_expires_at`, and `revoked_at`. |
| `_pat_tokens` | `id` | Separate indexes on `subject_id`, `created_by`, `expires_at`, and `revoked_at`. |
| `_assets` | `id`; `storage_key` | One compound index on `module`, `entity`, and `field`. |

These expiry indexes are ordinary indexes, not TTL indexes. Expiration and
revocation are checked by `AuthService`; expired records are not automatically
removed by this setup. In particular, the session repository's
`find_active_by_hash()` checks revocation, while the service checks expiry,
the absolute session limit, and the current user's eligibility. A repository
lookup is not sufficient to establish an authenticated actor.

## Repository operations and error boundaries

Repositories can use MongoDB operators, update pipelines, and bulk writes.
What remains outside storage is the decision about authorization, schema
compatibility, hooks, or query-language meaning. For example,
`update_descendants_hierarchy()` implements prefix replacement and depth
arithmetic using values already calculated by `NodeService`; it does not
decide whether a move is permitted.

Active-only methods put `deleted: false` in their explicit storage query.
General methods such as `find_one()` and `aggregate()` do not silently add
that restriction or ACL. A caller constructing an internal read must choose
the appropriate scope; the public node read path obtains its policy-complete
pipeline from `QueryBuilder`.

### Node uniqueness conflicts

`NodeRepository.insert_node()` and `replace_node()` catch PyMongo's
`DuplicateKeyError` and return `None`. `NodeService` maps that outcome to a
domain conflict. On create it checks whether the requested public ID exists
to distinguish `NodeIdAlreadyExistsError` from a generic unique-index
conflict. Ordinary replacement reports a generic conflict.

The unique index, not a prior existence check, is the atomic guarantee against
duplicate node IDs. This handling also covers additional unique indexes an
integrator places on a module collection, without parsing driver message
text. It is specific to these node write methods; do not assume every
repository exception is automatically converted into a domain conflict.

### Rejected aggregation queries

`NodeRepository.aggregate()` materializes the aggregation cursor inside its
error boundary. It classifies selected `OperationFailure` codes and raises
`StorageQueryRejectedError` with a safe message:

| Code | Classification |
| --- | --- |
| `2` | Unsupported database values or operations. This is a broad bad-value category, not a precise diagnosis of one sort problem. |
| `13103` | Too many sort fields. |
| `51091` | Invalid regular expression. |

`NodeService.query()` translates that storage-level exception into
`QueryValidationError`; the REST layer chooses the HTTP status and JSON
representation. Unknown operation failures and other storage errors retain
their original exceptions. Do not classify every database failure as bad
client input or expose raw driver messages as validation descriptions.

## Blob backend contract

`AssetService` receives a blob object with a `backend_name` and three operations:

| Operation | Storage behavior |
| --- | --- |
| `put_bytes(key, data, content_type=...)` | Write binary bytes under the exact storage key, passing a content type where supported. |
| `open(key)` | Return a dictionary containing a readable binary `stream` and `content_length`. |
| `delete(key)` | Remove the object addressed by that key. |

The local backend resolves its root directory at construction and creates it
if needed. Each key is resolved against that root; a resolved path outside the
root is rejected. It creates parent directories before writing and opens
ordinary binary file streams for reads.

The S3 backend constructs a boto3 client and uses the configured bucket plus
the unchanged storage key for `put_object`, `get_object`, and `delete_object`.
An open result contains the response body stream. `ASSET_S3_ADDRESSING_STYLE`
controls the client's S3 request addressing, not the public descriptor URL.
boto3 is imported only when constructing the S3 backend, so local storage does
not require that optional dependency.

Neither backend interprets node schemas, runs hooks, or checks node ACL.
The service handles schema-context admission and translates missing-blob and
invalid-key errors into domain errors. Other backend failures propagate.
Stream ownership belongs to the caller: direct Python callers close opened
streams, and the delivery route registers stream closure on its response.

## Asset metadata, storage keys, and delivery URLs

An uploaded binary is described by an `_assets` record. Its `id` and `kind`
identify the upload; `module`, `entity`, and `field` retain the original schema
context. `storage_backend` and `storage_key` record its storage location.
`mime_type`, `size`, and image `width`/`height` describe the stored output;
`source_content_type`, `source_filename`, and `cdate` retain source metadata
and creation time.

The original field path remains in metadata because the storage-key component
is normalized and is not an invertible schema-path encoding. The key is built
in core by `core/assets/key_builder.py`, not by a blob backend:

```text
assets/{module}/{entity}/{normalized_field}/{asset_id}/{filename}
```

Core passes the storage key to the blob backend, not a public URL; generated
keys have no leading slash. `AssetService.open_asset()` first loads the
corresponding metadata and then
opens the configured backend. It takes MIME type and size from metadata when
constructing `AssetOpenResult`. The recorded `storage_backend` is not a
per-record backend router: the container supplies the backend used to open
assets. Changing the configuration does not copy existing binary data.

Descriptor URL construction is a separate core concern. It can point at
Sandala's delivery route, a CDN, or direct storage delivery without changing
the key passed to the backend. Conversely, a node may contain an external
descriptor URL with no `_assets` record. The public mapping and examples are
in [Storage keys and descriptor URLs](../reference/rest-api/assets.md#storage-keys-and-descriptor-urls).

## Consistency boundaries

Node patch uses a read, candidate construction, and whole-document replacement.
The replacement has no version predicate or compare-and-swap condition, so
concurrent edits can overwrite one another. Index-enforced uniqueness is a
separate guarantee; it does not make the entire service operation atomic.

Moves update the selected node and then its descendants. Hierarchy updates
include soft-deleted descendants, whereas ACL and delete subtree operations
select active nodes. Recursive ACL changes use ordered `bulk_write()`;
subtree deletion uses `update_many()`. Neither provides an all-or-nothing
transaction across the subtree.

Asset storage also spans more than one persistence operation: `AssetService`
writes the blob, then inserts its metadata, and the client or a hook separately
assigns a descriptor to a node. These steps have no shared transaction or
automatic rollback. A node update or deletion does not itself delete the
binary object. Keep these ownership boundaries explicit when changing
storage coordination rather than assuming a repository call covers the whole
workflow.

When changing persistence code, verify index definitions and initialization
paths, ID and timestamp representations, filtering scope, safe error
translation, and stream closure. Changes that affect query results or
multi-node updates also need verification against MongoDB, not only a mocked
repository call. Keep domain validation and hook dispatch in core, and HTTP
formatting in the transport layer.
