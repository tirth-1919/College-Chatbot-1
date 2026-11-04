"""S3-compatible private object storage for tenant media."""
from io import BytesIO
import boto3
from botocore.config import Config
from .config import settings


def client():
    if not all((settings.s3_endpoint, settings.s3_bucket, settings.s3_access_key, settings.s3_secret_key)):
        raise RuntimeError("S3-compatible object storage is not configured")
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def put_image(object_key: str, image_bytes: bytes, content_type: str = "image/webp"):
    client().put_object(Bucket=settings.s3_bucket, Key=object_key, Body=BytesIO(image_bytes), ContentType=content_type)


def signed_url(object_key: str, expires: int = 900) -> str:
    return client().generate_presigned_url(
        "get_object", Params={"Bucket": settings.s3_bucket, "Key": object_key}, ExpiresIn=expires
    )


def remove(object_key: str):
    if object_key:
        client().delete_object(Bucket=settings.s3_bucket, Key=object_key)
