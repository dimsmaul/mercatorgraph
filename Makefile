# Build + publish the three service images.
#   make build push IMAGE_PREFIX=ghcr.io/<you> TAG=0.1.0
# Multi-arch (amd64+arm64) requires a buildx builder:
#   make buildx-push IMAGE_PREFIX=ghcr.io/<you> TAG=0.1.0

IMAGE_PREFIX ?= ck
TAG ?= dev
PLATFORMS ?= linux/amd64,linux/arm64

WORKER := $(IMAGE_PREFIX)/worker:$(TAG)
MCP    := $(IMAGE_PREFIX)/mcp:$(TAG)
DOCS   := $(IMAGE_PREFIX)/docs:$(TAG)

.PHONY: build push buildx-push test docs-build

build:
	docker build -t $(WORKER) -f worker/Dockerfile .
	docker build -t $(MCP)    -f mcp/Dockerfile .
	docker build -t $(DOCS)   docs

push:
	docker push $(WORKER)
	docker push $(MCP)
	docker push $(DOCS)

# Single command, multi-arch, pushes directly (needs `docker buildx create --use`).
buildx-push:
	docker buildx build --platform $(PLATFORMS) -t $(WORKER) -f worker/Dockerfile --push .
	docker buildx build --platform $(PLATFORMS) -t $(MCP)    -f mcp/Dockerfile --push .
	docker buildx build --platform $(PLATFORMS) -t $(DOCS)   --push docs

test:
	uv run --python 3.12 pytest -q

docs-build:
	cd docs && bun run build
