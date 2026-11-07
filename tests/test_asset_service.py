from __future__ import annotations

from io import BytesIO

from PIL import Image

from sandala.core.errors import (
    AssetStorageKeyInvalidError,
    AssetTransformInvalidError,
    FieldWriteForbiddenError,
    NotFoundError,
    ParameterInvalidError,
    ValidationError,
)
from sandala.core.services.asset_service import AssetService


class FakeEntityRepo:
    def __init__(self):
        self.schemas = {
            ("catalog", "Product"): {
                "type": "object",
                "properties": {
                    "cover": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "mime-type": {"type": "string"},
                            "width": {"type": "integer"},
                            "height": {"type": "integer"},
                            "size": {"type": "integer"},
                        },
                        "required": ["url", "mime-type", "width", "height", "size"],
                        "additionalProperties": False,
                        "x-meta": {"semantic-type": "Image", "visibility-mode": "all", "write-mode": "all"},
                    },
                    "manual": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "mime-type": {"type": "string"},
                            "size": {"type": "integer"},
                        },
                        "required": ["url", "mime-type", "size"],
                        "additionalProperties": False,
                        "x-meta": {"semantic-type": "File", "visibility-mode": "all", "write-mode": "admin"},
                    },
                    "clip": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "mime-type": {"type": "string"},
                            "size": {"type": "integer"},
                        },
                        "required": ["url", "mime-type", "size"],
                        "additionalProperties": False,
                        "x-meta": {"semantic-type": "Video", "visibility-mode": "all", "write-mode": "all"},
                    },
                    "nested": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "hero": {
                                "type": "object",
                                "properties": {
                                    "url": {"type": "string"},
                                    "mime-type": {"type": "string"},
                                    "width": {"type": "integer"},
                                    "height": {"type": "integer"},
                                    "size": {"type": "integer"},
                                },
                                "required": ["url", "mime-type", "width", "height", "size"],
                                "additionalProperties": False,
                                "x-meta": {"semantic-type": "Image", "visibility-mode": "all", "write-mode": "all"},
                            }
                        },
                        "x-meta": {"semantic-type": "Object", "visibility-mode": "all", "write-mode": "all"},
                    },
                    "gallery": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "image": {
                                    "type": "object",
                                    "properties": {
                                        "url": {"type": "string"},
                                        "mime-type": {"type": "string"},
                                        "width": {"type": "integer"},
                                        "height": {"type": "integer"},
                                        "size": {"type": "integer"},
                                    },
                                    "required": ["url", "mime-type", "width", "height", "size"],
                                    "additionalProperties": False,
                                    "x-meta": {"semantic-type": "Image", "visibility-mode": "all", "write-mode": "all"},
                                }
                            },
                            "x-meta": {"semantic-type": "Object", "visibility-mode": "all", "write-mode": "all"},
                        },
                        "x-meta": {"semantic-type": "Array", "visibility-mode": "all", "write-mode": "all"},
                    },
                    "gallery_direct": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "url": {"type": "string"},
                                "mime-type": {"type": "string"},
                                "width": {"type": "integer"},
                                "height": {"type": "integer"},
                                "size": {"type": "integer"},
                            },
                            "required": ["url", "mime-type", "width", "height", "size"],
                            "additionalProperties": False,
                            "x-meta": {"semantic-type": "Image", "visibility-mode": "all", "write-mode": "all"},
                        },
                        "x-meta": {"semantic-type": "Array", "visibility-mode": "all", "write-mode": "all"},
                    },
                },
            }
        }

    def get_schema(self, module, entity):
        return self.schemas.get((module, entity))


class FakeAssetRepo:
    def __init__(self):
        self.docs = {}

    def create(self, doc):
        self.docs[doc["id"]] = dict(doc)
        return doc

    def find_by_id(self, asset_id):
        doc = self.docs.get(asset_id)
        return dict(doc) if doc else None

    def find_by_storage_key(self, storage_key):
        for doc in self.docs.values():
            if doc.get("storage_key") == storage_key:
                return dict(doc)
        return None


class FakeBlobStorage:
    backend_name = "local_fs"

    def __init__(self):
        self.objects = {}

    def put_bytes(self, key, data, *, content_type=None):
        self.objects[key] = bytes(data)
        return {"key": key, "content_type": content_type, "content_length": len(data)}

    def open(self, key):
        return {"stream": BytesIO(self.objects[key]), "content_length": len(self.objects[key])}

    def delete(self, key):
        self.objects.pop(key, None)


class MissingBlobStorage(FakeBlobStorage):
    def open(self, key):
        raise FileNotFoundError(key)


