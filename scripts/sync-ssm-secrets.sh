#!/usr/bin/env bash
# Uploads the Lambda's secrets from local .env files to SSM Parameter Store.
#
# Run "scripts/sync-ssm-secrets.sh help" for usage. Values are read with
# python-dotenv (the parser pydantic-settings uses), validated, compared with
# what SSM already holds and written only when they changed. They are never
# printed, never passed as command-line arguments and never stored in Terraform.
#
# Must run on the macOS system bash (3.2): no associative arrays, no mapfile.

set -euo pipefail

readonly REGION="us-east-1"
readonly DEFAULT_ENVIRONMENT="prod"

# One secret per line: SSM name suffix | source file | variable | transform.
# Paths are relative to the repo root. Add a line here for a new secret.
readonly SECRETS="database_url|.env.cloud|DATABASE_URL|to_transaction_pooler
openai_api_key|.env|OPENAI_API_KEY|check_openai_key"

# shellcheck source=lib/ui.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/ui.sh"

usage() {
  title "SSM secrets" "help"
  cat >&2 <<EOF
  ${BOLD}Usage:${RESET} scripts/sync-ssm-secrets.sh ${CYAN}[environment]${RESET} ${CYAN}[options]${RESET}

  Reads the Lambda's secrets from local .env files and writes them to SSM
  Parameter Store as SecureString, only when they changed. Values are never shown.

  ${BOLD}Secrets${RESET}
    ${CYAN}/sobreplano/<env>/database_url${RESET}     DATABASE_URL in .env.cloud, converted to the
                                       Supabase transaction pooler ${DIM}(port 6543)${RESET}
    ${CYAN}/sobreplano/<env>/openai_api_key${RESET}   OPENAI_API_KEY in .env

  ${BOLD}Environments${RESET}
    ${CYAN}prod${RESET}      Profile sobreplano-prod ${DIM}(default)${RESET}

  ${BOLD}Options${RESET}
    ${CYAN}--dry-run${RESET}         Validate and compare with SSM, but write nothing
    ${CYAN}--profile NAME${RESET}    AWS profile ${DIM}(default: sobreplano-<env>)${RESET}
    ${CYAN}-h, --help${RESET}        Show this help

  ${BOLD}Examples${RESET}
    scripts/sync-ssm-secrets.sh --dry-run
    scripts/sync-ssm-secrets.sh

EOF
}

require_tools() {
  command -v aws >/dev/null 2>&1 || die "AWS CLI not found."
  command -v jq >/dev/null 2>&1 || die "jq not found. Install it with: brew install jq"
  command -v uv >/dev/null 2>&1 || die "uv not found."
}

# Prints the value of a variable from a .env file, or fails if it is missing or empty.
dotenv_get() {
  local file="$1" key="$2"
  [[ -f "$file" ]] || die "$file not found (run from a full checkout of the repo)."
  uv run --quiet --no-sync python -c '
import sys
from dotenv import dotenv_values

value = dotenv_values(sys.argv[1]).get(sys.argv[2])
if not value:
    sys.exit(3)
sys.stdout.write(value)
' "$file" "$key" || die "$key is missing or empty in $file."
}

# --- Transforms: validate a value and print it in the form the Lambda needs ---

