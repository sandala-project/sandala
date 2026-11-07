# Assets

Sandala uploads binary objects and returns descriptors for the `Image`, `File`,
and `Video` semantic types. This page defines the upload and delivery HTTP
contracts. For the data model, public-access implications, and the distinction
between an uploaded asset and a node field, see [Assets](../../concepts/assets.md).

The upload paths on this page are below `/api/v1/`. The delivery path is
deliberately outside that prefix.

## Upload request format

All uploads use `multipart/form-data`; they do not use a JSON request body.
Every upload has these parts:

| Part | Required | Value |
| --- | --- | --- |
| `file` | Yes | The binary upload. Its filename and MIME type, when supplied by the multipart client, are retained as source metadata. |
| `target` | Yes | A JSON object encoded as a form string. It identifies the schema context for the upload. |
| `transform` | Images only, optional | A JSON object encoded as a form string that requests image output processing. |

`target` has exactly the following meaningful properties:

```json
{
  "module": "library",
  "entity": "Book",
  "field": "cover"
}
```

| Property | Rules |
| --- | --- |
| `module` | Non-empty module name. |
| `entity` | Non-empty entity name in that module. |
| `field` | Non-empty schema field path in dot notation. |

The target field must exist, have the semantic type accepted by the endpoint,
and be writable by the current actor according to its `x-meta.write-mode`.
Upload authentication is optional: an anonymous request can upload only to a
target field whose write mode is `all`. This is a schema-field permission
check, not node ACL: no node is identified or modified by an upload.

The returned descriptor is not bound to the target field. A client or hook can
later place it in any schema-compatible field it is allowed to write.

Field paths pass through object properties with dots. They never use array
indices: use `gallery.image` for an `Image` property of objects in `gallery`,
and use `gallery` itself for an array whose direct items are `Image` values.

## Upload an image

`POST /uploads/assets/images/`

The target field must be `Image` or `RichText`. `RichText` is accepted so an
editor can upload an image and insert the returned URL into text content.

Sandala accepts JPEG, PNG, GIF, and WebP input. It validates the actual image
data rather than relying on the uploaded filename or declared MIME type. A
successful request returns `201 Created`:

```json
{
  "image": {
    "url": "/assets/library/Book/cover/6e0d5b3b-02ef-4ca8-b996-17b7e0a1b1f3/cover.webp",
    "mime-type": "image/webp",
    "width": 640,
    "height": 960,
    "size": 84231
  }
}
```

| Descriptor field | Meaning |
| --- | --- |
| `url` | Public delivery URL of the stored object. |
| `mime-type` | MIME type of the stored image. |
| `width`, `height` | Dimensions of the stored image in pixels. EXIF orientation is accounted for. |
| `size` | Size of the stored image in bytes. |

Without `transform`, Sandala stores the original image bytes. With a
transformation, it stores only the resulting image.

### Image transformations

`transform` is a JSON object with this shape:

```json
{
  "format": "webp",
  "width": 640,
  "height": 960,
  "fit": "cover"
}
```

| Property | Required | Rules |
| --- | --- | --- |
| `format` | Yes | Output format: `jpg`, `png`, or `webp`. |
| `width` | No | Positive integer. |
| `height` | No | Positive integer. |
| `fit` | No | `inside` (the default) or `cover`. Used when both dimensions are present. |

Providing only `format` transcodes without resizing. Providing one dimension
resizes proportionally. With both dimensions, `inside` fits the image within
the requested rectangle and preserves its aspect ratio; `cover` crops it to
the exact requested size. Animated GIF transformation uses the first frame and
produces a static image. JPEG output flattens transparency onto a white
background.

For example, this request produces a WebP image that fits inside a
640-by-960 rectangle:

```bash
curl --request POST http://localhost:3000/api/v1/uploads/assets/images/ \
  --form 'file=@cover.png' \
  --form 'target={"module":"library","entity":"Book","field":"cover"}' \
  --form 'transform={"format":"webp","width":640,"height":960,"fit":"inside"}'
```

## Upload a file

`POST /uploads/assets/files/`

The target field must be `File`. On success the endpoint returns `201 Created`:

```json
{
  "file": {
    "url": "/assets/library/Book/manuscript/4d2d1e51-e0ab-4a33-a3e3-1a5519c9a4ee/manuscript.pdf",
    "mime-type": "application/pdf",
    "size": 182736
  }
}
```

Sandala does not inspect the binary format of a file upload. Its `mime-type`
is the multipart content type when present, otherwise a type guessed from the
filename, or `application/octet-stream` when neither is available.

## Upload a video

`POST /uploads/assets/videos/`

The target field must be `Video`. Its successful `201 Created` response has
the same descriptor shape as a file upload, in a `video` wrapper:

