from abc import ABC, abstractmethod

from packages.shared.config import settings


class StorageBackend(ABC):
    @abstractmethod
    def put_bytes(
        self, object_key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> str:
        """Stores bytes and returns the object key."""
        pass

    @abstractmethod
    def get_bytes(self, object_key: str) -> bytes:
        """Retrieves bytes by object key."""
        pass

    @abstractmethod
    def get_presigned_url(self, object_key: str, expires_in: int = 3600) -> str:
        """Generates a presigned URL for downloading the object."""
        pass


class S3StorageBackend(StorageBackend):
    def __init__(self):
        import boto3
        from botocore.config import Config

        self.s3_client = boto3.client(
            "s3",
            endpoint_url=settings.STORAGE_S3_ENDPOINT,
            aws_access_key_id=settings.STORAGE_S3_ACCESS_KEY,
            aws_secret_access_key=settings.STORAGE_S3_SECRET_KEY,
            region_name=settings.STORAGE_S3_REGION,
            config=Config(signature_version="s3v4"),
        )
        self.bucket = settings.STORAGE_S3_BUCKET
        self._ensure_bucket()

    def _ensure_bucket(self):
        try:
            self.s3_client.head_bucket(Bucket=self.bucket)
        except Exception:
            # Create if it doesn't exist
            try:
                self.s3_client.create_bucket(Bucket=self.bucket)
            except Exception as e:
                print(f"Failed to create bucket: {e}")

    def put_bytes(
        self, object_key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> str:
        self.s3_client.put_object(
            Bucket=self.bucket, Key=object_key, Body=data, ContentType=content_type
        )
        return object_key

    def get_bytes(self, object_key: str) -> bytes:
        response = self.s3_client.get_object(Bucket=self.bucket, Key=object_key)
        return response["Body"].read()

    def get_presigned_url(self, object_key: str, expires_in: int = 3600) -> str:
        return self.s3_client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": object_key}, ExpiresIn=expires_in
        )


def get_storage_backend() -> StorageBackend:
    if settings.STORAGE_BACKEND_TYPE.lower() == "s3":
        return S3StorageBackend()
    raise ValueError(f"Unsupported storage backend: {settings.STORAGE_BACKEND_TYPE}")
