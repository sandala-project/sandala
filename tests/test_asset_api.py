from __future__ import annotations

from io import BytesIO

from flask import Flask

from sandala.api.routes_assets import register_asset_routes
from sandala.core.errors import AuthenticationError, NotFoundError, ParameterInvalidError
from sandala.core.services.asset_service import AssetOpenResult


class StubAssetService:
    def __init__(self):
        self.calls = []

    def store_image(self, file_obj, *, filename=None, content_type=None, target=None, transform=None, actor=None):
        self.calls.append(("image", filename, content_type, target, transform, actor, file_obj.read()))
        return {"url": "/assets/catalog/Product/cover/image-1/cover.webp", "mime-type": "image/webp", "width": 20, "height": 10, "size": 8}

    def store_file(self, file_obj, *, filename=None, content_type=None, target=None, actor=None):
        self.calls.append(("file", filename, content_type, target, None, actor, file_obj.read()))
        return {"url": "/assets/catalog/Product/manual/file-1/manual.pdf", "mime-type": "application/pdf", "size": 3}

    def store_video(self, file_obj, *, filename=None, content_type=None, target=None, actor=None):
        self.calls.append(("video", filename, content_type, target, None, actor, file_obj.read()))
        return {"url": "/assets/catalog/Product/clip/video-1/clip.mp4", "mime-type": "video/mp4", "size": 3}

    def open_asset(self, storage_key):
        if storage_key == "assets/missing":
            raise NotFoundError("missing")
        return AssetOpenResult(storage_key=storage_key, mime_type="image/png", size=4, stream=BytesIO(b"data"))


class StubAuthService:
    def authenticate_request(self, *, bearer_token=None, session_id=None):
        if bearer_token == "admin":
            return {"actor": {"user_id": "admin-1", "role": "admin"}, "renew_session": False, "session_id": None}
        if bearer_token is None and session_id is None:
            return None
        raise AuthenticationError("Invalid access token")


def test_asset_api_upload_and_delivery():
    app = Flask(__name__)
    service = StubAssetService()
    register_asset_routes(app, service, url_prefix="")
    app.config["auth_service"] = StubAuthService()
    client = app.test_client()

    resp = client.post(
        "/uploads/assets/images/",
        data={
            "file": (BytesIO(b"image-bytes"), "cover.png"),
            "target": '{"module":"catalog","entity":"Product","field":"cover"}',
            "transform": '{"format":"webp","width":20}',
        },
        content_type="multipart/form-data",
        headers={"Authorization": "Bearer admin"},
    )

    assert resp.status_code == 201
    body = resp.get_json()
    assert body["image"]["url"] == "/assets/catalog/Product/cover/image-1/cover.webp"
    assert service.calls[0][0] == "image"
    assert service.calls[0][1] == "cover.png"
    assert service.calls[0][3] == {"module": "catalog", "entity": "Product", "field": "cover"}
    assert service.calls[0][4] == {"format": "webp", "width": 20}
    assert service.calls[0][5]["role"] == "admin"

    resp = client.get("/assets/catalog/Product/cover/image-1/cover.webp")
    assert resp.status_code == 200
    assert resp.data == b"data"
    assert resp.headers["Content-Type"].startswith("image/png")
    assert resp.headers["Cache-Control"] == "public, max-age=31536000, immutable"


def test_asset_api_requires_json_target_and_file_field():
    app = Flask(__name__)
    register_asset_routes(app, StubAssetService(), url_prefix="")
    app.config["auth_service"] = StubAuthService()
    client = app.test_client()

    resp = client.post(
        "/uploads/assets/files/",
        data={
            "file": (BytesIO(b"%PDF"), "manual.pdf"),
            "target": "bad-json",
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "parameter_invalid"

    resp = client.post(
        "/uploads/assets/files/",
        data={"target": '{"module":"catalog","entity":"Product","field":"manual"}'},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "asset_file_missing"


def test_asset_api_upload_file_endpoint_returns_file_descriptor():
    app = Flask(__name__)
    service = StubAssetService()
    register_asset_routes(app, service, url_prefix="")
    app.config["auth_service"] = StubAuthService()
    client = app.test_client()

    resp = client.post(
        "/uploads/assets/files/",
        data={
            "file": (BytesIO(b"%PDF"), "manual.pdf"),
            "target": '{"module":"catalog","entity":"Product","field":"manual"}',
        },
        content_type="multipart/form-data",
    )

    assert resp.status_code == 201
    body = resp.get_json()
    assert body["file"]["url"] == "/assets/catalog/Product/manual/file-1/manual.pdf"
    assert body["file"]["mime-type"] == "application/pdf"


def test_asset_api_upload_video_endpoint_returns_video_descriptor():
    app = Flask(__name__)
    service = StubAssetService()
    register_asset_routes(app, service, url_prefix="")
    app.config["auth_service"] = StubAuthService()
    client = app.test_client()

    resp = client.post(
        "/uploads/assets/videos/",
        data={
            "file": (BytesIO(b"mp4"), "clip.mp4"),
            "target": '{"module":"catalog","entity":"Product","field":"clip"}',
        },
        content_type="multipart/form-data",
    )

    assert resp.status_code == 201
    body = resp.get_json()
    assert body["video"]["url"] == "/assets/catalog/Product/clip/video-1/clip.mp4"
    assert body["video"]["mime-type"] == "video/mp4"


def test_asset_api_invalid_transform_json_returns_parameter_invalid():
    app = Flask(__name__)
    register_asset_routes(app, StubAssetService(), url_prefix="")
    app.config["auth_service"] = StubAuthService()
    client = app.test_client()

    resp = client.post(
        "/uploads/assets/images/",
        data={
            "file": (BytesIO(b"image"), "cover.png"),
            "target": '{"module":"catalog","entity":"Product","field":"cover"}',
            "transform": "[]",
        },
        content_type="multipart/form-data",
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "parameter_invalid"


def test_asset_api_invalid_target_json_type_returns_parameter_invalid():
    app = Flask(__name__)
    register_asset_routes(app, StubAssetService(), url_prefix="")
    app.config["auth_service"] = StubAuthService()
    client = app.test_client()

    resp = client.post(
        "/uploads/assets/images/",
        data={
            "file": (BytesIO(b"image"), "cover.png"),
            "target": "[]",
        },
        content_type="multipart/form-data",
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "parameter_invalid"


def test_asset_api_propagates_not_found_from_delivery():
    app = Flask(__name__)
    register_asset_routes(app, StubAssetService(), url_prefix="")
    app.config["auth_service"] = StubAuthService()
    client = app.test_client()

    resp = client.get("/assets/missing")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "not_found"
