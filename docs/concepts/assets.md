# Assets

Sandala's asset subsystem stores binary files and returns descriptors that fit
the `Image`, `File`, and `Video` semantic types. It is optional: a node may
also contain a descriptor with an external URL, without using Sandala's upload
or delivery endpoints.

Assets are independent from nodes. Uploading a file produces a descriptor; the
client or a hook later puts that descriptor into a node. Conversely, changing
or deleting a node does not delete its uploaded files.

## Descriptors

An upload response contains a descriptor ready to place in a matching field:

```json
{
  "url": "/assets/library/Book/cover/6e0d5b3b-02ef-4ca8-b996-17b7e0a1b1f3/cover.webp",
  "mime-type": "image/webp",
  "width": 640,
  "height": 960,
  "size": 84231
}
```

`File` and `Video` descriptors contain `url`, `mime-type`, and `size`.
`Image` descriptors additionally contain `width` and `height`. The descriptor
schema requires only `url`; the remaining fields describe the uploaded object
when Sandala knows them.

## Upload context

The three upload endpoints accept `multipart/form-data` with a binary `file`
part and a JSON `target` part:

```json
{
  "module": "library",
  "entity": "Book",
  "field": "cover"
}
```

`target` is a schema context, not a location in a particular node. It has no
node ID and the upload does not write the resulting descriptor into that field.
It serves three purposes:

1. Sandala checks that the module, entity, and field path exist in the schema.
2. It checks that the field has the semantic type accepted by the endpoint.
3. It checks the field's `x-meta.write-mode` for the current actor.

The endpoints are:

| Endpoint | Accepted target type | Response field |
| --- | --- | --- |
| `POST /api/v1/uploads/assets/images/` | `Image` or `RichText` | `image` |
| `POST /api/v1/uploads/assets/files/` | `File` | `file` |
| `POST /api/v1/uploads/assets/videos/` | `Video` | `video` |

The image endpoint accepts `RichText` so an editor can upload an image and
insert its URL into rich-text content.

Field paths use schema dot notation. For an image directly in an Array, use the
Array field's path; for an image property of objects inside an Array, use its
property path without an item index. For example, `gallery.image` identifies
the `image` property of each object in `gallery`.

## Upload permission is not node ACL

An upload may occur before any node exists, so Sandala does not check a node's
`owner`, `group`, or `perm` against `target`. It checks only the target field's
write mode. An anonymous upload is therefore possible only for a field with
`write-mode: all`.

This is a write-admission mechanism for the asset store, not a guarantee that
the descriptor will be used in the named field. After a successful upload, a
client can put the descriptor into any schema-compatible field it is otherwise
allowed to patch.

## Images and transformations

Sandala accepts JPEG, PNG, GIF, and WebP image uploads. It inspects the image
and returns the resulting MIME type, dimensions, and byte size.

An image upload may include a `transform` object that selects an output format
(`jpg`, `png`, or `webp`), optional dimensions, and an `inside` or `cover` fit
mode. Without `transform`, Sandala stores the original bytes. With it, Sandala
stores only the transformed output. Image dimensions use visual orientation
after EXIF orientation is applied; transforming an animated GIF uses its first
frame and produces a static image.

File and video uploads do not perform content-format inspection. Their MIME
type comes from the supplied content type, the filename when it can be guessed,
or `application/octet-stream` as a fallback.

## Storage and delivery

Sandala stores metadata in its internal `_assets` collection and binary data in
either a local directory or an S3-compatible bucket. `ASSET_STORAGE_BACKEND`
selects the backend; see [Configuration](../reference/configuration.md) for
the available settings.

Each object has a generated storage key shaped like:

```text
assets/{module}/{entity}/{normalized_field}/{asset_id}/{filename}
```

The key keeps uploads from different schema contexts in separate logical
prefixes. The field component is normalized for a storage path—for example,
`metadata.cover` becomes `metadata__cover`—and is not an invertible schema-path
encoding.

By default a descriptor URL is the storage key with a leading slash, and
Sandala serves it through its public `/assets/` route. Setting
`ASSET_PUBLIC_BASE_URL` makes upload responses use an external base URL
instead, such as a CDN. The exact URL mapping and S3 configuration belong in
the [assets API reference](../reference/rest-api/assets.md).

## Public URLs

Asset delivery is public in the current model. The `/assets/` route does not
authenticate the requester and does not inspect node ACL or field visibility.
Permission to upload in a schema context is not permission to read a returned
URL, and restricting a field's visibility does not make an already issued asset
URL private.

Treat every Sandala-managed asset URL as publicly shareable. If an integration
needs protected binary content, it must provide an access-controlled delivery
layer rather than relying on the current public asset route.