class InvalidKeyBlobStorage(FakeBlobStorage):
    def open(self, key):
        raise ValueError("Invalid blob storage key")


def test_store_image_without_transform_returns_image_descriptor_and_persists_metadata():
    service, repo, storage = _service()

    data = _make_image_bytes("PNG", size=(64, 32))
    descriptor = service.store_image(
        BytesIO(data),
        filename="cover.png",
        target={"module": "catalog", "entity": "Product", "field": "cover"},
        actor=None,
    )

    assert descriptor["url"].startswith("/assets/")
    assert descriptor["mime-type"] == "image/png"
    assert descriptor["width"] == 64
    assert descriptor["height"] == 32
    assert descriptor["size"] == len(data)

    stored_doc = next(iter(repo.docs.values()))
    assert stored_doc["kind"] == "image"
    assert stored_doc["mime_type"] == "image/png"
    assert stored_doc["source_filename"] == "cover.png"
    assert stored_doc["storage_key"].startswith("assets/catalog/Product/cover/")
    assert storage.objects[stored_doc["storage_key"]] == data


def test_store_image_with_transform_resizes_and_transcodes():
    service, repo, storage = _service()

    descriptor = service.store_image(
        BytesIO(_make_image_bytes("PNG", size=(200, 100))),
        filename="cover.png",
        target={"module": "catalog", "entity": "Product", "field": "nested.hero"},
        transform={"format": "webp", "width": 50},
        actor=None,
    )

    assert descriptor["mime-type"] == "image/webp"
    assert descriptor["width"] == 50
    assert descriptor["height"] == 25

    stored_doc = next(iter(repo.docs.values()))
    assert stored_doc["field"] == "nested.hero"
    assert stored_doc["mime_type"] == "image/webp"
    assert stored_doc["width"] == 50
    assert stored_doc["height"] == 25
    stored_bytes = storage.objects[stored_doc["storage_key"]]
    with Image.open(BytesIO(stored_bytes)) as image:
        assert image.format == "WEBP"
        assert image.size == (50, 25)


def test_store_image_transform_with_cover_uses_crop_when_both_sides_provided():
    service, _, storage = _service()

    descriptor = service.store_image(
        BytesIO(_make_image_bytes("PNG", size=(200, 100))),
        filename="cover.png",
        target={"module": "catalog", "entity": "Product", "field": "cover"},
        transform={"format": "webp", "width": 80, "height": 80, "fit": "cover"},
        actor=None,
    )

    assert descriptor["width"] == 80
    assert descriptor["height"] == 80
    stored_doc = next(iter(storage.objects))
    with Image.open(BytesIO(storage.objects[stored_doc])) as image:
        assert image.size == (80, 80)


def test_store_image_transform_with_inside_keeps_image_within_bounds_when_both_sides_provided():
    service, _, storage = _service()

    descriptor = service.store_image(
        BytesIO(_make_image_bytes("PNG", size=(200, 100))),
        filename="cover.png",
        target={"module": "catalog", "entity": "Product", "field": "cover"},
        transform={"format": "webp", "width": 80, "height": 80, "fit": "inside"},
        actor=None,
    )

    assert descriptor["width"] == 80
    assert descriptor["height"] == 40
    stored_doc = next(iter(storage.objects))
    with Image.open(BytesIO(storage.objects[stored_doc])) as image:
        assert image.size == (80, 40)


def test_store_image_transform_allows_transcoding_without_resize():
    service, _, storage = _service()

    descriptor = service.store_image(
        BytesIO(_make_image_bytes("PNG", size=(45, 15))),
        filename="cover.png",
        target={"module": "catalog", "entity": "Product", "field": "cover"},
        transform={"format": "jpg"},
        actor=None,
    )

    assert descriptor["mime-type"] == "image/jpeg"
    assert descriptor["width"] == 45
    assert descriptor["height"] == 15
    stored_doc = next(iter(storage.objects))
    with Image.open(BytesIO(storage.objects[stored_doc])) as image:
        assert image.format == "JPEG"
        assert image.size == (45, 15)


def test_store_image_transform_uses_first_frame_for_animated_gif():
    service, _, storage = _service()

    descriptor = service.store_image(
        BytesIO(_make_animated_gif_bytes()),
        filename="anim.gif",
        target={"module": "catalog", "entity": "Product", "field": "cover"},
        transform={"format": "png"},
        actor=None,
    )

    assert descriptor["mime-type"] == "image/png"
    stored_doc = next(iter(storage.objects))
    with Image.open(BytesIO(storage.objects[stored_doc])) as image:
        pixel = image.convert("RGB").getpixel((0, 0))
        assert pixel[0] > 200
        assert pixel[1] < 50
        assert pixel[2] < 50


