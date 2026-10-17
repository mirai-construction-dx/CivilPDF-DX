#!/usr/bin/env bash
#
# CivilPDF-DX — verify docker compose definitions (CI guard).
#
# Guards the staging definition added in PR #164 so it cannot silently regress:
#
#   1. every tracked compose file is well-formed
#      (`docker compose -f <file> config --no-interpolate -q`);
#   2. docker-compose.staging.yml resolves to project `civilpdf-stg`, exposes
#      exactly ONE host port and it is the frontend bound to 127.0.0.1 (loopback
#      only); db and backend publish NO host ports;
#   3. docker-compose.prod.yml keeps db and backend off the host network.
#
# Assertions are made against the RESOLVED config (`docker compose ... config`).
# To resolve without reading (or clobbering) the repository's real `.env` /
# `.env.stg`, the compose files are rendered with `--project-directory` pointing
# at a throwaway directory that holds inert `.env` / `.env.stg` files. Only
# `config` is ever executed — nothing is built or started here.
#
# Exits non-zero when any check fails. Requires docker compose v2 + python3.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

COMPOSE_FILES=(docker-compose.prod.yml docker-compose.mvp.yml docker-compose.staging.yml)
STAGING_FILE="docker-compose.staging.yml"
PROD_FILE="docker-compose.prod.yml"

FAIL=0
pass() { printf '[PASS] %s\n' "$*"; }
fail() { printf '[FAIL] %s\n' "$*" >&2; FAIL=1; }