# The Lambda runs outside a VPC (IPv4 only) and is serverless, so it must use the
# shared pooler in transaction mode (port 6543). .env.cloud holds the session
# mode URL (5432) used by Alembic; only the port differs.
to_transaction_pooler() {
  local url="$1"
  url="${url/.pooler.supabase.com:5432\//.pooler.supabase.com:6543/}"
  [[ "$url" == postgresql+psycopg://* ]] ||
    die "DATABASE_URL must start with postgresql+psycopg:// (SQLAlchemy with psycopg 3)."
  [[ "$url" =~ ^postgresql\+psycopg://postgres\.[a-z0-9]+:[^@]+@[a-z0-9-]+\.pooler\.supabase\.com:6543/postgres$ ]] ||
    die "DATABASE_URL in .env.cloud is not a Supabase shared pooler URL (postgres.<ref>:<password>@<host>.pooler.supabase.com:5432/postgres)."
  [[ "$url" != *"[YOUR-PASSWORD]"* ]] || die "DATABASE_URL in .env.cloud still has the [YOUR-PASSWORD] placeholder."
  printf '%s' "$url"
}

check_openai_key() {
  [[ "$1" == sk-* ]] || die "OPENAI_API_KEY in .env does not look like an OpenAI key (sk-...)."
  printf '%s' "$1"
}

# --- SSM ---

check_credentials() {
  local arn
  arn="$(aws sts get-caller-identity --profile "$PROFILE" --region "$REGION" --query Arn --output text 2>/dev/null)" ||
    die "No valid credentials for profile '$PROFILE'. Sign in with: eval \"\$(scripts/aws-sso.sh)\""
  ok "Signed in as $(hl "$arn")"
}

# Prints the current value, prints nothing if the parameter does not exist, fails otherwise.
ssm_current_value() {
  local name="$1" output
  if output="$(aws ssm get-parameter --name "$name" --with-decryption --profile "$PROFILE" --region "$REGION" \
    --query Parameter.Value --output text 2>&1)"; then
    printf '%s' "$output"
  elif [[ "$output" == *ParameterNotFound* ]]; then
    return 0
  else
    die "Could not read $name: $output"
  fi
}

# Writes through a private temp file so the value never appears in `ps` output.
ssm_put() {
  local name="$1" value="$2" request
  request="$(umask 077 && mktemp)"
  # shellcheck disable=SC2064 # expand now: $request is local and gone when the trap runs
  trap "rm -f '$request'" EXIT
  SSM_VALUE="$value" jq -n --arg name "$name" \
    '{Name: $name, Value: env.SSM_VALUE, Type: "SecureString", Overwrite: true}' >"$request"
  aws ssm put-parameter --cli-input-json "file://$request" --profile "$PROFILE" --region "$REGION" >/dev/null ||
    die "Could not write $name."
  rm -f "$request"
  trap - EXIT
}

CHANGES=0

# Adds one row per secret to the summary table; CHANGES counts pending or written changes.
sync_secret() {
  local suffix="$1" file="$2" key="$3" transform="$4" name raw value current
  name="/sobreplano/$ENVIRONMENT/$suffix"
  raw="$(dotenv_get "$file" "$key")"
  value="$("$transform" "$raw")"
  current="$(ssm_current_value "$name")"

  if [[ "$current" == "$value" ]]; then
    table_row info "$name" "up to date ($key in $file)"
    return 0
  fi
  CHANGES=$((CHANGES + 1))
  if [[ "$DRY_RUN" -eq 1 ]]; then
    if [[ -z "$current" ]]; then
      table_row warn "$name" "would be created from $key in $file"
    else
      table_row warn "$name" "would be updated from $key in $file"
    fi
  else
    ssm_put "$name" "$value"
    if [[ -z "$current" ]]; then
      table_row ok "$name" "created from $key in $file"
    else
      table_row ok "$name" "updated from $key in $file"
    fi
  fi
}

# --- Arguments ---

ENVIRONMENT="$DEFAULT_ENVIRONMENT"
PROFILE=""
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h | --help | help)
      usage
      exit 0
      ;;
    --dry-run) DRY_RUN=1 && shift ;;
    --profile)
      [[ $# -ge 2 ]] || die "--profile needs a value."
      PROFILE="$2" && shift 2
      ;;
    --profile=*) PROFILE="${1#*=}" && shift ;;
    -*) die "Unknown option: $1 (see 'scripts/sync-ssm-secrets.sh help')." ;;
    prod) ENVIRONMENT="$1" && shift ;;
    *) die "Unknown environment: '$1'. Environments: prod." ;;
  esac
done
PROFILE="${PROFILE:-sobreplano-$ENVIRONMENT}"

cd "$(dirname "$0")/.." # .env paths are relative to the repo root
if [[ "$DRY_RUN" -eq 1 ]]; then title "SSM secrets" "dry run · $ENVIRONMENT"; else title "SSM secrets" "sync · $ENVIRONMENT"; fi
require_tools
check_credentials
if [[ "$DRY_RUN" -eq 1 ]]; then warn "Dry run: nothing will be written"; fi
info "Reading the .env files and comparing with SSM ${DIM}(region $REGION)${RESET}"

# fd 3 keeps the list away from the stdin of uv and aws inside the loop.
while IFS='|' read -r suffix file key transform <&3; do
  [[ -n "$suffix" ]] || continue
  sync_secret "$suffix" "$file" "$key" "$transform"
done 3<<<"$SECRETS"

printf '\n' >&2
table_print
printf '\n' >&2
if [[ "$CHANGES" -eq 0 ]]; then
  ok "Everything is up to date"
elif [[ "$DRY_RUN" -eq 1 ]]; then
  warn "$CHANGES change(s) pending"
  hint "Write them with: scripts/sync-ssm-secrets.sh"
else
  ok "$CHANGES secret(s) written"
  hint "The Lambda reads these at cold start; a running container keeps the old values until it is replaced."
fi
printf '\n' >&2
