from dataclasses import dataclass
from urllib.parse import quote

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings


@dataclass(frozen=True)
class UploadedObjectMetadata:
    size_bytes: int
    content_type: str | None


class StorageService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create_presigned_upload_url(self, *, storage_key: str, content_type: str) -> str | None:
        if self._settings.storage_backend == "none":
            return None

        client = boto3.client(
            "s3",
            endpoint_url=self._settings.s3_public_endpoint_url or self._settings.s3_endpoint_url,
            region_name=self._settings.s3_region_name,
            aws_access_key_id=self._settings.s3_access_key_id,
            aws_secret_access_key=self._settings.s3_secret_access_key,
            config=Config(signature_version="s3v4"),
        )
        return client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self._settings.s3_bucket,
                "Key": storage_key,
                "ContentType": content_type,
            },
            ExpiresIn=self._settings.s3_presigned_upload_expire_seconds,
        )

    def create_presigned_download_url(
        self,
        *,
        storage_key: str,
        filename: str,
        content_type: str,
    ) -> str | None:
        if self._settings.storage_backend == "none":
            return None

        client = boto3.client(
            "s3",
            endpoint_url=self._settings.s3_public_endpoint_url or self._settings.s3_endpoint_url,
            region_name=self._settings.s3_region_name,
            aws_access_key_id=self._settings.s3_access_key_id,
            aws_secret_access_key=self._settings.s3_secret_access_key,
            config=Config(signature_version="s3v4"),
        )
        safe_filename = filename.replace('"', "")
        return client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self._settings.s3_bucket,
                "Key": storage_key,
                "ResponseContentType": content_type,
                "ResponseContentDisposition": (
                    f"attachment; filename*=UTF-8''{quote(safe_filename)}"
                ),
            },
            ExpiresIn=self._settings.s3_presigned_download_expire_seconds,
        )

    def head_object(self, *, storage_key: str) -> UploadedObjectMetadata | None:
        if self._settings.storage_backend == "none":
            return None

        client = boto3.client(
            "s3",
            endpoint_url=self._settings.s3_endpoint_url,
            region_name=self._settings.s3_region_name,
            aws_access_key_id=self._settings.s3_access_key_id,
            aws_secret_access_key=self._settings.s3_secret_access_key,
            config=Config(signature_version="s3v4"),
        )
        try:
            response = client.head_object(Bucket=self._settings.s3_bucket, Key=storage_key)
        except ClientError as exc:
            status_code = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status_code == 404:
                return None
            raise
        except BotoCoreError:
            raise

        return UploadedObjectMetadata(
            size_bytes=int(response["ContentLength"]),
            content_type=response.get("ContentType"),
        )