def test_store_image_transform_to_jpg_flattens_alpha_background():
    service, _, storage = _service()

    descriptor = service.store_image(
        BytesIO(_make_rgba_png_bytes()),
        filename="cover.png",
        target={"module": "catalog", "entity": "Product", "field": "cover"},
        transform={"format": "jpg"},
        actor=None,
    )

    assert descriptor["mime-type"] == "image/jpeg"
    stored_doc = next(iter(storage.objects))
    with Image.open(BytesIO(storage.objects[stored_doc])) as image:
        assert image.format == "JPEG"
        assert image.mode == "RGB"


def test_store_file_obeys_field_acl():
    service, _, _ = _service()

    try:
        service.store_file(
            BytesIO(b"pdf"),
            filename="manual.pdf",
            content_type="application/pdf",
            target={"module": "catalog", "entity": "Product", "field": "manual"},
            actor=None,
        )
    except FieldWriteForbiddenError as exc:
        assert exc.code == "field_write_forbidden"
    else:
        raise AssertionError("Expected FieldWriteForbiddenError")


def test_store_file_uses_filename_mimetype_fallback_when_content_type_missing():
    service, _, _ = _service()

    descriptor = service.store_file(
        BytesIO(b"%PDF"),
        filename="manual.pdf",
        content_type=None,
        target={"module": "catalog", "entity": "Product", "field": "manual"},
        actor={"role": "admin"},
    )

    assert descriptor["mime-type"] == "application/pdf"


def test_store_file_uses_octet_stream_when_no_filename_and_no_content_type():
    service, _, _ = _service()

    descriptor = service.store_file(
        BytesIO(b"raw"),
        filename=None,
        content_type=None,
        target={"module": "catalog", "entity": "Product", "field": "manual"},
        actor={"role": "admin"},
    )

    assert descriptor["mime-type"] == "application/octet-stream"


def test_store_video_returns_descriptor_with_size_and_url():
    service, _, _ = _service()

    descriptor = service.store_video(
        BytesIO(b"video-data"),
        filename="clip.mp4",
        content_type="video/mp4",
        target={"module": "catalog", "entity": "Product", "field": "clip"},
        actor=None,
    )

    assert descriptor["mime-type"] == "video/mp4"
    assert descriptor["size"] == len(b"video-data")
    assert descriptor["url"].startswith("/assets/catalog/Product/clip/")


def test_store_image_rejects_semantic_type_mismatch():
    service, _, _ = _service()

    try:
        service.store_image(
            BytesIO(_make_image_bytes("PNG")),
            filename="cover.png",
            target={"module": "catalog", "entity": "Product", "field": "clip"},
            actor=None,
        )
    except ValidationError as exc:
        assert exc.code == "asset_target_semantic_type_mismatch"
    else:
        raise AssertionError("Expected ValidationError")


def test_store_image_builds_url_with_asset_public_base_url():
    service, _, _ = _service(config={"ASSET_PUBLIC_BASE_URL": "https://cdn.example.com"})

    descriptor = service.store_image(
        BytesIO(_make_image_bytes("PNG")),
        filename="cover.png",
        target={"module": "catalog", "entity": "Product", "field": "cover"},
        actor=None,
    )

    assert descriptor["url"].startswith("https://cdn.example.com/assets/catalog/Product/cover/")


def test_store_file_builds_url_with_asset_public_base_url_path_prefix():
    service, _, _ = _service(config={"ASSET_PUBLIC_BASE_URL": "/media/public"})

    descriptor = service.store_file(
        BytesIO(b"pdf"),
        filename="manual.pdf",
        content_type="application/pdf",
        target={"module": "catalog", "entity": "Product", "field": "manual"},
        actor={"role": "admin"},
    )

    assert descriptor["url"].startswith("/media/public/assets/catalog/Product/manual/")


def test_open_asset_returns_streamed_content():
    service, repo, storage = _service()
    repo.create(
        {
            "id": "asset-1",
            "kind": "file",
            "module": "catalog",
            "entity": "Product",
            "field": "manual",
            "storage_backend": "local_fs",
            "storage_key": "catalog/Product/manual/asset-1/manual.pdf",
            "mime_type": "application/pdf",
            "size": 4,
            "source_content_type": "application/pdf",
            "source_filename": "manual.pdf",
            "cdate": "2026-01-01T00:00:00Z",
        }
    )
    storage.put_bytes("catalog/Product/manual/asset-1/manual.pdf", b"test", content_type="application/pdf")

    storage.objects["assets/catalog/Product/manual/asset-1/manual.pdf"] = storage.objects.pop("catalog/Product/manual/asset-1/manual.pdf")
    repo.docs["asset-1"]["storage_key"] = "assets/catalog/Product/manual/asset-1/manual.pdf"

    opened = service.open_asset("assets/catalog/Product/manual/asset-1/manual.pdf")

    assert opened.mime_type == "application/pdf"
    assert opened.size == 4
    assert opened.stream.read() == b"test"


