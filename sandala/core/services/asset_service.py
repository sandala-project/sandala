from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from sandala.core.assets.field_resolver import enforce_field_write_access, resolve_asset_field
from sandala.core.assets.image_processor import ImageProcessor
from sandala.core.assets.key_builder import build_storage_key
from sandala.core.assets.url_builder import build_asset_url
from sandala.core.errors import (
    AssetStorageKeyInvalidError,
    AssetTargetInvalidError,
    AssetTargetSemanticTypeMismatchError,
    NotFoundError,
    ParameterInvalidError,
    ValidationError,
)
from sandala.core.time_utils import utc_now_iso


@dataclass(slots=True)
class AssetOpenResult:
    storage_key: str
    mime_type: str
    size: int
    stream: Any


class AssetService:
    def __init__(self, entity_repo, asset_repo, blob_storage, config: dict[str, Any] | None = None):
        self._entity_repo = entity_repo
        self._asset_repo = asset_repo
        self._blob_storage = blob_storage
        self._config = config or {}
        self._image_processor = ImageProcessor()

    def store_image(
        self,
        file_obj,
        *,
        filename: str | None = None,
        content_type: str | None = None,
        target: dict[str, Any],
        transform: dict[str, Any] | None = None,
        actor: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        target_info = self._resolve_target(target, expected_semantic={"Image", "RichText"}, actor=actor)
        data = _read_input_bytes(file_obj)
        source_filename = _normalize_optional_string(filename)
        if transform is None:
            image = self._image_processor.inspect_original(data)
        else:
            transform_payload = _normalize_transform(transform)
            image = self._image_processor.transform(data, transform_payload)

        asset_id = str(uuid4())
        storage_key = build_storage_key(
            module=target_info["module"],
            entity=target_info["entity"],
            field=target_info["field"],
            asset_id=asset_id,
            source_filename=source_filename,
            extension=image.extension,
        )
        self._blob_storage.put_bytes(storage_key, image.data, content_type=image.mime_type)
        self._asset_repo.create(
            {
                "id": asset_id,
                "kind": "image",
                "module": target_info["module"],
                "entity": target_info["entity"],
                "field": target_info["field"],
                "storage_backend": self._blob_storage.backend_name,
                "storage_key": storage_key,
                "mime_type": image.mime_type,
                "size": image.size,
                "width": image.width,
                "height": image.height,
                "source_content_type": _normalize_optional_string(content_type),
                "source_filename": source_filename,
                "cdate": utc_now_iso(),
            }
        )
        return {
            "url": build_asset_url(storage_key, public_base_url=self._config.get("ASSET_PUBLIC_BASE_URL")),
            "mime-type": image.mime_type,
            "width": image.width,
            "height": image.height,
            "size": image.size,
        }

    def store_file(
        self,
        file_obj,
        *,
        filename: str | None = None,
        content_type: str | None = None,
        target: dict[str, Any],
        actor: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._store_binary(
            kind="file",
            expected_semantic="File",
            file_obj=file_obj,
            filename=filename,
            content_type=content_type,
            target=target,
            actor=actor,
        )

    def store_video(
        self,
        file_obj,
        *,
        filename: str | None = None,
        content_type: str | None = None,
        target: dict[str, Any],
        actor: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._store_binary(
            kind="video",
            expected_semantic="Video",
            file_obj=file_obj,
            filename=filename,
            content_type=content_type,
            target=target,
            actor=actor,
        )

    def store_image_from_path(self, path, **kwargs) -> dict[str, Any]:
        with Path(path).open("rb") as stream:
            return self.store_image(stream, filename=kwargs.pop("filename", Path(path).name), **kwargs)

    def store_file_from_path(self, path, **kwargs) -> dict[str, Any]:
        with Path(path).open("rb") as stream:
            return self.store_file(stream, filename=kwargs.pop("filename", Path(path).name), **kwargs)

    def store_video_from_path(self, path, **kwargs) -> dict[str, Any]:
        with Path(path).open("rb") as stream:
            return self.store_video(stream, filename=kwargs.pop("filename", Path(path).name), **kwargs)

    def open_asset(self, storage_key: str) -> AssetOpenResult:
        if not isinstance(storage_key, str) or not storage_key:
            raise AssetStorageKeyInvalidError("Storage key must be a non-empty string")
        doc = self._asset_repo.find_by_storage_key(storage_key)
        if doc is None:
            raise NotFoundError(f"Asset with storage key '{storage_key}' not found")
        try:
            opened = self._blob_storage.open(storage_key)
        except FileNotFoundError as exc:
            raise NotFoundError(f"Asset with storage key '{storage_key}' not found") from exc
        except ValueError as exc:
            raise AssetStorageKeyInvalidError(f"Storage key '{storage_key}' is invalid") from exc
        except Exception as exc:
            if _is_missing_blob_error(exc):
                raise NotFoundError(f"Asset with storage key '{storage_key}' not found") from exc
            raise
        mime_type = doc.get("mime_type")
        size = doc.get("size")
        if not isinstance(mime_type, str) or not isinstance(size, int):
            raise ValidationError(f"Asset with storage key '{storage_key}' metadata is invalid")
        return AssetOpenResult(
            storage_key=storage_key,
            mime_type=mime_type,
            size=size,
            stream=opened["stream"],
        )

    def open_descriptor(self, descriptor: dict[str, Any]) -> AssetOpenResult:
        """Open an asset addressed by a descriptor URL containing a Sandala asset key."""
        return self.open_asset(_storage_key_from_descriptor(descriptor))

    def _store_binary(
        self,
        *,
        kind: str,
        expected_semantic: str | set[str],
        file_obj,
        filename: str | None,
        content_type: str | None,
        target: dict[str, Any],
        actor: dict[str, Any] | None,
    ) -> dict[str, Any]:
        target_info = self._resolve_target(target, expected_semantic=expected_semantic, actor=actor)
        data = _read_input_bytes(file_obj)
        source_filename = _normalize_optional_string(filename)
        mime_type = _choose_content_type(content_type, filename=source_filename)
        extension = _choose_extension_from_filename(source_filename)
        asset_id = str(uuid4())
        storage_key = build_storage_key(
            module=target_info["module"],
            entity=target_info["entity"],
            field=target_info["field"],
            asset_id=asset_id,
            source_filename=source_filename,
            extension=extension,
        )
        self._blob_storage.put_bytes(storage_key, data, content_type=mime_type)
        self._asset_repo.create(
            {
                "id": asset_id,
                "kind": kind,
                "module": target_info["module"],
                "entity": target_info["entity"],
                "field": target_info["field"],
                "storage_backend": self._blob_storage.backend_name,
                "storage_key": storage_key,
                "mime_type": mime_type,
                "size": len(data),
                "source_content_type": _normalize_optional_string(content_type),
                "source_filename": source_filename,
                "cdate": utc_now_iso(),
            }
        )
        return {
            "url": build_asset_url(storage_key, public_base_url=self._config.get("ASSET_PUBLIC_BASE_URL")),
            "mime-type": mime_type,
            "size": len(data),
        }

    def _resolve_target(self, target: dict[str, Any], *, expected_semantic: str, actor: dict[str, Any] | None) -> dict[str, str]:
        if not isinstance(target, dict):
            raise AssetTargetInvalidError("Field 'target' must be an object")
        module = target.get("module")
        entity = target.get("entity")
        field = target.get("field")
        if not isinstance(module, str) or not module:
            raise AssetTargetInvalidError("Field 'target.module' must be a non-empty string")
        if not isinstance(entity, str) or not entity:
            raise AssetTargetInvalidError("Field 'target.entity' must be a non-empty string")
        if not isinstance(field, str) or not field:
            raise AssetTargetInvalidError("Field 'target.field' must be a non-empty string")

        field_schema = resolve_asset_field(self._entity_repo, module, entity, field)
        semantic_type = field_schema.get("x-meta", {}).get("semantic-type")
        expected_semantics = {expected_semantic} if isinstance(expected_semantic, str) else expected_semantic
        if semantic_type not in expected_semantics:
            expected_text = " or ".join(f"'{item}'" for item in sorted(expected_semantics))
            raise AssetTargetSemanticTypeMismatchError(
                f"Field '{field}' in entity '{entity}' of module '{module}' must have semantic type {expected_text}"
            )
        enforce_field_write_access(field_schema, field, actor=actor)
        return {"module": module, "entity": entity, "field": field}


def _storage_key_from_descriptor(descriptor: dict[str, Any]) -> str:
    if not isinstance(descriptor, dict):
        raise AssetStorageKeyInvalidError("Asset descriptor must be an object")
    url = descriptor.get("url")
    if not isinstance(url, str) or not url:
        raise AssetStorageKeyInvalidError("Asset descriptor must contain a non-empty URL")

    path_segments = urlparse(url).path.split("/")
    try:
        assets_index = path_segments.index("assets")
    except ValueError as exc:
        raise AssetStorageKeyInvalidError("Asset descriptor URL does not identify a Sandala asset") from exc

    storage_key = "/".join(path_segments[assets_index:])
    if storage_key == "assets":
        raise AssetStorageKeyInvalidError("Asset descriptor URL does not identify a Sandala asset")
    return storage_key


def _read_input_bytes(file_obj) -> bytes:
    if isinstance(file_obj, bytes):
        return file_obj
    if hasattr(file_obj, "read") and callable(file_obj.read):
        data = file_obj.read()
        if not isinstance(data, bytes):
            raise ParameterInvalidError("Asset file content must be bytes")
        return data
    raise ParameterInvalidError("Asset file must be bytes or file-like object")


def _normalize_optional_string(value) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_transform(transform: dict[str, Any]) -> dict[str, Any]:
    from sandala.core.errors import AssetTransformInvalidError

    if not isinstance(transform, dict):
        raise AssetTransformInvalidError("Field 'transform' must be an object")
    return dict(transform)


def _is_missing_blob_error(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return False
    error = response.get("Error")
    if not isinstance(error, dict):
        return False
    code = error.get("Code")
    return code in {"NoSuchKey", "404", "NotFound"}


def _choose_content_type(content_type: str | None, *, filename: str | None) -> str:
    normalized = _normalize_optional_string(content_type)
    if normalized is not None:
        return normalized
    if filename:
        guessed, _ = mimetypes.guess_type(filename)
        if isinstance(guessed, str) and guessed:
            return guessed
    return "application/octet-stream"


def _choose_extension_from_filename(filename: str | None) -> str:
    if not filename or "." not in filename:
        return "bin"
    return filename.rsplit(".", 1)[-1].strip().lower() or "bin"
