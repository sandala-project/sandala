from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from sandala.core.errors import (
    AssetInvalidImageFileError,
    AssetTransformFormatUnsupportedError,
    AssetTransformInvalidError,
    AssetUnsupportedImageFormatError,
)


INPUT_FORMATS = {
    "JPEG": ("jpg", "image/jpeg"),
    "PNG": ("png", "image/png"),
    "GIF": ("gif", "image/gif"),
    "WEBP": ("webp", "image/webp"),
}

OUTPUT_FORMATS = {
    "jpg": ("JPEG", "image/jpeg"),
    "png": ("PNG", "image/png"),
    "webp": ("WEBP", "image/webp"),
}


@dataclass(slots=True)
class ImageDescriptorData:
    data: bytes
    extension: str
    mime_type: str
    width: int
    height: int
    size: int


class ImageProcessor:
    def inspect_original(self, data: bytes) -> ImageDescriptorData:
        Image, ImageOps = _load_pillow()
        try:
            with Image.open(BytesIO(data)) as image:
                fmt = image.format
                if fmt not in INPUT_FORMATS:
                    raise AssetUnsupportedImageFormatError()
                oriented = ImageOps.exif_transpose(image)
                extension, mime_type = INPUT_FORMATS[fmt]
                width, height = oriented.size
        except AssetUnsupportedImageFormatError:
            raise
        except Exception as exc:
            raise AssetInvalidImageFileError() from exc
        return ImageDescriptorData(
            data=data,
            extension=extension,
            mime_type=mime_type,
            width=width,
            height=height,
            size=len(data),
        )

    def transform(self, data: bytes, transform: dict[str, object]) -> ImageDescriptorData:
        Image, ImageOps = _load_pillow()
        output_format_key = transform.get("format")
        if output_format_key not in OUTPUT_FORMATS:
            raise AssetTransformFormatUnsupportedError("Field 'transform.format' must be one of: jpg, png, webp")

        width = _normalize_optional_positive_int(transform.get("width"), field="transform.width")
        height = _normalize_optional_positive_int(transform.get("height"), field="transform.height")
        fit = transform.get("fit", "inside")
        if fit not in {"inside", "cover"}:
            raise AssetTransformInvalidError("Field 'transform.fit' must be one of: inside, cover")

        try:
            with Image.open(BytesIO(data)) as image:
                if image.format not in INPUT_FORMATS:
                    raise AssetUnsupportedImageFormatError()
                if image.format == "GIF" and getattr(image, "is_animated", False):
                    image.seek(0)
                transformed = ImageOps.exif_transpose(image.copy())
        except AssetUnsupportedImageFormatError:
            raise
        except Exception as exc:
            raise AssetInvalidImageFileError() from exc

        if width is not None or height is not None:
            transformed = _resize_image(transformed, width=width, height=height, fit=fit, image_ops=ImageOps, image_module=Image)

        save_format, mime_type = OUTPUT_FORMATS[output_format_key]
        transformed = _prepare_for_save(transformed, save_format)
        buffer = BytesIO()
        save_kwargs = {"format": save_format}
        if save_format == "JPEG":
            save_kwargs["quality"] = 90
        transformed.save(buffer, **save_kwargs)
        output_data = buffer.getvalue()
        return ImageDescriptorData(
            data=output_data,
            extension=output_format_key,
            mime_type=mime_type,
            width=transformed.width,
            height=transformed.height,
            size=len(output_data),
        )


def _load_pillow():
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise RuntimeError("Pillow is required for asset image processing") from exc
    return Image, ImageOps


def _normalize_optional_positive_int(value, *, field: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value <= 0:
        raise AssetTransformInvalidError(f"Field '{field}' must be a positive integer")
    return value


def _resize_image(image, *, width: int | None, height: int | None, fit: str, image_ops, image_module):
    if width is not None and height is not None:
        if fit == "cover":
            return image_ops.fit(image, (width, height), method=image_module.Resampling.LANCZOS)
        return image_ops.contain(image, (width, height), method=image_module.Resampling.LANCZOS)

    original_width, original_height = image.size
    if width is not None:
        scale = width / original_width
        height = max(1, int(round(original_height * scale)))
    else:
        assert height is not None
        scale = height / original_height
        width = max(1, int(round(original_width * scale)))
    return image.resize((width, height), resample=image_module.Resampling.LANCZOS)


def _prepare_for_save(image, save_format: str):
    Image, _ImageOps = _load_pillow()
    if save_format != "JPEG":
        return image
    if image.mode in {"RGB", "L"}:
        return image
    if "A" in image.mode:
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.getchannel("A"))
        return background
    return image.convert("RGB")
