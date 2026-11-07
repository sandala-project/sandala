# Frontend architecture

This page is for contributors to `admin-ui/`, Sandala's first-party React
application. It records the boundaries that keep a schema-driven UI aligned
with the backend.

## Boundaries and source of truth

The backend is authoritative for authentication, ACL, field visibility and
write modes, node and schema validation, and all domain invariants. The client
may validate forms for immediate feedback, but it does not reproduce backend
authorization or business rules.

Keep HTTP access in `src/lib/api.ts` and the feature API modules. Screens and
field components use those thin clients rather than constructing independent
requests. Backend errors retain their machine-readable structure so that the
form layer can associate a reported location with the relevant field.

`src/app/App.tsx` composes the shared providers: React Query, theme, i18n, and
authentication. New screens belong behind this foundation rather than adding
parallel session, locale, theme, or API mechanisms.

## Routes and application shell

The SPA reserves `/_app/` below its deployment mount point. This prevents
application routes from colliding with static assets or the mount root. The
route configuration is in `src/router/router.tsx`; `src/router/routeConfig.ts`
owns the prefix constant.

The protected application has three areas: Nodes, Entities, and Settings.
Unauthenticated access redirects to `/_app/login` with the current internal
location retained for the return after sign-in. `AppShell` permits only
`admin` and `superuser` users. It exposes the Entities area read-only to an
`admin`; only a superuser gets structure-changing controls. These UI checks
improve usability but never replace server checks.

Routes express addressable working context. In particular, Tree can encode a
module and selected node, Table can encode a module and entity, and Entities
can encode a module and entity. Do not make incidental overlays or ephemeral
widget state into routes without a restoration or deep-linking reason.

## Server state and working snapshots

React Query caches structural metadata such as modules, entity lists, and
schemas during an authenticated session. Use the canonical query keys and
invalidate or update affected metadata after structural mutations.

Node data is deliberately more local. A table, tree, picker, and editor own
their active snapshots and must not treat one another's compact records as
full node documents. Opening a full editor fetches the node separately. When
a session ends, auth handling clears non-session query data.

This separation prevents stale table rows or tree summaries from becoming an
editor draft and keeps link display values scoped to the surface that loaded
them.

Preserve these refresh and lifetime rules:

- A tree branch loads children on expansion. Collapsing it discards loaded
  descendants and their branch states; expanding it again fetches fresh data.
  A successful response replaces the branch rather than merging in old nodes
  absent from that response.
- Table pages belong only to the active table. After an existing node changes,
  replace its row immediately with the mutation response, then refetch all
  loaded pages. Keep the visible table, page set, and scroll position during
  that refresh; the returned pages reconcile row placement and filter membership.
- Closing a full editor releases its loaded document. Reopening performs a new
  GET. Parent-picker branches and link-search results likewise belong to their
  open picker/menu, not a cross-surface node cache.
- Saving a linked node updates its representations in the originating editor,
  including nested links; a table context also reconciles its loaded pages.

The query options in `src/lib/queryOptions.ts` encode the distinction:
structural metadata remains fresh for the session, while node queries use
zero stale and garbage-collection times and refetch on mount. Do not turn
compact records into reusable full-node snapshots to avoid a request.

Link search uses the same schema keys and session metadata cache as labels and
editors. A pure filter builder uses the existing editor-schema visibility logic
to select searchable text fields from the reference label template and the shared
fallback list. Template path extraction and label rendering share the same syntax;
only Object paths are traversed for search. The open menu runs a separate node query for
each allowed entity, with a root `entity` constraint so path validation uses that
entity's schema. Results retain the menu-scoped lifetime described above; the API
client does not fetch metadata or determine field access.

## Schema-driven editors

Node and schema editors are built from entity schemas, semantic metadata, and
the current actor's capabilities. Do not add entity-specific form screens.
Use the existing recursive renderers and specialized controls for links,
assets, rich text, arrays, objects, enums, and passwords.

Forms hold a local draft distinct from the loaded server document. Containers
own loading, draft lifecycle, submission, and mutation results; renderers own
recursive presentation; validation helpers remain outside JSX. Preserve focus,
scroll position, and nested draft state during local updates where possible.

`Password` values are input-only. The UI uses matching masked inputs and does
not show an existing value, even if a malformed stored document contains one.

The user-facing editor, visual-query, and UTC date-control rules are in
[Admin UI](../reference/admin-ui.md). Keep shared date conversions in
`src/lib/dateTime.ts` so node forms, table editors, filters, and PAT controls
do not interpret the same input in different timezones.

## Validation and error presentation

Forms validate individual fields on blur and validate the complete draft at
submission. Keep these immediate UX checks separate from authoritative server
validation and from the recursive renderer.

`src/lib/errors.ts` normalizes API failures and localizes their machine codes.
Use `error` and structured `details` for decisions, not parsed
`error_description` text. Map `field_errors[*].location` into the form and
translate each `keyword`; when its translation is unavailable, use the field
error's `message` as a fallback. The general description is a fallback for
unrecognized errors, not the localization contract.

Show field errors beside their controls and a summary in the form. When field
errors exist, activating the summary scrolls the editor to the first error;
otherwise the summary is ordinary text. The shared technical-details dialog
shows the HTTP status, machine code, and original response JSON without
localizing the diagnostic payload. Use the shared components in
`src/components/Form.tsx` and `ApiErrorDetailsOverlay.tsx` rather than building
feature-specific error presentations.

## UI foundations

All product strings belong in `src/locales/`; module, entity, and field names
are backend data rather than translated interface strings. Theme, locale, and
split-pane layout preferences are browser-local settings.

The default locale is `en-US`. Language changes apply without a page reload;
the selected locale is kept in `localStorage`, not written into the user node.

Prefer shared primitives in `src/components/` for repeated controls, panels,
dialogs, and layout. Keep global styling organized in `src/styles/global.css`;
avoid a second visual system inside a feature. The intended product remains
desktop-first, with a supported minimum workspace width of 900 px.

## Build and test

Run these commands from `admin-ui/`:

```bash
npm run check
npm run build
```

`npm run build` type-checks the application and creates the production static
bundle. `ADMIN_UI_DIST` is described in [Configuration](../reference/configuration.md).
User-facing workflows belong in [Using the Admin UI](../guides/using-the-admin-ui.md).
