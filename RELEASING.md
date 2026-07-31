# Releasing

CI builds and publishes three Docker images to **GHCR** and tags the repo, driven entirely by
the **latest commit subject** on `main`. Workflow: `.github/workflows/release.yml`.

## Images

Published to `ghcr.io/<owner>/<repo>/<service>`:

- `ghcr.io/dimsmaul/mercatorgraph/worker`
- `ghcr.io/dimsmaul/mercatorgraph/mcp`
- `ghcr.io/dimsmaul/mercatorgraph/docs`

## Two mechanisms

Both read the subject (first line) of the pushed commit:

| Commit subject | Result | Image tags |
|----------------|--------|------------|
| `release: major` | bump MAJOR, reset minor+patch | `X.0.0` and `latest` |
| `release: minor` | bump MINOR, reset patch | `X.Y.0` and `latest` |
| `release: patch` | bump PATCH | `X.Y.Z` and `latest` |
| `beta: <note>` | prerelease, increments only the trailing number | `X.Y.Z-beta.N` (no `latest`) |
| anything else | nothing built or tagged | — |

Keyword is case-insensitive (`Release:`, `BETA:` work).

### Version rules (SemVer)

- Stable: `MAJOR.MINOR.PATCH`, computed from the highest existing `vX.Y.Z` tag (starts at
  `0.0.0`).
- Beta: `MAJOR.MINOR.PATCH-beta.N` (standard SemVer prerelease; `0.2.3-beta.1` < `0.2.3`).
  - The **first** `beta:` after a release targets the next PATCH → e.g. release `0.2.2`
    then `beta:` → `0.2.3-beta.1`.
  - Each subsequent `beta:` only increments N → `0.2.3-beta.2`, `0.2.3-beta.3`, …
  - Once `0.2.3` ships as a release, the next `beta:` starts a fresh line `0.2.4-beta.1`.

The logic lives in `scripts/next_version.sh` (testable locally):

```bash
COMMIT_MSG="beta: wip" CK_TAGS=$'v0.2.2\nv0.2.3-beta.1' bash scripts/next_version.sh
# channel=beta
# version=v0.2.3-beta.2
```

## Usage

```bash
# cut a stable patch release
git commit -m "release: patch"
git push origin main

# publish a beta prerelease
git commit -m "beta: trying the new diff tool"
git push origin main

# normal work — no release
git commit -m "fix: something"
git push origin main
```

On a matching push, CI: computes the version → builds+pushes the 3 images → creates the git
tag `vX.Y.Z[-beta.N]` → creates a GitHub Release (betas marked *pre-release*).

## Pull published images

```bash
docker pull ghcr.io/dimsmaul/mercatorgraph/worker:0.2.3
docker pull ghcr.io/dimsmaul/mercatorgraph/mcp:0.2.3
docker pull ghcr.io/dimsmaul/mercatorgraph/docs:0.2.3
```

Or deploy the whole stack against a published tag:

```bash
IMAGE_PREFIX=ghcr.io/dimsmaul/mercatorgraph TAG=0.2.3 \
  docker compose -f docker-compose.deploy.yml up -d
```

## Notes

- Auth uses the built-in `GITHUB_TOKEN` (no extra secret). GHCR packages are **private** by
  default — make them public in the repo's Packages settings if you want open distribution.
- Images build `linux/amd64` only. To also publish `linux/arm64` (Apple Silicon hosts), add it
  to `platforms:` in the workflow (slower builds).
- To use Docker Hub instead of GHCR: change `IMAGE_BASE`, swap the `docker/login-action`
  registry to `docker.io`, and add `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` secrets.
