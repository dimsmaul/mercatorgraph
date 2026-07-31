#!/usr/bin/env bash
# Compute the next version + release channel from the latest commit message and existing
# git tags. Emits `channel=` and `version=` lines on stdout (consumable by $GITHUB_OUTPUT).
#
# Channels:
#   "release: major|minor|patch" in the commit subject -> bump that part, e.g. v1.2.3
#   "beta: ..."                   in the commit subject -> prerelease, e.g. v1.2.4-beta.1
#   anything else                 -> channel=none (CI skips build/publish)
#
# Beta only touches the trailing prerelease number (SemVer: MAJOR.MINOR.PATCH-beta.N).
# The first beta after a release targets the next PATCH; subsequent betas just increment N.
#
# Tags are read from `git tag -l` unless CK_TAGS is set (newline-separated) — for testing.
set -euo pipefail

msg="${COMMIT_MSG:-}"
subject="$(printf '%s\n' "$msg" | head -n1)"

if [[ -n "${CK_TAGS:-}" ]]; then
  tags="$CK_TAGS"
else
  tags="$(git tag -l 'v*' || true)"
fi

# strip leading "v" and match strictly
releases="$(printf '%s\n' "$tags" | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' || true)"
betas="$(printf '%s\n' "$tags" | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+-beta\.[0-9]+$' || true)"

latest_release="$(printf '%s\n' "$releases" | sed 's/^v//' | sort -V | tail -n1)"
[[ -z "$latest_release" ]] && latest_release="0.0.0"

emit() { echo "channel=$1"; echo "version=$2"; }

shopt -s nocasematch  # accept Release:/BETA: etc.

# --- release channel ------------------------------------------------------
if [[ "$subject" =~ ^release:[[:space:]]*(major|minor|patch) ]]; then
  part="${BASH_REMATCH[1],,}"  # lowercase the bump part
  IFS='.' read -r X Y Z <<<"$latest_release"
  case "$part" in
    major) X=$((X + 1)); Y=0; Z=0 ;;
    minor) Y=$((Y + 1)); Z=0 ;;
    patch) Z=$((Z + 1)) ;;
  esac
  emit "release" "v${X}.${Y}.${Z}"
  exit 0
fi

# --- beta channel ---------------------------------------------------------
if [[ "$subject" =~ ^beta: ]]; then
  latest_beta="$(printf '%s\n' "$betas" | sed 's/^v//' | sort -V | tail -n1)"

  base=""
  n=0
  if [[ -n "$latest_beta" ]]; then
    base="${latest_beta%-beta.*}"          # X.Y.Z
    n="${latest_beta##*-beta.}"            # N
    # is this beta line still ahead of the latest release? (base > latest_release)
    higher="$(printf '%s\n%s\n' "$base" "$latest_release" | sort -V | tail -n1)"
    if [[ "$higher" != "$base" || "$base" == "$latest_release" ]]; then
      base=""  # beta already released (or equal) -> start a fresh line
    fi
  fi

  if [[ -z "$base" ]]; then
    IFS='.' read -r X Y Z <<<"$latest_release"
    Z=$((Z + 1))                           # first beta targets next patch
    base="${X}.${Y}.${Z}"
    n=0
  fi

  emit "beta" "v${base}-beta.$((n + 1))"
  exit 0
fi

emit "none" ""
