"""Durable public storage for published outputs (finalized → published, §1.19-exception).

Hendo's settled v1 call: a plain, publicly-readable S3 bucket — no signed URLs, no unguessable
keys, no access-control layer (those were explicitly ruled out; the bucket policy is the only
gate, and it's public-read by design, see ``infra/aws-poc/publish_bucket.tf``). Callers are
responsible for the immutable-key discipline (a fresh key per publish, never overwriting one in
place) — this module is just the upload primitive.

``boto3`` is imported lazily, guarded like ``app/secrets/aws_provider.py``'s SSM client and
``app/render/pdf.py``'s Playwright import, so a deployment that never publishes needs neither the
SDK installed nor real AWS credentials to boot. The synchronous boto3 call is offloaded to a
worker thread (``anyio.to_thread``) so it never blocks the event loop.
"""

from __future__ import annotations

from typing import Any, Protocol


class PublishStorageError(RuntimeError):
    """The published-assets bucket isn't configured, or an upload failed."""


class PublishStorage(Protocol):
    async def put(self, key: str, body: bytes, *, content_type: str, acl: str = "public-read") -> str:
        """Upload ``body`` at ``key`` and return its public URL. Tests inject a fake; production
        wires :class:`S3PublishStorage`."""
        ...

    async def make_private(self, key: str) -> None:
        """Flip the object at ``key`` to private ACL (unpublish). Missing object is normal (skip)."""
        ...


class S3PublishStorage:
    """Real :class:`PublishStorage` over a plain, public-read S3 bucket."""

    def __init__(self, bucket: str, *, region: str = "us-east-1", client: Any | None = None) -> None:
        """``client``, when passed, is used as-is (the test seam — a fake/mocked S3 client) and
        boto3 is never imported. Production leaves it unset; the real client is built lazily on
        first upload."""
        if not bucket:
            raise PublishStorageError(
                "published-assets bucket is not configured (PUBLISHED_ASSETS_BUCKET)"
            )
        self.bucket = bucket
        self.region = region
        self._client = client

    def _client_or_create(self) -> Any:
        if self._client is None:
            try:
                import boto3
            except ImportError as exc:
                raise PublishStorageError(
                    "boto3 is not installed — required to publish to S3"
                ) from exc
            self._client = boto3.client("s3", region_name=self.region)
        return self._client

    async def put(self, key: str, body: bytes, *, content_type: str, acl: str = "public-read") -> str:
        import anyio

        client = self._client_or_create()

        def _put() -> None:
            client.put_object(
                Bucket=self.bucket, Key=key, Body=body, ContentType=content_type, ACL=acl
            )

        try:
            await anyio.to_thread.run_sync(_put)
        except Exception as exc:  # boto3 raises botocore.exceptions.ClientError et al.
            raise PublishStorageError(f"upload to s3://{self.bucket}/{key} failed: {exc}") from exc
        return f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{key}"

    async def make_private(self, key: str) -> None:
        import anyio

        client = self._client_or_create()

        def _make_private() -> None:
            try:
                client.put_object_acl(Bucket=self.bucket, Key=key, ACL="private")
            except Exception as e:  # ClientError for NoSuchKey etc. is normal
                if "NoSuchKey" not in str(e) and "404" not in str(e):
                    raise

        try:
            await anyio.to_thread.run_sync(_make_private)
        except Exception as exc:
            if "NoSuchKey" not in str(exc) and "404" not in str(exc):
                raise PublishStorageError(f"make private s3://{self.bucket}/{key} failed: {exc}") from exc
