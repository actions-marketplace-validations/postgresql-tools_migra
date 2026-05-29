#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="ghcr.io/migradiff/migra"
TAG="${1:-latest}"

docker build -t "${IMAGE_NAME}:${TAG}" .
echo "Built: ${IMAGE_NAME}:${TAG}"
