from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from sandala.api.app import create_app
from tests.integration.helpers import mongo_local_asset_services


@pytest.mark.integration
def test_asset_service_stores_and_reads_image_via_local_filesystem(tmp_path: Path):
    asset_root = tmp_path / "asset_root"
    with mongo_local_asset_services(asset_root, mongo_db="sandala_it_assets_local_service") as (
        entity_service,
        _node_service,
        node_repo,
        asset_service,
        _config,
    ):
        entity_service.create("catalog", "Product", _product_schema())
        actor = _bootstrap_admin_actor(node_repo)

        descriptor = asset_service.store_image(
            BytesIO(_make_image_bytes("PNG", size=(48, 24))),
            filename="cover.png",
            target={"module": "catalog", "entity": "Product", "field": "cover"},
            transform={"format": "webp", "width": 24},
            actor=actor,
        )

        assert descriptor["url"].startswith("/assets/catalog/Product/cover/")
        storage_key = descriptor["url"].lstrip("/")
        local_path = asset_root / storage_key
        assert local_path.exists()

        opened = asset_service.open_asset(storage_key)
        payload = opened.stream.read()
        with Image.open(BytesIO(payload)) as image:
            assert image.format == "WEBP"
            assert image.size == (24, 12)


@pytest.mark.integration
def test_asset_api_upload_and_delivery_work_with_local_filesystem(tmp_path: Path):
    asset_root = tmp_path / "asset_root"
    with mongo_local_asset_services(asset_root, mongo_db="sandala_it_assets_local_api") as (
        entity_service,
        _node_service,
        _node_repo,
        _asset_service,
        config,
    ):
        entity_service.create("catalog", "Product", _product_schema())
        app = create_app(config)
        client = app.test_client()

        resp = client.post(
            "/api/v1/uploads/assets/images/",
            data={
                "file": (BytesIO(_make_image_bytes("PNG", size=(36, 18))), "cover.png"),
                "target": '{"module":"catalog","entity":"Product","field":"cover"}',
                "transform": '{"format":"webp","width":18}',
            },
            content_type="multipart/form-data",
        )

        assert resp.status_code == 201
        body = resp.get_json()
        assert body["image"]["url"].startswith("/assets/catalog/Product/cover/")

        local_path = asset_root / body["image"]["url"].lstrip("/")
        assert local_path.exists()

        delivery_resp = client.get(body["image"]["url"])
        assert delivery_resp.status_code == 200
        assert delivery_resp.headers["Content-Type"].startswith("image/webp")
        with Image.open(BytesIO(delivery_resp.data)) as image:
            assert image.format == "WEBP"
            assert image.size == (18, 9)


@pytest.mark.integration
def test_asset_api_file_upload_and_delivery_work_with_local_filesystem(tmp_path: Path):
    asset_root = tmp_path / "asset_root"
    with mongo_local_asset_services(asset_root, mongo_db="sandala_it_assets_local_file_api") as (
        entity_service,
        _node_service,
        _node_repo,
        _asset_service,
        config,
    ):
        entity_service.create("catalog", "Product", _product_schema())
        app = create_app(config)
        client = app.test_client()

        resp = client.post(
            "/api/v1/uploads/assets/files/",
            data={
                "file": (BytesIO(b"%PDF-1.4"), "manual.pdf"),
                "target": '{"module":"catalog","entity":"Product","field":"manual"}',
            },
            content_type="multipart/form-data",
        )

        assert resp.status_code == 201
        body = resp.get_json()
        assert body["file"]["url"].startswith("/assets/catalog/Product/manual/")
        delivery_resp = client.get(body["file"]["url"])
        assert delivery_resp.status_code == 200
        assert delivery_resp.data == b"%PDF-1.4"
        assert delivery_resp.headers["Content-Type"].startswith("application/pdf")


