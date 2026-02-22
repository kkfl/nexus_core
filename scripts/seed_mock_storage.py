import os
import boto3

# Use minio defaults
ENDPOINT_URL = os.environ.get("MINIO_ENDPOINT", "http://localhost:9000")
AK = os.environ.get("MINIO_ROOT_USER", "admin")
SK = os.environ.get("MINIO_ROOT_PASSWORD", "minio_pass")

def main():
    s3 = boto3.client(
        's3',
        endpoint_url=ENDPOINT_URL,
        aws_access_key_id=AK,
        aws_secret_access_key=SK,
        region_name="us-east-1"
    )

    for bucket in ["target-a", "target-b", "mock-bucket"]:
        try:
            s3.create_bucket(Bucket=bucket)
            print(f"Created bucket: {bucket}")
        except Exception as e:
            if 'BucketAlreadyOwnedByYou' in str(e) or 'BucketAlreadyExists' in str(e):
                print(f"Bucket {bucket} already exists.")
            else:
                print(f"Error creating bucket {bucket}: {e}")

    # Seed mock content in target-a
    objects = {
        "kb/test-doc-1.txt": b"Hello world from KB.",
        "artifacts/nexus/run-1.json": b'{"status": "ok"}',
        "recording/zoom/audit-55.mp4": b"fake mp4 data",
    }
    
    for key, data in objects.items():
        s3.put_object(Bucket="target-a", Key=key, Body=data)
        print(f"Seeded s3://target-a/{key}")

if __name__ == "__main__":
    main()