```json
{
  "video": {
    "url": "/assets/library/Book/trailer/18f27d54-cc61-4e40-9690-2db3117810a7/trailer.mp4",
    "mime-type": "video/mp4",
    "size": 2458810
  }
}
```

Sandala does not inspect or transcode video data. MIME type selection follows
the same rules as file uploads.

## Public asset delivery

`GET /assets/{storage_key_tail}`

This route returns the binary object addressed by its storage key. It is not
under `/api/v1/` and requires no authentication. Sandala does not apply node
ACL or field visibility when delivering an asset. Treat every URL returned by
an upload as publicly shareable.

A successful response streams the stored bytes with the stored `Content-Type`
and `Content-Length` headers. It also includes:

```text
Cache-Control: public, max-age=31536000, immutable
```

## Storage keys and descriptor URLs

Every upload receives a generated storage key:

```text
assets/{module}/{entity}/{normalized_field}/{asset_id}/{filename}
```

`asset_id` is a UUID. `normalized_field` is based on the target field path:
dot-separated segments are joined with `__`, and characters unsuitable for a
storage-path segment are replaced. The filename is based on the supplied
filename and the extension of the stored object; it becomes `asset.<ext>` when
there is no usable filename. A storage key is an implementation-facing address
for the object, not a reversible encoding of a schema path.

With the default configuration, an upload descriptor's `url` is the storage
key with a leading slash. For example:

```text
storage key: assets/library/Book/cover/6e0d5b3b-02ef-4ca8-b996-17b7e0a1b1f3/cover.webp
URL:         /assets/library/Book/cover/6e0d5b3b-02ef-4ca8-b996-17b7e0a1b1f3/cover.webp
```

The `/assets/` HTTP route accounts for the first `assets` segment itself, so
its `{storage_key_tail}` begins with `library` in this example.

Set `ASSET_PUBLIC_BASE_URL` to make descriptors point at a public origin or
path prefix instead:

```text
ASSET_PUBLIC_BASE_URL=https://cdn.example.com/media
descriptor URL: https://cdn.example.com/media/assets/library/Book/cover/...
```

This setting changes returned descriptor URLs; it does not move the object or
change its storage key. It lets a CDN, reverse proxy, or object-storage public
endpoint deliver the same key path. Backend and public-URL configuration is
described in [Configuration](../configuration.md#asset-storage).

## Errors

All failures use the [common error contract](errors.md).

### Upload an image, file, or video

`POST /uploads/assets/images/`, `POST /uploads/assets/files/`, and
`POST /uploads/assets/videos/`

Uploads are optional-authentication endpoints. An anonymous request is valid
when the target field has `write-mode: all`; a supplied invalid credential
returns `401` with `authentication_error`.

| Status | Error code | Meaning |
| --- | --- | --- |
| `400` | `parameter_invalid` | The required `target` form part is missing, or `target` is malformed JSON or is not a JSON object. For image uploads, this also covers a malformed or non-object `transform` part. |
| `400` | `asset_file_missing` | The multipart form has no `file` part. |
| `400` | `asset_target_invalid` | `target`, its module/entity/field members, or its field-path syntax is malformed. |
| `400` | `asset_target_field_not_found` | The target field path does not exist in the entity schema. |
| `400` | `asset_target_semantic_type_mismatch` | The target field does not have a semantic type accepted by this upload endpoint. |
| `400` | `field_write_forbidden` | The target field is not writable by the current actor according to its field write mode. |
| `400` | `validation_error` | The target path cannot be traversed through its schema, or the stored schema has an invalid field container or write mode. |
| `404` | `not_found` | The target module and entity do not identify an existing entity schema. |

### Upload an image

`POST /uploads/assets/images/`

In addition to the shared upload errors:

| Status | Error code | Meaning |
| --- | --- | --- |
| `400` | `asset_unsupported_image_format` | The image format is not JPEG, PNG, GIF, or WebP. |
| `400` | `asset_invalid_image_file` | The uploaded bytes cannot be read as a valid image. |
| `400` | `asset_transform_invalid` | The parsed `transform` has invalid dimensions or fit mode. |
| `400` | `asset_transform_format_unsupported` | `transform.format` is not `jpg`, `png`, or `webp`. |

### Public asset delivery

`GET /assets/{storage_key_tail}`

| Status | Error code | Meaning |
| --- | --- | --- |
| `404` | `not_found` | The storage key has no metadata record, or its stored binary object is unavailable. |
| `400` | `asset_storage_key_invalid` | A backend rejects the stored key as invalid. |
| `400` | `validation_error` | The asset metadata record has no valid stored MIME type or byte size. |
