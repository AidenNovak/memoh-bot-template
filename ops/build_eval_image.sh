#!/usr/bin/env bash
set -euo pipefail
# Run on vultr-sg. Builds use the managed 6 GiB / 4 CPU builder, sequentially.
TASK_SOURCE=/srv/native-build/memoh-template-upstream-1bfb421
TASK_COMMIT=1bfb42154e09efacd34f68898ceaab78c10c85f3
if [[ ! -d "$TASK_SOURCE/.git" ]]; then
  git clone --depth 1 --recurse-submodules --shallow-submodules https://github.com/felinics/Memoh.git "$TASK_SOURCE"
fi
test "$(git -C "$TASK_SOURCE" rev-parse HEAD)" = "$TASK_COMMIT"
cat > /srv/native-build/memoh-template-eval-server.Dockerfile <<'DOCKER'
FROM golang:1.25-alpine AS build
RUN apk add --no-cache git
WORKDIR /build
ENV GOMAXPROCS=4 GOMEMLIMIT=4GiB
COPY go.mod go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod go mod download
COPY . .
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 go build -p 4 -trimpath -ldflags '-s -w -X github.com/felinics/memoh/internal/version.Version=template-eval -X github.com/felinics/memoh/internal/version.CommitHash=1bfb42154e09efacd34f68898ceaab78c10c85f3' -o /out/memoh-server ./cmd/agent && \
    CGO_ENABLED=0 go build -p 4 -trimpath -ldflags '-s -w -X github.com/felinics/memoh/internal/version.CommitHash=1bfb42154e09efacd34f68898ceaab78c10c85f3' -o /out/memoh-channel ./cmd/channel && \
    CGO_ENABLED=0 go build -p 4 -trimpath -ldflags '-s -w -X github.com/felinics/memoh/internal/version.CommitHash=1bfb42154e09efacd34f68898ceaab78c10c85f3' -o /out/bridge ./cmd/bridge
FROM memohai/server@sha256:bdc3f65783b91ba4f781966789554f6521a197aec1a556d75aa3559eb9853413
COPY --from=build /out/memoh-server /app/memoh-server
COPY --from=build /out/memoh-channel /app/memoh-channel
COPY --from=build /out/bridge /opt/memoh/runtime/bridge
COPY --from=build /build/spec /app/spec
COPY --from=build /build/conf/providers /app/conf/providers
COPY --chmod=755 --from=build /build/docker/server-entrypoint.sh /entrypoint.sh
DOCKER
uptime
/opt/meimaobing-alpha/scripts/build-limited.sh build "$TASK_SOURCE" /srv/native-build/memoh-template-eval-server.Dockerfile memoh-template-eval/upstream:1bfb421
/opt/meimaobing-alpha/scripts/build-limited.sh build "$TASK_SOURCE" "$TASK_SOURCE/docker/Dockerfile.web" memoh-template-eval/web:1bfb421
uptime
