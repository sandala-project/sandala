# Link patching

An ordinary node PATCH can be assembled from a resolved read response, but
that response is not a complete view of the stored references. A target hidden
by node ACL disappears from a resolved LinkArray, or leaves a resolved Link as
`null`. Saving the edited value without protection could silently remove a
reference the caller never saw.

This page explains the write-side protection in `NodeService`. The public
behavior and recovery path are defined in
[Protection of ACL-hidden links](../reference/rest-api/nodes.md#protection-of-acl-hidden-links).
[ACL and field visibility](acl-and-field-visibility.md) explains the underlying
permission checks; [Query builder](query-builder.md) explains resolution.

## Scope and trade-off

The protection applies to user-defined Link and LinkArray fields in affected
payload branches, and to the system `parent` link when it is submitted. It is
part of ordinary `NodeService.patch()`, not create or the dedicated ACL patch
operation. `owner` and `group` changes have their own ACL-operation checks.

A stored reference is protected only when all of these conditions hold:

- its target still exists and is not soft-deleted;
- the target's entity is permitted by this field's `x-meta.link.entities`;
- the original caller lacks read permission on that target under node ACL.

For `parent`, the allowed targets are the entity schemas of the current
module, rather than a user-field link list. Missing, deleted, and disallowed
targets are not preserved by this mechanism. An explicit empty target-entity
list therefore protects no references. Superusers have no ACL-hidden targets.

This is deliberately not a record of what the caller actually read. A caller
may have fetched raw IDs rather than resolved objects; the same protection
still applies. The service cannot distinguish an intentional omission of a
known hidden reference from an accidental omission after resolution. Within
the protected cases, retaining the hidden reference takes precedence.

Query-hook policies are outside this rule. A reference hidden only by a
required query filter or output exclusion is not protected. Integrators using
those policies own their safe-editing behavior; a new read policy does not
automatically become a write-side preservation policy.

## Placement in the patch lifecycle

The relevant part of the ordinary patch path is:

```text
NodeService.patch(module, node_id, payload, actor=...)
    ├── load raw current node and entity schema
    ├── reject client ACL changes; check field write modes and node w
    ├── copy payload and protect ACL-hidden references for the original actor
    ├── dispatch before_patch with the prepared payload
    ├── construct and validate the candidate using the effective actor
    └── persist, run after_patch, and read the response
```

Protection works on the raw current node, not its projected representation.
It runs before `before_patch`, so that handler sees any completed LinkArray
values. A handler changing the actor does not retroactively change which
references were protected: the decision belongs to the original caller.

Protection is not rerun after the handler. Hooks are trusted application code
and may deliberately change the prepared payload, subject to the remaining
service checks. Do not move protection after a hook or run it under a newly
elevated actor: either change would alter the meaning of the original edit.
The full hook contract is in [Node hooks](../reference/node-hooks.md#write-hooks).

## Discover only affected reference paths

`_collect_link_patch_paths()` walks the entity schema alongside the current
value and patch payload. It unwraps nullable schemas before interpreting
semantic types. At the document root it enters only fields present in the
payload; an omitted top-level field is not being replaced.

A supplied Object is different. PATCH replaces its entire value rather than
merging individual children. The walker therefore examines its schema-defined
children even when a child reference is missing from the supplied Object.
For example, replacing `metadata` with `{"note": "updated"}` also affects an
omitted `metadata.editor` Link or `metadata.reviewers` LinkArray. Ignoring those
missing children would let a containing Object bypass reference protection.

Discovery records one of two shapes:

- `_LinkPatchPath` identifies a reference at an unambiguous Object path, with
  its target module, allowed entities, and single/multiple-reference kind.
- `_ArrayNestedLinkPatchPath` records the outermost ordinary Array path, its
  schema, and the remaining schema-relative route to a reference. It does not
  establish an identity for an Array item.

The walker adds `parent` separately, using the current module's entity scope.
System ACL fields do not enter this user-schema traversal.

### Container removal is not reference editing

Discovery stops when an Object or Array container is omitted within a
replacement Object or supplied as `null`; an empty ordinary Array has no items
to inspect. Removing that container is not treated as an attempt to edit each
of its descendant references. Schema validation still decides whether that
container may be absent, null, or empty.

Distinguish those container cases from a reference value. A supplied empty
LinkArray still edits the reference field, and a null LinkArray cannot retain
protected IDs. A supplied Object with an omitted direct child Link or
LinkArray also edits that reference, as described above.

For array-nested references, once discovery records a relative reference
route, its protection check covers that route throughout the current
outermost Array. It does not check only the items whose positions happened to
be visited during payload discovery.

## Classify targets without resolving them

The service gathers current reference IDs for the discovered paths, deduplicates
the IDs by target module, and calls `NodeRepository.find_active_by_ids()` once
for each module with IDs to inspect. The repository returns only `id`,
`entity`, `owner`, `group`, and `perm` for active targets.

This is a metadata read, not a second resolved query. `NodeService` checks the
allowed entity list for each field and calls `_can_node_action(...,
permission="r")` to classify its targets. Storage does not decide which
references are hidden, and neither query hooks nor field visibility are used
to determine target-node ACL.

No target-node query is needed when discovery finds no relevant references or
there are no current IDs to inspect. Work is grouped by module, not by link
field, Array item, or reference occurrence. Reusing those target snapshots is
also what makes checks across several nested Arrays practical.

## References outside ordinary Arrays

For each unambiguous path, the service compares protected current IDs with
the submitted reference IDs:

| Submitted field | Action when a protected ID is missing |
| --- | --- |
| LinkArray with a list value | Append missing protected occurrences to the list. |
| LinkArray omitted from a replacement Object, or supplied as `null` | Reject: no list is available to complete. |
| Link, including `parent` | Reject: restoring a single value would replace the caller's chosen value. |

For example, where A and C are readable and B is ACL-hidden:

```text
stored reviewers:    [A, B]
resolved reviewers:  [object(A)]
submitted reviewers: [C]
prepared reviewers:  [C, B]
```

The readable A can be intentionally removed; only B is restored. Submitted
values keep their order, and missing protected occurrences are appended in
their current stored order. This does not promise an order for subsequent
LinkArray resolution or restore previous list positions.

The comparison uses occurrence counts, not just sets. `_missing_reference_ids()`
uses `Counter` so duplicate protected IDs are not silently collapsed, and an
already retained occurrence is not appended again. This is preservation of
current multiplicity, not a new uniqueness rule for LinkArray.

Completion does not bypass candidate schema validation. The resulting list
must still satisfy the field's constraints, including `minItems` and `maxItems`.

Single Link values cannot be completed in that way. If the current hidden
target is H, neither `null`, a different ID, nor an omitted child Link in a
replacement Object retains H. The operation fails rather than guessing a
replacement value. The same rule protects `parent` from an accidental move to
the module root when its resolved parent was null.

## References below ordinary Arrays

An Array item has no service-defined identity. Position is not identity:
items may have been reordered, inserted, or removed. Even an Array containing
another Object between it and the reference has the same ambiguity. Appending
a hidden ID to the item at its old index could attach it to the wrong item.

The service therefore never automatically inserts hidden references below an
ordinary Array. For each discovered reference route it:

1. traverses that route across all current items of the outermost Array;
2. classifies the current reference occurrences using the target metadata;
3. collects submitted occurrences along the same route across the replacement
   Array;
4. requires every protected occurrence to remain somewhere on that route.

The containment check also uses `Counter`. Readable IDs may be absent, and
Array items may change order; protected IDs cannot be replaced by a different
ID or moved to a different reference field. If there are no protected
occurrences, this guard does not restrict the edit.

For example:

```text
sections[] → member → team → groups[] → group → reviewers: LinkArray
```

`sections` is the outermost Array. Discovery retains the route through the
intervening Objects and `groups` Array. `_collect_link_values_in_array_branch()`
then traverses that complete route in the current and submitted `sections`
values. The check is not repeated independently at each `groups` index.

Passing this check establishes retention across the branch, not that a
protected target stayed attached to the same logical item. The service has no
identity with which to establish that stronger invariant. Do not introduce
index-based pairing as an apparent fix for this limitation.

## Rejection and recovery

Failures raise `LinkPatchAclHiddenReferencesMissingError`, with code
`link_patch_acl_hidden_references_missing`. They happen before `before_patch`
and before persistence. The exception includes one `details.field_errors`
entry for each blocked location:

- an unambiguous reference uses its own field path;
- an array-nested reference uses its outermost ordinary Array path.

Locations are deduplicated and use the normal string/integer segment format.
Each entry has keyword `acl_hidden_references`; target IDs are not included
in the error. Reporting the Array rather than an old item index avoids
pointing at an item the user may already have moved or removed.

A caller can fetch the node with `project=["*"]` to obtain stored reference
IDs without resolution, subject to field visibility and query hooks, then
include the protected IDs in the relevant values. Raw source IDs do not grant
read permission on the referenced target nodes. The exact request is in the
[Nodes reference](../reference/rest-api/nodes.md#protection-of-acl-hidden-links).

Keep this protection separate from candidate schema validation, hierarchy
checks, and ACL mutation rules. Passing it does not establish that a new ID
exists or is an allowed target; user-defined links may be dangling. It also
does not make the metadata read and later node replacement a transaction.
