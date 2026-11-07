# Managing assets

Sandala stores uploaded images, files, and videos as independent binary
objects. An upload returns a descriptor that fits an `Image`, `File`, or
`Video` field; a separate node create or patch stores that descriptor in
content.

This separation is deliberate. Uploading a file does not identify, read, or
modify a node. It checks a schema field as an upload context, then returns a
descriptor that a client or hook may later place in any compatible field.

Examples use the `library` module and assume that `SANDALA_URL` and
`COOKIE_JAR` are configured as in the [Quickstart](../getting-started/quickstart.md).
The exact endpoint and error contracts are in [Assets](../reference/rest-api/assets.md).

## Prepare an asset field

An upload target names a schema field, so the schema must exist first. For
example, a Book schema can define an `Image` field named `cover`:

```json
{
  "cover": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "url": {"type": "string"},
      "mime-type": {"type": "string"},
      "width": {"type": "integer"},
      "height": {"type": "integer"},
      "size": {"type": "integer"}
    },
    "required": ["url"],
    "x-meta": {
      "semantic-type": "Image",
      "visibility-mode": "all",
      "write-mode": "all"
    }
  }
}
```

The upload endpoint selects its accepted type from this field:

| Endpoint | Accepted target type | Returned descriptor wrapper |
| --- | --- | --- |
| `POST /uploads/assets/images/` | `Image` or `RichText` | `image` |
| `POST /uploads/assets/files/` | `File` | `file` |
| `POST /uploads/assets/videos/` | `Video` | `video` |

For an `Image`, `File`, or `Video` within an Object, use its dot path, such as
`metadata.cover`. Array paths never include item indexes: use `gallery` when
the array items are Image values, or `gallery.image` when each array item is
an Object with an `image` property.

The semantic-type reference defines the exact descriptor shapes and allowed
schema keywords. A descriptor can also contain an external URL; Sandala upload
is not required for every asset value.

## Upload an image

Send the binary file and a JSON `target` string as `multipart/form-data`.
`transform` is optional: omit it to store the original image bytes unchanged.

```bash
curl --fail-with-body --silent --show-error \
  --request POST \
  --cookie "$COOKIE_JAR" \
  --form 'file=@cover.png' \
  --form 'target={"module":"library","entity":"Book","field":"cover"}' \
  "$SANDALA_URL/uploads/assets/images/"
```

The response has status `201 Created` and contains a descriptor:

```json
{
  "image": {
    "url": "/assets/library/Book/cover/6e0d5b3b-02ef-4ca8-b996-17b7e0a1b1f3/cover.png",
    "mime-type": "image/png",
    "width": 640,
    "height": 960,
    "size": 84231
  }
}
```

### Optionally transform an image

Add a `transform` form part only when Sandala should produce a converted or
resized image instead of the original:

```text
--form 'transform={"format":"webp","width":640,"height":960,"fit":"inside"}'
```

Sandala validates actual JPEG, PNG, GIF, or WebP image data; it does not trust
only the filename or supplied MIME type. An image transform requires an output
`format` of `jpg`, `png`, or `webp`. One requested dimension preserves aspect
ratio. With both dimensions, `inside` fits within the rectangle and `cover`
crops to its exact size. The example transform produces a WebP descriptor;
without that form part, the descriptor describes the stored original image.

Use the same pattern for a file or video, without `transform`:

```bash
curl --fail-with-body --silent --show-error \
  --request POST \
  --cookie "$COOKIE_JAR" \
  --form 'file=@manuscript.pdf' \
  --form 'target={"module":"library","entity":"Book","field":"manuscript"}' \
  "$SANDALA_URL/uploads/assets/files/"
```

File and video uploads do not inspect or transcode binary content. Their MIME
type comes from multipart metadata when available, then the filename, then
`application/octet-stream`. Do not treat that type as security validation:
scan or validate untrusted uploaded content in an integration when necessary.

## Store the descriptor in a node

The target above is not a node ID. It only verifies a schema context and field
write mode; the successful upload has not attached anything to a Book yet.
Use the returned descriptor in an ordinary node create or patch:

```bash
curl --fail-with-body --silent --show-error \
  --request PATCH \
  --cookie "$COOKIE_JAR" \
  --header 'Content-Type: application/json' \
  --data '{
    "node": {
      "cover": {
        "url": "/assets/library/Book/cover/6e0d5b3b-02ef-4ca8-b996-17b7e0a1b1f3/cover.png",
        "mime-type": "image/png",
        "width": 640,
        "height": 960,
        "size": 84231
      }
    }
  }' \
  "$SANDALA_URL/nodes/library/b0313e66-29a7-40b4-a235-e55f99f66826/"
```

This second operation needs the usual node `w` permission and field
`write-mode`; upload permission alone is not enough to edit a particular node.
Conversely, a descriptor returned for `Book.cover` is not technically bound to
that field. A client may place it in any compatible writable asset field.

For an `Image` upload targeting a `RichText` field, insert the returned
`image.url` into the rich-text value rather than storing the whole Image
descriptor in the text field.

## Understand upload permission

An upload has no node in its request, so it does not evaluate node `owner`,
`group`, or `perm`. It evaluates only the target field's schema and
`x-meta.write-mode`:

- an anonymous client may upload only to a target field with `write-mode: all`;
- an authenticated client may upload when its role satisfies that field's write
  mode;
- a field that is missing, has the wrong semantic type, or is not writable
  rejects the upload before a descriptor is created.

This check limits admission to storage and gives upload tooling a known
descriptor shape. It does not imply that the eventual node value is readable
or writable by the same actor.

## Treat every returned URL as public

The current delivery route, `GET /assets/{storage_key_tail}`, requires no
authentication and does not check node ACL or field visibility. A URL returned
by an upload is therefore publicly shareable. Hiding the descriptor field in a
node does not make an already issued asset URL private.

Do not upload protected documents, private images, or secrets through this
delivery model. An integration that needs protected binary content must use an
access-controlled delivery layer rather than relying on Sandala's public asset
route.

By default, Sandala returns a relative `/assets/...` URL and serves that key
through its own route. `ASSET_PUBLIC_BASE_URL` changes new descriptor URLs to
an external public origin or path prefix, such as a CDN, without moving the
stored object or changing its storage key. See [Asset storage configuration](../reference/configuration.md#asset-storage)
for local and S3-compatible storage settings.

Each upload receives a new UUID-based storage key and a new URL. Delivered
asset responses are cacheable as immutable public content, so a client should
use the newly returned descriptor after replacing an asset instead of assuming
that an old URL changes in place.

## Handle common failures

Treat upload and node update as separate steps with separate error handling:

1. On an upload error, keep the node unchanged and show the target, file, or
   transform problem to the user.
2. On a successful upload followed by a node-patch error, keep the descriptor
   available for a retry if appropriate; do not silently repeat the upload and
   create needless duplicate objects.
3. On a delivery `404`, handle it as a missing public object. It can mean that
   the asset metadata or its binary data is no longer available.

The [assets API error table](../reference/rest-api/assets.md#errors) lists the
machine-readable error codes for malformed targets, wrong field types,
forbidden target fields, invalid images, transforms, and delivery failures.

The Admin UI follows this lifecycle for asset controls: it uploads first and
then writes the descriptor through the node editor. See [Using the Admin UI](using-the-admin-ui.md)
for that workflow.