command -v docker >/dev/null 2>&1 || { echo "ERROR: docker not found" >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "ERROR: docker compose v2 not available" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 not found" >&2; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT INT TERM

# Inert throwaway env files: satisfy Compose interpolation of required variables
# and the services' env_file references without touching the repo's real files.
cat > "$WORK/.env" <<'EOF'
POSTGRES_DB=civilpdf
POSTGRES_USER=civilpdf
POSTGRES_PASSWORD=compose-guard-throwaway
EOF

cat > "$WORK/.env.stg" <<'EOF'
POSTGRES_DB=civilpdf_stg
POSTGRES_USER=civilpdf_stg
POSTGRES_PASSWORD=compose-guard-throwaway
SECRET_KEY=compose-guard-throwaway
TIMESTAMP_HMAC_KEY=compose-guard-throwaway
FRONTEND_PORT=18971
EOF

# The staging backend reads env secrets from ${STG_ENV_FILE:-.env.stg}. Point it at
# the throwaway file so the guard never reads the real staging/prod secrets.
export STG_ENV_FILE="$WORK/.env.stg"

# `--no-interpolate` (compose >= 2.17) validates structure without env expansion.
NO_INTERPOLATE=()
if docker compose config --help 2>/dev/null | grep -q -- '--no-interpolate'; then
  NO_INTERPOLATE=(--no-interpolate)
fi

echo "== 1. Well-formedness =="
for f in "${COMPOSE_FILES[@]}"; do
  if docker compose --project-directory "$WORK" -f "$ROOT/$f" config "${NO_INTERPOLATE[@]}" -q >/dev/null 2>&1; then
    pass "well-formed: $f"
  else
    fail "well-formed: $f"
  fi
done

# Render the resolved config. Prefers JSON (`--format json`); falls back to the
# resolved YAML when the flag is unavailable. The parser accepts either.
resolve_config() {
  local out
  out="$1"
  shift
  if docker compose --project-directory "$WORK" "$@" config --format json >"$out" 2>"$out.err"; then
    return 0
  fi
  if docker compose --project-directory "$WORK" "$@" config >"$out" 2>"$out.err"; then
    return 0
  fi
  return 1
}

STAGING_OUT="$WORK/staging.out"
PROD_OUT="$WORK/prod.out"

echo "== 2. Resolved-config invariants =="
RESOLVED_OK=1
if ! resolve_config "$STAGING_OUT" --env-file "$WORK/.env.stg" -f "$ROOT/$STAGING_FILE"; then
  fail "resolve $STAGING_FILE (config)"
  cat "$STAGING_OUT.err" >&2 || true
  RESOLVED_OK=0
fi
if ! resolve_config "$PROD_OUT" -f "$ROOT/$PROD_FILE"; then
  fail "resolve $PROD_FILE (config)"
  cat "$PROD_OUT.err" >&2 || true
  RESOLVED_OK=0
fi

if [[ "$RESOLVED_OK" -eq 1 ]]; then
  set +e
  python3 - "$STAGING_OUT" "$PROD_OUT" "$ROOT" <<'PY'
import json
import sys


def load(path):
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        import yaml  # resolved YAML fallback (--format json unavailable)
    except ImportError:
        sys.stderr.write(
            "[FAIL] cannot parse compose config: no JSON and no PyYAML available\n"
        )
        sys.exit(2)
    return yaml.safe_load(text)


failures = 0


def check(label, condition, detail=""):
    global failures
    status = "PASS" if condition else "FAIL"
    line = f"[{status}] {label}"
    if detail:
        line += f" {detail}"
    print(line)
    if not condition:
        failures += 1


def host_ports(doc, service):
    definition = doc.get("services", {}).get(service, {})
    return definition.get("ports") or []


staging = load(sys.argv[1])
prod = load(sys.argv[2])

# -- docker-compose.staging.yml -------------------------------------------------
check(
    "staging project name is civilpdf-stg",
    staging.get("name") == "civilpdf-stg",
    f"got={staging.get('name')!r}",
)

for service in ("db", "backend"):
    ports = host_ports(staging, service)
    check(f"staging {service} publishes no host ports", len(ports) == 0, f"ports={ports}")

published = [
    (name, port)
    for name, definition in staging.get("services", {}).items()
    for port in (definition.get("ports") or [])
]
check(
    "staging publishes exactly one host port",
    len(published) == 1,
    f"count={len(published)}",
)
if len(published) == 1:
    name, port = published[0]
    check("staging published port belongs to frontend", name == "frontend", f"service={name}")
    check(
        "staging frontend binds loopback only",
        port.get("host_ip") == "127.0.0.1",
        f"host_ip={port.get('host_ip')!r}",
    )
    check(
        "staging frontend publishes a host port",
        str(port.get("published", "")) != "",
        f"published={port.get('published')!r}",
    )

# -- docker-compose.prod.yml ----------------------------------------------------
for service in ("db", "backend"):
    ports = host_ports(prod, service)
    check(f"prod {service} publishes no host ports", len(ports) == 0, f"ports={ports}")

# -- infra/staging/identifiers.json contract -----------------------------------
# identifiers.json is the single source of truth for the staging environment.
# Fail when the compose files or the shipped unit/script files drift from it
# (e.g. someone renames the project, moves the port, or adds a volume).
import os

root = sys.argv[3]
ids_path = os.path.join(root, "infra", "staging", "identifiers.json")
ids = None
try:
    with open(ids_path, encoding="utf-8") as handle:
        ids = json.load(handle)
    check("identifiers.json is readable JSON", True)
except OSError as exc:
    check("identifiers.json is readable JSON", False, f"{exc}")
except json.JSONDecodeError as exc:
    check("identifiers.json is readable JSON", False, f"invalid JSON: {exc}")

if ids is not None:
    check(
        "identifiers environment is staging",
        ids.get("environment") == "staging",
        f"got={ids.get('environment')!r}",
    )
    check(
        "staging compose project matches identifiers",
        staging.get("name") == ids.get("composeProject"),
        f"compose={staging.get('name')!r} identifiers={ids.get('composeProject')!r}",
    )
    listen = ids.get("listen") or {}
    if len(published) == 1:
        _svc, port = published[0]
        check(
            "staging published port matches identifiers",
            str(port.get("published")) == str(listen.get("port")),
            f"compose={port.get('published')!r} identifiers={listen.get('port')!r}",
        )
        check(
            "staging bind host matches identifiers",
            port.get("host_ip") == listen.get("host"),
            f"compose={port.get('host_ip')!r} identifiers={listen.get('host')!r}",
        )

    db_environment = staging.get("services", {}).get("db", {}).get("environment") or {}
    check(
        "staging database name matches identifiers",
        db_environment.get("POSTGRES_DB") == ids.get("databaseName"),
        f"compose={db_environment.get('POSTGRES_DB')!r} identifiers={ids.get('databaseName')!r}",
    )

    configured_volumes = staging.get("volumes") or {}
    for key in ("postgres", "uploads"):
        expected = (ids.get("volumes") or {}).get(key)
        check(
            f"staging volume {key} matches identifiers",
            bool(expected) and expected in configured_volumes,
            f"identifiers={expected!r} compose={sorted(configured_volumes)}",
        )

    units = ids.get("units") or {}
    for key in ("app", "tunnel"):
        unit = units.get(key)
        check(
            f"identifiers unit {key} exists",
            bool(unit) and os.path.isfile(os.path.join(root, "deploy", unit)),
            f"deploy/{unit}",
        )
    for key in ("composeFile", "repoEnvExample", "seedScript", "smokeScript"):
        rel = ids.get(key)
        check(
            f"identifiers {key} exists",
            bool(rel) and os.path.isfile(os.path.join(root, rel)),
            f"{rel}",
        )

    production = ids.get("production") or {}
    prod_db_environment = prod.get("services", {}).get("db", {}).get("environment") or {}
    check(
        "prod database name matches identifiers",
        prod_db_environment.get("POSTGRES_DB") == production.get("databaseName"),
        f"compose={prod_db_environment.get('POSTGRES_DB')!r} identifiers={production.get('databaseName')!r}",
    )
    check(
        "staging and production databases differ",
        bool(ids.get("databaseName")) and ids.get("databaseName") != production.get("databaseName"),
        f"staging={ids.get('databaseName')!r} prod={production.get('databaseName')!r}",
    )
    check(
        "staging and production FQDNs differ",
        bool(ids.get("fqdn")) and ids.get("fqdn") != production.get("fqdn"),
        f"staging={ids.get('fqdn')!r} prod={production.get('fqdn')!r}",
    )
    check(
        "staging and production tunnels differ",
        bool(ids.get("tunnelName")) and ids.get("tunnelName") != production.get("tunnelName"),
        f"staging={ids.get('tunnelName')!r} prod={production.get('tunnelName')!r}",
    )

sys.exit(1 if failures else 0)
PY
  py_status=$?
  set -e
  if [[ "$py_status" -ne 0 ]]; then
    FAIL=1
  fi
fi

echo
if [[ "$FAIL" -ne 0 ]]; then
  echo "COMPOSE VERIFY: FAILED" >&2
  exit 1
fi
echo "COMPOSE VERIFY: OK"
