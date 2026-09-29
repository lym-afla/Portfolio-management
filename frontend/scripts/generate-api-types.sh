#!/bin/sh
set -e
cd "$(dirname "$0")/.."
node scripts/generate-api-types.mjs --write
