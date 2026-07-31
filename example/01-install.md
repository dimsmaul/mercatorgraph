# 01 — Install Docker

Mercatorgraph ships as Docker images and runs with Docker Compose. You need **Docker Engine
20.10+** (which includes the `docker compose` v2 plugin).

## macOS

Install [Docker Desktop for Mac](https://docs.docker.com/desktop/install/mac-install/) (Apple
Silicon or Intel). After install, verify:

```bash
docker --version
docker compose version
```

## Windows

Install [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/)
(WSL 2 backend recommended). Verify the same two commands in PowerShell.

## Linux

Install Docker Engine + the Compose plugin (Ubuntu/Debian example):

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"   # run docker without sudo (re-login after)
docker compose version
```

For other distros see <https://docs.docker.com/engine/install/>.

## Verify Compose works

```bash
docker run --rm hello-world
```

If that prints a welcome message, you're ready — continue to
[02-quickstart.md](02-quickstart.md).

> Note: on Apple Silicon the published images are `linux/amd64` and run under emulation. It
> works but is slower; a native `linux/arm64` build can be enabled in the release workflow.
