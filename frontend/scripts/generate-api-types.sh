#!/bin/bash
set -e
echo "Generating OpenAPI schema from backend..."
cd "$(dirname "$0")/../../backend"
uv run python manage.py spectacular --format openapi-json > /tmp/openapi-schema.json
echo "Generating TypeScript types..."
cd ../frontend
npx openapi-typescript /tmp/openapi-schema.json -o src/types/api.d.ts
echo "Done. Types written to frontend/src/types/api.d.ts"
