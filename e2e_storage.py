import asyncio
import sys

import httpx

URL = "http://localhost:8005/v1"
HEADERS = {"X-Service-ID": "automation-agent", "X-Agent-Key": "automation-storage-key-change-me"}

# Note: make sure to run python e2e_setup_storage.py first to seed credentials in Vault


async def run_e2e():
    print("=== Storage Agent E2E Workflow Test ===")

    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. Register a Target dynamically using aliases previously set up in e2e_setup_storage
        print("\n1. Upserting Storage Target 'minio_local'...")
        target_payload = {
            "storage_target_id": "minio_local",
            "endpoint_url": "http://minio:9000",
            "region": "us-east-1",
            "default_bucket": "nexus-test-bucket",
            "credential_aliases": {
                "access_key_id": "storage.minio_local.access_key_id",
                "secret_access_key": "storage.minio_local.secret_access_key",
            },
            "flags": {"s3_force_path_style": True},
        }
        res = await client.post(f"{URL}/targets", json=target_payload, headers=HEADERS)
        if res.status_code != 200:
            print("Failed to create target:", res.text)
            sys.exit(1)
        print(" -> Success:", res.json())

        # 2. Ensure Bucket
        print("\n2. Ensuring bucket 'nexus-test-bucket' exists...")
        bucket_req = {"storage_target_id": "minio_local", "bucket_name": "nexus-test-bucket"}
        res = await client.post(f"{URL}/buckets/ensure", json=bucket_req, headers=HEADERS)
        if res.status_code != 200:
            print("Failed to ensure bucket:", res.text)
            sys.exit(1)
        print(" -> Success:", res.json())

        # 3. Generating a Presigned URL for PUT
        print("\n3. Generating presigned PUT URL...")
        presign_req = {
            "storage_target_id": "minio_local",
            "bucket_name": "nexus-test-bucket",
            "object_key": "test_folder/hello.txt",
            "method": "PUT",
            "expires_in_seconds": 600,
        }
        res = await client.post(f"{URL}/objects/presign", json=presign_req, headers=HEADERS)
        if res.status_code != 200:
            print("Failed to presign url:", res.text)
            sys.exit(1)

        presign_data = res.json()
        put_url = presign_data["url"].replace("http://minio:9000", "http://localhost:9000")
        print(" -> Success: Generated URL:", put_url)

        # 4. Direct Upload via Presign
        print("\n4. Uploading file via S3 presigned URL directly...")
        upload_resp = await client.put(put_url, content=b"Hello from Nexus Final Pass Test!")
        if upload_resp.status_code != 200:
            print("Direct upload failed!", upload_resp.status_code, upload_resp.text)
            sys.exit(1)
        print(" -> Success: File uploaded directly to S3 via presigned URL.")

        # 5. List objects in bucket
        print("\n5. Listing objects in bucket...")
        list_req = {
            "storage_target_id": "minio_local",
            "bucket_name": "nexus-test-bucket",
            "prefix": "test_folder/",
        }
        res = await client.post(f"{URL}/objects/list", json=list_req, headers=HEADERS)
        if res.status_code != 200:
            print("Failed to list objects:", res.text)
            sys.exit(1)

        objs = res.json().get("keys", [])
        print(" -> Success: Found", len(objs), "objects.")
        for o in objs:
            print("    *", o["key"], f"({o['size_bytes']} bytes)")

        # 6. Trigger Retention Dry-Run Job (Async -> Telegram notification)
        print("\n6. Queuing async Retention dry-run job...")
        retention_req = {
            "storage_target_id": "minio_local",
            "bucket_name": "nexus-test-bucket",
            "prefix": "test_folder/",
            "older_than_days": 0,  # Should scan everything
            "dry_run": True,
        }
        # Actually hit our job endpoint at /v1 (Note: the api code handles Telegram alert internally)
        res = await client.post(f"{URL}/retention/execute", json=retention_req, headers=HEADERS)
        if res.status_code != 200:
            print("Failed to start job:", res.text)
            sys.exit(1)

        print(" -> Job queued:", res.json())
        print(" -> Giving background task 3 seconds to complete + dispatch telegram alert...")
        await asyncio.sleep(3)

        print("\n=== E2E Test Complete ===")
        print("SUCCESS: Full workflow succeeded!")


if __name__ == "__main__":
    asyncio.run(run_e2e())