def test_open_descriptor_returns_streamed_content_for_sandala_descriptor():
    service, _, _ = _service()
    image_bytes = _make_image_bytes("PNG", size=(64, 32))
    descriptor = service.store_image(
        BytesIO(image_bytes),
        filename="cover.png",
        target={"module": "catalog", "entity": "Product", "field": "cover"},
        actor=None,
    )

    opened = service.open_descriptor(descriptor)

    try:
        assert opened.storage_key == descriptor["url"].lstrip("/")
        assert opened.mime_type == "image/png"
        assert opened.size == len(image_bytes)
        assert opened.stream.read() == image_bytes
    finally:
        opened.stream.close()


def test_open_descriptor_supports_public_base_url_path_prefix():
    service, _, _ = _service(config={"ASSET_PUBLIC_BASE_URL": "https://cdn.example.com/media"})
    image_bytes = _make_image_bytes("PNG", size=(16, 8))
    descriptor = service.store_image(
        BytesIO(image_bytes),
        filename="cover.png",
        target={"module": "catalog", "entity": "Product", "field": "cover"},
        actor=None,
    )

    opened = service.open_descriptor(descriptor)

    try:
        assert opened.storage_key.startswith("assets/catalog/Product/cover/")
        assert opened.stream.read() == image_bytes
    finally:
        opened.stream.close()


def test_open_descriptor_rejects_external_descriptor_url():
    service, _, _ = _service()

    try:
        service.open_descriptor({"url": "https://example.com/cover.png"})
    except AssetStorageKeyInvalidError as exc:
        assert exc.code == "asset_storage_key_invalid"
    else:
        raise AssertionError("Expected AssetStorageKeyInvalidError")


def test_open_asset_returns_not_found_when_blob_is_missing_in_storage():
    repo = FakeAssetRepo()
    repo.create(
        {
            "id": "asset-1",
            "kind": "file",
            "module": "catalog",
            "entity": "Product",
            "field": "manual",
            "storage_backend": "local_fs",
            "storage_key": "assets/catalog/Product/manual/asset-1/manual.pdf",
            "mime_type": "application/pdf",
            "size": 4,
            "source_content_type": "application/pdf",
            "source_filename": "manual.pdf",
            "cdate": "2026-01-01T00:00:00Z",
        }
    )
    service = AssetService(FakeEntityRepo(), repo, MissingBlobStorage(), {"ASSET_PUBLIC_BASE_URL": None})

    try:
        service.open_asset("assets/catalog/Product/manual/asset-1/manual.pdf")
    except NotFoundError as exc:
        assert exc.code == "not_found"
    else:
        raise AssertionError("Expected NotFoundError")


def test_open_asset_returns_asset_storage_key_invalid_for_backend_key_validation_error():
    repo = FakeAssetRepo()
    repo.create(
        {
            "id": "asset-1",
            "kind": "file",
            "module": "catalog",
            "entity": "Product",
            "field": "manual",
            "storage_backend": "local_fs",
            "storage_key": "assets/catalog/Product/manual/asset-1/manual.pdf",
            "mime_type": "application/pdf",
            "size": 4,
            "source_content_type": "application/pdf",
            "source_filename": "manual.pdf",
            "cdate": "2026-01-01T00:00:00Z",
        }
    )
    service = AssetService(FakeEntityRepo(), repo, InvalidKeyBlobStorage(), {"ASSET_PUBLIC_BASE_URL": None})

    try:
        service.open_asset("assets/catalog/Product/manual/asset-1/manual.pdf")
    except AssetStorageKeyInvalidError as exc:
        assert exc.code == "asset_storage_key_invalid"
    else:
        raise AssertionError("Expected AssetStorageKeyInvalidError")


def test_store_image_supports_schema_path_inside_array_items():
    service, _, _ = _service()

    descriptor = service.store_image(
        BytesIO(_make_image_bytes("PNG", size=(30, 10))),
        filename="gallery.png",
        target={"module": "catalog", "entity": "Product", "field": "gallery.image"},
        actor=None,
    )

    assert descriptor["width"] == 30
    assert descriptor["height"] == 10