@pytest.mark.integration
def test_asset_api_video_upload_and_delivery_work_with_local_filesystem(tmp_path: Path):
    asset_root = tmp_path / "asset_root"
    with mongo_local_asset_services(asset_root, mongo_db="sandala_it_assets_local_video_api") as (
        entity_service,
        _node_service,
        _node_repo,
        _asset_service,
        config,
    ):
        entity_service.create("catalog", "Product", _product_schema())
        app = create_app(config)
        client = app.test_client()

        resp = client.post(
            "/api/v1/uploads/assets/videos/",
            data={
                "file": (BytesIO(b"video-data"), "clip.mp4"),
                "target": '{"module":"catalog","entity":"Product","field":"clip"}',
            },
            content_type="multipart/form-data",
        )

        assert resp.status_code == 201
        body = resp.get_json()
        assert body["video"]["url"].startswith("/assets/catalog/Product/clip/")
        delivery_resp = client.get(body["video"]["url"])
        assert delivery_resp.status_code == 200
        assert delivery_resp.data == b"video-data"
        assert delivery_resp.headers["Content-Type"].startswith("video/mp4")


@pytest.mark.integration
def test_asset_api_respects_asset_public_base_url_with_local_backend(tmp_path: Path):
    asset_root = tmp_path / "asset_root"
    with mongo_local_asset_services(
        asset_root,
        mongo_db="sandala_it_assets_local_public_base",
        extra_config={"ASSET_PUBLIC_BASE_URL": "https://cdn.example.com/media"},
    ) as (
        entity_service,
        _node_service,
        _node_repo,
        _asset_service,
        config,
    ):
        entity_service.create("catalog", "Product", _product_schema())
        app = create_app(config)
        client = app.test_client()

        resp = client.post(
            "/api/v1/uploads/assets/files/",
            data={
                "file": (BytesIO(b"%PDF-1.4"), "manual.pdf"),
                "target": '{"module":"catalog","entity":"Product","field":"manual"}',
            },
            content_type="multipart/form-data",
        )

        assert resp.status_code == 201
        body = resp.get_json()
        assert body["file"]["url"].startswith("https://cdn.example.com/media/assets/catalog/Product/manual/")


def _bootstrap_admin_actor(node_repo) -> dict[str, object]:
    root_user = node_repo.find_one(
        "users",
        {"entity": "user", "deleted": False, "username": "admin"},
        {"_id": 0},
    )
    assert root_user is not None
    return {
        "user_id": root_user["id"],
        "role": "superuser",
        "primary_group": root_user["primary_group"],
        "groups": root_user["groups"],
    }


def _product_schema() -> dict:
    return {
        "title": "Product",
        "description": "Product",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "cover": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "url": {"type": "string"},
                    "mime-type": {"type": "string"},
                    "width": {"type": "integer"},
                    "height": {"type": "integer"},
                    "size": {"type": "integer"},
                },
                "required": ["url", "mime-type", "width", "height", "size"],
                "x-meta": {"semantic-type": "Image", "visibility-mode": "all", "write-mode": "all"},
            },
            "manual": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "url": {"type": "string"},
                    "mime-type": {"type": "string"},
                    "size": {"type": "integer"},
                },
                "required": ["url", "mime-type", "size"],
                "x-meta": {"semantic-type": "File", "visibility-mode": "all", "write-mode": "all"},
            },
            "clip": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "url": {"type": "string"},
                    "mime-type": {"type": "string"},
                    "size": {"type": "integer"},
                },
                "required": ["url", "mime-type", "size"],
                "x-meta": {"semantic-type": "Video", "visibility-mode": "all", "write-mode": "all"},
            }
        },
        "required": [],
        "x-meta": {
            "children": {"entities": []},
            "perm": {
                "default": {
                    "owner": {"r": True, "w": True, "p": True},
                    "group": {"r": True, "w": True, "p": True},
                    "others": {"r": True, "w": True, "p": True},
                }
            },
        },
    }


def _make_image_bytes(image_format: str, *, size=(32, 16)) -> bytes:
    image = Image.new("RGB", size, (255, 0, 0))
    buffer = BytesIO()
    image.save(buffer, format=image_format)
    return buffer.getvalue()
