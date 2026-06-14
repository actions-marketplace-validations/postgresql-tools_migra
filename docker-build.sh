#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="ghcr.io/postgresql-tools/migra"
TAG="${1:-latest}"

docker build -t "${IMAGE_NAME}:${TAG}" .
echo "Built: ${IMAGE_NAME}:${TAG}"