def test_store_image_supports_array_of_images_directly():
    service, _, _ = _service()

    descriptor = service.store_image(
        BytesIO(_make_image_bytes("PNG", size=(11, 9))),
        filename="gallery.png",
        target={"module": "catalog", "entity": "Product", "field": "gallery_direct"},
        actor=None,
    )

    assert descriptor["width"] == 11
    assert descriptor["height"] == 9


def test_store_image_supports_named_array_levels_with_nullable_object_items():
    entity_repo = FakeEntityRepo()
    schema = entity_repo.schemas[("catalog", "Product")]
    schema["properties"]["sections"] = {
        "type": "array",
        "x-meta": {"semantic-type": "Array", "visibility-mode": "all", "write-mode": "all"},
        "items": {"anyOf": [{"type": "null"}, {
            "type": "object", "additionalProperties": False,
            "x-meta": {"semantic-type": "Object", "visibility-mode": "all", "write-mode": "all"},
            "properties": {"gallery": schema["properties"]["gallery"]},
        }]},
    }
    service = AssetService(entity_repo, FakeAssetRepo(), FakeBlobStorage(), {"ASSET_PUBLIC_BASE_URL": None})

    descriptor = service.store_image(
        BytesIO(_make_image_bytes("PNG", size=(17, 9))),
        filename="nested.png",
        target={"module": "catalog", "entity": "Product", "field": "sections.gallery.image"},
        actor=None,
    )

    assert descriptor["width"] == 17
    assert descriptor["height"] == 9


def test_store_image_rejects_array_index_syntax_in_target_field():
    service, _, _ = _service()

    try:
        service.store_image(
            BytesIO(_make_image_bytes("PNG")),
            filename="cover.png",
            target={"module": "catalog", "entity": "Product", "field": "gallery[0].image"},
            actor=None,
        )
    except ParameterInvalidError as exc:
        assert exc.code == "asset_target_invalid"
    else:
        raise AssertionError("Expected ParameterInvalidError")


def test_resolve_array_nested_field_rejects_invalid_path_after_scalar_or_leaf():
    service, _, _ = _service()

    try:
        service.store_image(
            BytesIO(_make_image_bytes("PNG")),
            filename="cover.png",
            target={"module": "catalog", "entity": "Product", "field": "gallery.image.foo"},
            actor=None,
        )
    except ValidationError as exc:
        assert exc.code == "validation_error"
    else:
        raise AssertionError("Expected ValidationError")


def test_resolve_field_rejects_empty_path_segments():
    service, _, _ = _service()

    try:
        service.store_image(
            BytesIO(_make_image_bytes("PNG")),
            filename="cover.png",
            target={"module": "catalog", "entity": "Product", "field": "nested..hero"},
            actor=None,
        )
    except ParameterInvalidError as exc:
        assert exc.code == "asset_target_invalid"
    else:
        raise AssertionError("Expected ParameterInvalidError")


def test_store_image_transform_rejects_boolean_dimension_values():
    service, _, _ = _service()

    try:
        service.store_image(
            BytesIO(_make_image_bytes("PNG")),
            filename="cover.png",
            target={"module": "catalog", "entity": "Product", "field": "cover"},
            transform={"format": "webp", "width": True},
            actor=None,
        )
    except AssetTransformInvalidError as exc:
        assert exc.code == "asset_transform_invalid"
    else:
        raise AssertionError("Expected AssetTransformInvalidError")


def _service(*, config=None):
    repo = FakeAssetRepo()
    storage = FakeBlobStorage()
    service = AssetService(
        FakeEntityRepo(),
        repo,
        storage,
        {"ASSET_PUBLIC_BASE_URL": None, **(config or {})},
    )
    return service, repo, storage


def _make_image_bytes(image_format: str, *, size=(32, 16)) -> bytes:
    image = Image.new("RGB", size, (255, 0, 0))
    buffer = BytesIO()
    image.save(buffer, format=image_format)
    return buffer.getvalue()


def _make_animated_gif_bytes() -> bytes:
    frame_one = Image.new("RGB", (20, 20), (255, 0, 0))
    frame_two = Image.new("RGB", (20, 20), (0, 0, 255))
    buffer = BytesIO()
    frame_one.save(buffer, format="GIF", save_all=True, append_images=[frame_two], loop=0, duration=100)
    return buffer.getvalue()


def _make_rgba_png_bytes() -> bytes:
    image = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    for x in range(16):
        for y in range(16):
            image.putpixel((x, y), (255, 0, 0, 128))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
