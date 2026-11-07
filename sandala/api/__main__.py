from __future__ import annotations

from sandala.api.app import create_app


def main() -> None:
    app = create_app()
    cfg = app.config["sandala_config"]
    host = cfg["HOST"]
    port = cfg["PORT"]
    app.run(host=host, port=port)


if __name__ == "__main__":
    main()
