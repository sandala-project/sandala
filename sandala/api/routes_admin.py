from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, send_from_directory


admin_ui_bp = Blueprint("admin_ui", __name__, url_prefix="/admin")


def register_admin_ui_routes(app, dist_dir: str | Path | None = None):
    configured_dist = Path(dist_dir) if dist_dir is not None else _default_admin_ui_dist()
    if not configured_dist.is_dir() or not (configured_dist / "index.html").is_file():
        if dist_dir is not None:
            raise RuntimeError(f"Admin UI dist directory is missing index.html: {configured_dist}")
        return

    app.config["admin_ui_dist"] = configured_dist
    app.register_blueprint(admin_ui_bp)


@admin_ui_bp.get("/")
def admin_index():
    return _send_admin_file("index.html")


@admin_ui_bp.get("/<path:requested_path>")
def admin_file(requested_path: str):
    if requested_path == "_app" or requested_path.startswith("_app/"):
        return _send_admin_file("index.html")
    return _send_admin_file(requested_path)


def _send_admin_file(relative_path: str):
    admin_ui_dist = current_app.config.get("admin_ui_dist")
    if admin_ui_dist is None:
        raise RuntimeError("Admin UI routes are not configured")
    return send_from_directory(admin_ui_dist, relative_path)


def _default_admin_ui_dist() -> Path:
    return Path(__file__).resolve().parents[1] / "admin_ui_dist"
