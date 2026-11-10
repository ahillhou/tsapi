#!/bin/bash
# Build this folder's code and replace the running "voicerequest" container.
#
# Only one container can listen on port 8000, so running this from the
# tsapi folder or from the legacy tdx_pcr folder swaps which code is live.
# To roll back, run the legacy folder's deploy.sh.
set -e

# Always build the folder this script lives in, wherever it's run from
cd "$(dirname "$0")"

if [ ! -f app/.env ]; then
    echo "app/.env is missing in $(pwd); copy it from the other folder first."
    exit 1
fi

echo "Building image from $(pwd)..."
docker build -t voicerequest .

echo "Stopping old container..."
docker stop voicerequest 2>/dev/null || true

echo "Removing old container..."
docker rm voicerequest 2>/dev/null || true

echo "Starting new container..."
docker run -d \
    --restart unless-stopped \
    --name voicerequest \
    --env-file app/.env \
    -p 8000:8000 \
    voicerequest

docker ps

echo ""
echo "===== FOLLOWING LOGS (Ctrl+C stops following; the container keeps running) ====="
echo ""

docker logs -f voicerequest
