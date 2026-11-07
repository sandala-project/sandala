from __future__ import annotations

from flask import Blueprint, Response, current_app, jsonify, request

from sandala.api.auth import attach_optional_auth_context
from sandala.api.errors import register_error_handlers
from sandala.api.payloads import get_optional_form_json_object, require_form_json_object, wrap_resource
from sandala.api.route_prefixes import API_V1_PREFIX
from sandala.core.errors import AssetFileMissingError


asset_api_bp = Blueprint("asset_api", __name__)
asset_delivery_bp = Blueprint("asset_delivery", __name__)


def register_asset_routes(app, asset_service, *, url_prefix: str = API_V1_PREFIX):
    register_error_handlers(app)
    app.register_blueprint(asset_api_bp, url_prefix=url_prefix)
    app.register_blueprint(asset_delivery_bp)
    app.config["asset_service"] = asset_service


@asset_api_bp.post("/uploads/assets/images/")
def upload_image():
    service = _service()
    actor = attach_optional_auth_context()
    upload = _require_uploaded_file()
    descriptor = service.store_image(
        upload.stream,
        filename=upload.filename,
        content_type=upload.mimetype,
        target=require_form_json_object("target"),
        transform=get_optional_form_json_object("transform"),
        actor=actor,
    )
    return jsonify(wrap_resource("image", descriptor)), 201


@asset_api_bp.post("/uploads/assets/files/")
def upload_file():
    service = _service()
    actor = attach_optional_auth_context()
    upload = _require_uploaded_file()
    descriptor = service.store_file(
        upload.stream,
        filename=upload.filename,
        content_type=upload.mimetype,
        target=require_form_json_object("target"),
        actor=actor,
    )
    return jsonify(wrap_resource("file", descriptor)), 201


@asset_api_bp.post("/uploads/assets/videos/")
def upload_video():
    service = _service()
    actor = attach_optional_auth_context()
    upload = _require_uploaded_file()
    descriptor = service.store_video(
        upload.stream,
        filename=upload.filename,
        content_type=upload.mimetype,
        target=require_form_json_object("target"),
        actor=actor,
    )
    return jsonify(wrap_resource("video", descriptor)), 201


@asset_delivery_bp.get("/assets/<path:key_tail>")
def get_asset(key_tail: str):
    storage_key = f"assets/{key_tail}"
    result = _service().open_asset(storage_key)
    response = Response(result.stream, mimetype=result.mime_type, direct_passthrough=True)
    response.headers["Content-Length"] = str(result.size)
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    response.call_on_close(result.stream.close)
    return response


def _service():
    return current_app.config["asset_service"]


def _require_uploaded_file():
    upload = request.files.get("file")
    if upload is None:
        raise AssetFileMissingError("Multipart form must contain uploaded file in field 'file'")
    return upload
