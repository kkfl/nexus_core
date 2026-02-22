#!/usr/bin/env bash
set -eo pipefail

echo "========================================"
echo "     Nexus Production Key Rotator       "
echo "========================================"

if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Usage: ./rotate_keys.sh <api_token> <api_key_id_to_rotate>"
    echo "Provide an admin-level JWT and the ID of the API Key you wish to rotate."
    exit 1
fi

TOKEN="$1"
KEY_ID="$2"
URL=${NEXUS_API_URL:-"http://127.0.0.1:8000"}

echo "Rotating API Key ID: $KEY_ID..."

RESPONSE=$(curl -s -X POST "${URL}/auth/api-keys/${KEY_ID}/rotate" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json")

NEW_KEY=$(echo $RESPONSE | grep -o '"key":"[^"]*' | grep -o '[^"]*$')

if [ -z "$NEW_KEY" ]; then
    echo "ERROR: Failed to rotate key. API Response:"
    echo "$RESPONSE"
    exit 1
fi

echo "SUCCESS: Key Rotated."
echo "New Plaintext Key: $NEW_KEY"
echo "Warning: This new key is ONLY shown once. Store it securely."
