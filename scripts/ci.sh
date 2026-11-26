#!/usr/bin/env bash
# Local CI: the same checks GitHub Actions used to run, before anything is pushed.
#
#   scripts/ci.sh            # pytest + hassfest + HACS
#   SKIP_HACS=1 scripts/ci.sh
#
# Runs automatically from .githooks/pre-push (enable once with
# `git config core.hooksPath .githooks`). Bypass in an emergency with
# `git push --no-verify`.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

step() { printf '\n\033[1;34m▶ %s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

step "Tests (pytest)"
python3 -m pytest -q --cov=custom_components/aqualia --cov-report=term-missing:skip-covered \
  || fail "pytest falló"

command -v docker >/dev/null || fail "Docker no está disponible (hace falta para hassfest y HACS)"

step "Hassfest"
docker run --rm -v "$PWD:/github/workspace" ghcr.io/home-assistant/hassfest \
  || fail "hassfest falló"

if [[ "${SKIP_HACS:-}" == "1" ]]; then
  step "HACS (omitido: SKIP_HACS=1)"
else
  step "HACS"
  # The HACS validator inspects the repository on GitHub (description, topics,
  # releases) plus the local checkout, so it needs a token and the repo name.
  token="${GITHUB_TOKEN:-$(gh auth token 2>/dev/null || true)}"
  [[ -n "$token" ]] || fail "Sin token de GitHub: exporta GITHUB_TOKEN o haz 'gh auth login' (o usa SKIP_HACS=1)"
  repo="$(git remote get-url origin | sed -E 's#(git@github.com:|https://github.com/)##; s#\.git$##')"
  log="$(mktemp)"
  trap 'rm -f "$log"' EXIT
  docker run --rm \
    -e INPUT_CATEGORY=integration \
    -e INPUT_GITHUB_TOKEN="$token" \
    -e GITHUB_REPOSITORY="$repo" \
    -e GITHUB_WORKSPACE=/github/workspace \
    -v "$PWD:/github/workspace" \
    ghcr.io/hacs/action:main >"$log" 2>&1 \
    || { cat "$log" >&2; fail "validación HACS falló"; }
  grep -E '::(INFO|ERROR|WARNING)::' "$log" || true
fi

printf '\n\033[1;32m✓ CI local OK\033[0m\n'
