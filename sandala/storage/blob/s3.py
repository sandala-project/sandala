from __future__ import annotations


class S3BlobStorage:
    backend_name = "s3"

    def __init__(self, config: dict):
        try:
            import boto3
            from botocore.config import Config as BotoConfig
        except ImportError as exc:
            raise RuntimeError("boto3 is required for S3 asset storage backend") from exc

        self._bucket = config["ASSET_S3_BUCKET"]
        session = boto3.session.Session()
        client_config = BotoConfig(
            s3={
                "addressing_style": config.get("ASSET_S3_ADDRESSING_STYLE", "path"),
            }
        )
        self._client = session.client(
            "s3",
            endpoint_url=config.get("ASSET_S3_ENDPOINT") or None,
            region_name=config.get("ASSET_S3_REGION") or None,
            aws_access_key_id=config.get("ASSET_S3_ACCESS_KEY") or None,
            aws_secret_access_key=config.get("ASSET_S3_SECRET_KEY") or None,
            config=client_config,
        )

    def put_bytes(self, key: str, data: bytes, *, content_type: str | None = None) -> dict:
        kwargs = {"Bucket": self._bucket, "Key": key, "Body": data}
        if isinstance(content_type, str) and content_type:
            kwargs["ContentType"] = content_type
        self._client.put_object(**kwargs)
        return {"key": key, "content_type": content_type, "content_length": len(data)}

    def open(self, key: str) -> dict:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        return {
            "stream": response["Body"],
            "content_length": response.get("ContentLength"),
        }

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)
