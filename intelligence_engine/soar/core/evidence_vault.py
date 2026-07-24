import hashlib
import os
import structlog
from datetime import datetime, timezone
from typing import Dict, Any, Optional

logger = structlog.get_logger(__name__)

STORAGE_BACKEND = os.getenv("EVIDENCE_STORAGE_BACKEND", "s3")
S3_BUCKET = os.getenv("EVIDENCE_S3_BUCKET", "shieldai-evidence")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")  # None = AWS; set for MinIO


class EvidenceVault:
    """
    Cryptographically hashes artifacts (PCAPs, logs) and stores them in real
    object storage (S3 / MinIO / GCS) with immutability + server-side encryption.

    Env vars:
      EVIDENCE_STORAGE_BACKEND   s3 | gcs | local (default: s3)
      EVIDENCE_S3_BUCKET         bucket name
      S3_ENDPOINT_URL            set for MinIO (leave empty for AWS)
      AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY or IAM role
    """

    def __init__(self, storage_backend: Optional[str] = None) -> None:
        self.storage_backend = storage_backend or STORAGE_BACKEND
        self._s3_client = None

    def _get_s3_client(self):
        if self._s3_client is None:
            import boto3

            kwargs: Dict[str, Any] = {}
            if S3_ENDPOINT_URL:
                kwargs["endpoint_url"] = S3_ENDPOINT_URL
            self._s3_client = boto3.client("s3", **kwargs)
        return self._s3_client

    async def ingest_artifact(
        self,
        tenant_id: int,
        execution_id: int,
        artifact_data: bytes,
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        sha256_hash = hashlib.sha256(artifact_data).hexdigest()
        object_key = f"tenant-{tenant_id}/evidence/{execution_id}/{sha256_hash}.bin"

        if self.storage_backend == "s3":
            storage_uri = await self._upload_s3(object_key, artifact_data, sha256_hash)
        elif self.storage_backend == "local":
            storage_uri = self._store_local(object_key, artifact_data)
        else:
            raise ValueError(f"Unsupported storage backend: {self.storage_backend}")

        record = {
            "tenant_id": tenant_id,
            "execution_id": execution_id,
            "sha256_hash": sha256_hash,
            "storage_uri": storage_uri,
            "metadata": metadata,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.info(
            "evidence_ingested",
            sha256=sha256_hash,
            execution_id=execution_id,
            uri=storage_uri,
        )
        return record

    async def _upload_s3(self, object_key: str, data: bytes, sha256_hash: str) -> str:
        import asyncio

        s3 = self._get_s3_client()
        loop = asyncio.get_event_loop()

        def _put():
            s3.put_object(
                Bucket=S3_BUCKET,
                Key=object_key,
                Body=data,
                ChecksumSHA256=sha256_hash,
                ServerSideEncryption="AES256",
                ObjectLockMode="COMPLIANCE",
                ObjectLockRetainUntilDate=datetime(
                    datetime.now(timezone.utc).year + 7,
                    datetime.now(timezone.utc).month,
                    datetime.now(timezone.utc).day,
                    tzinfo=timezone.utc,
                ),
            )

        await loop.run_in_executor(None, _put)
        endpoint = S3_ENDPOINT_URL or "https://s3.amazonaws.com"
        return f"{endpoint}/{S3_BUCKET}/{object_key}"

    def _store_local(self, object_key: str, data: bytes) -> str:
        import pathlib

        base = pathlib.Path("/tmp/evidence_vault")
        path = base / object_key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return f"file://{path}"
