"""S3-compatible storage (RustFS in Compose; any S3 later). See ADR-004.

Two clients:
- internal: operations from backend/worker to the storage service (S3_ENDPOINT);
- public: only signs URLs for the browser, against the origin users open
  (S3_PUBLIC_ENDPOINT). Signing does not touch the network.

Large objects are never loaded whole: reads are by range or by chunks.
"""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import aioboto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_CONFIG = Config(signature_version="s3v4", s3={"addressing_style": "path"})


@dataclass(frozen=True)
class UploadedPart:
    number: int
    size: int
    etag: str


class Storage:
    def __init__(
        self,
        endpoint: str | None = None,
        public_endpoint: str | None = None,
        bucket: str | None = None,
    ) -> None:
        settings = get_settings()
        self.endpoint = endpoint or settings.s3_endpoint
        self.public_endpoint = public_endpoint or settings.s3_public_endpoint
        self.bucket = bucket or settings.s3_bucket
        self._session = aioboto3.Session(
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
        )

    def _client(self, public: bool = False) -> Any:
        return self._session.client(
            "s3", endpoint_url=self.public_endpoint if public else self.endpoint, config=_CONFIG
        )

    async def ensure_bucket(self) -> None:
        async with self._client() as s3:
            try:
                await s3.head_bucket(Bucket=self.bucket)
            except ClientError:
                await s3.create_bucket(Bucket=self.bucket)

    async def create_multipart(self, key: str, content_type: str) -> str:
        async with self._client() as s3:
            response = await s3.create_multipart_upload(
                Bucket=self.bucket, Key=key, ContentType=content_type
            )
        return str(response["UploadId"])

    async def presign_part(self, key: str, upload_id: str, number: int, expires: int) -> str:
        async with self._client(public=True) as s3:
            url: str = await s3.generate_presigned_url(
                "upload_part",
                Params={
                    "Bucket": self.bucket,
                    "Key": key,
                    "UploadId": upload_id,
                    "PartNumber": number,
                },
                ExpiresIn=expires,
            )
        return url

    async def list_parts(self, key: str, upload_id: str) -> list[UploadedPart]:
        parts: list[UploadedPart] = []
        marker = 0
        async with self._client() as s3:
            while True:
                response = await s3.list_parts(
                    Bucket=self.bucket, Key=key, UploadId=upload_id, PartNumberMarker=marker
                )
                parts.extend(
                    UploadedPart(int(p["PartNumber"]), int(p["Size"]), str(p["ETag"]))
                    for p in response.get("Parts", [])
                )
                if not response.get("IsTruncated"):
                    return parts
                marker = int(response["NextPartNumberMarker"])

    async def complete_multipart(self, key: str, upload_id: str, parts: list[UploadedPart]) -> None:
        async with self._client() as s3:
            await s3.complete_multipart_upload(
                Bucket=self.bucket,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={
                    "Parts": [{"PartNumber": p.number, "ETag": p.etag} for p in parts]
                },
            )

    async def abort_multipart(self, key: str, upload_id: str) -> None:
        async with self._client() as s3:
            try:
                await s3.abort_multipart_upload(Bucket=self.bucket, Key=key, UploadId=upload_id)
            except ClientError as exc:
                logger.info("abort_multipart_ignored", extra={"extra_fields": {"error": str(exc)}})

    async def read_range(self, key: str, start: int, end: int) -> bytes:
        async with self._client() as s3:
            response = await s3.get_object(
                Bucket=self.bucket, Key=key, Range=f"bytes={start}-{end}"
            )
            body = response["Body"]
            try:
                data: bytes = await body.read()
            finally:
                body.close()
        return data
        return data

    async def iter_chunks(self, key: str, chunk_size: int) -> AsyncIterator[bytes]:
        async with self._client() as s3:
            response = await s3.get_object(Bucket=self.bucket, Key=key)
            body = response["Body"]
            try:
                while chunk := await body.read(chunk_size):
                    yield chunk
            finally:
                body.close()

    async def put_fileobj(self, key: str, fileobj: Any, content_type: str) -> None:
        """Streams a file object to storage (multipart under the hood), never all in memory."""
        async with self._client() as s3:
            await s3.upload_fileobj(
                fileobj, self.bucket, key, ExtraArgs={"ContentType": content_type}
            )

    async def size(self, key: str) -> int:
        async with self._client() as s3:
            response = await s3.head_object(Bucket=self.bucket, Key=key)
        return int(response["ContentLength"])

    async def exists(self, key: str) -> bool:
        try:
            await self.size(key)
        except ClientError:
            return False
        return True

    async def copy(self, source: str, target: str) -> None:
        async with self._client() as s3:
            await s3.copy_object(
                Bucket=self.bucket, Key=target, CopySource={"Bucket": self.bucket, "Key": source}
            )

    async def delete(self, key: str) -> None:
        async with self._client() as s3:
            await s3.delete_object(Bucket=self.bucket, Key=key)

    async def presign_get(self, key: str, expires: int, filename: str) -> str:
        safe_name = filename.replace('"', "").replace("\\", "")
        async with self._client(public=True) as s3:
            url: str = await s3.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.bucket,
                    "Key": key,
                    "ResponseContentType": "application/pdf",
                    "ResponseContentDisposition": f'inline; filename="{safe_name}"',
                },
                ExpiresIn=expires,
            )
        return url


def get_storage() -> Storage:
    return Storage()
