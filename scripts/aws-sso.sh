#!/usr/bin/env bash
# Sets up and refreshes AWS IAM Identity Center (SSO) access to Sobreplano's AWS accounts.
#
# Run "scripts/aws-sso.sh help" for usage. Nothing account-specific lives in this
# public repo: the access portal URL is asked once and stored only in
# ~/.aws/config, and the account ID is discovered from your SSO session.
#
# All messages go to stderr; on success "login" prints a single
# "export AWS_PROFILE=..." line to stdout, so `eval "$(scripts/aws-sso.sh)"`
# signs in and sets the profile in the current shell.
#
# Must run on the macOS system bash (3.2): no associative arrays, no mapfile.

set -euo pipefail

readonly SSO_SESSION="sobreplano"
readonly SSO_REGION="us-east-1"
readonly CLI_REGION="us-east-1"
readonly SSO_SCOPES="sso:account:access"
readonly AWS_CONFIG="${AWS_CONFIG_FILE:-$HOME/.aws/config}"
readonly SSO_CACHE_DIR="$HOME/.aws/sso/cache"
readonly DEFAULT_ENVIRONMENT="prod"
# Add a new environment here and in account_name_for() when its account exists.
readonly ENVIRONMENTS="prod"

# The AWS CLI loads AWS_PROFILE before any command, even "aws sso login
# --sso-session", and fails if that profile does not exist yet (first run after
# an earlier export). Every call below names its profile or session explicitly,
# so drop both variables here and keep the caller's value for the messages.
readonly CALLER_PROFILE="${AWS_PROFILE:-}"
unset AWS_PROFILE AWS_DEFAULT_PROFILE

# shellcheck source=lib/ui.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/ui.sh"

human_minutes() {
  if (($1 >= 60)); then
    printf '%dh %02dm' $(($1 / 60)) $(($1 % 60))
  else
    printf '%d min' "$1"
  fi
}

usage() {
  title "AWS SSO" "help"
  cat >&2 <<EOF
  ${BOLD}Usage:${RESET} scripts/aws-sso.sh ${CYAN}[command]${RESET} ${CYAN}[environment]${RESET} ${CYAN}[options]${RESET}

  Configures and refreshes AWS IAM Identity Center (SSO) access to Sobreplano.
  The first run asks for the AWS access portal URL (ask the project owner).
  The account ID is discovered from your SSO session.

  ${BOLD}Commands${RESET}
    ${CYAN}login${RESET}     Configure what is missing, sign in if needed and verify ${DIM}(default)${RESET}
    ${CYAN}status${RESET}    Show the SSO session, the profile and the signed-in identity
    ${CYAN}logout${RESET}    Sign out of every AWS SSO session in this CLI (aws sso logout)
    ${CYAN}reset${RESET}     Remove Sobreplano's SSO session and profiles from ~/.aws/config
    ${CYAN}help${RESET}      Show this help

  ${BOLD}Environments${RESET}
    ${CYAN}prod${RESET}      Account sobreplano-prod, profile sobreplano-prod ${DIM}(default)${RESET}

  ${BOLD}Options${RESET}
    ${CYAN}--start-url URL${RESET}   Access portal URL (or set SOBREPLANO_SSO_START_URL)
    ${CYAN}--role NAME${RESET}       Permission set to use: AdministratorAccess or SobreplanoDeveloper.
                      Asked for if your user has more than one.
    ${CYAN}-y, --yes${RESET}         Skip confirmations (logout, reset)
    ${CYAN}-h, --help${RESET}        Show this help

  ${BOLD}Examples${RESET}
    eval "\$(scripts/aws-sso.sh)"                  ${DIM}# sign in and export AWS_PROFILE${RESET}
    scripts/aws-sso.sh --role SobreplanoDeveloper  ${DIM}# first run as a developer${RESET}
    scripts/aws-sso.sh status
    scripts/aws-sso.sh reset                       ${DIM}# start over (backs up ~/.aws/config)${RESET}

EOF
}

account_name_for() {
  case "$1" in
    prod) printf 'sobreplano-prod' ;;
    *) return 1 ;;
  esac
}

profile_for() { printf 'sobreplano-%s' "$1"; }

is_command() {
  case "$1" in
    login | status | logout | reset | help) return 0 ;;
    *) return 1 ;;
  esac
}

confirm() {
  local answer
  if [[ "$ASSUME_YES" -eq 1 ]]; then
    return 0
  fi
  [[ -t 0 ]] || die "Confirmation needed and there is no terminal: re-run with --yes."
  read -r -p "  ${YELLOW}?${RESET} $1 ${DIM}[y/N]${RESET} " answer
  [[ "$answer" =~ ^[Yy]$ ]]
}

require_tools() {
  command -v aws >/dev/null 2>&1 ||
    die "AWS CLI not found. Install v2: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
  case "$(aws --version 2>&1)" in
    aws-cli/2.*) ;;
    *) die "AWS CLI v2 is required (found: $(aws --version 2>&1))." ;;
  esac
  command -v jq >/dev/null 2>&1 || die "jq not found. Install it with: brew install jq"
}

# --- ~/.aws/config helpers (INI). Section names are passed without brackets. ---

ini_has_section() {
  [[ -f "$AWS_CONFIG" ]] || return 1
  awk -v want="[$1]" '
    { line = $0; sub(/[ \t\r]+$/, "", line) }
    line == want { found = 1; exit }
    END { exit !found }' "$AWS_CONFIG"
}

ini_get() {
  [[ -f "$AWS_CONFIG" ]] || return 0
  awk -v want="[$1]" -v key="$2" '
    { line = $0; sub(/[ \t\r]+$/, "", line) }
    line ~ /^[ \t]*\[/ { in_section = (line == want); next }
    in_section && index(line, "=") {
      k = substr(line, 1, index(line, "=") - 1)
      gsub(/[ \t]/, "", k)
      if (k == key) {
        v = substr(line, index(line, "=") + 1)
        sub(/^[ \t]+/, "", v)
        print v
        exit
      }
    }' "$AWS_CONFIG"
}

BACKED_UP=0
backup_config() {
  local backup
  [[ "$BACKED_UP" -eq 0 && -f "$AWS_CONFIG" ]] || return 0
  backup="$AWS_CONFIG.backup.$(date +%Y%m%d-%H%M%S)"
  cp -p "$AWS_CONFIG" "$backup"
  BACKED_UP=1
  info "Backup of $AWS_CONFIG saved to $(hl "$backup")"
}

# --- Access portal URL ---

normalize_start_url() {
  local url="$1"
  url="${url%%#*}" # the console copies it as .../start/#
  url="${url%/}"
  printf '%s' "$url"
}

resolve_start_url() {
  local url="${START_URL:-${SOBREPLANO_SSO_START_URL:-}}"
  if [[ -z "$url" ]]; then
    url="$(ini_get "sso-session $SSO_SESSION" sso_start_url)"
  fi
  if [[ -z "$url" ]]; then
    [[ -t 0 ]] || die "No access portal URL: pass --start-url or set SOBREPLANO_SSO_START_URL."
    read -r -p "  ${BLUE}?${RESET} AWS access portal URL ${DIM}(ask the project owner)${RESET}: " url
  fi
  url="$(normalize_start_url "$url")"
  [[ "$url" =~ ^https://[A-Za-z0-9-]+\.awsapps\.com/start$ ]] ||
    die "Not an access portal URL: '$url' (expected https://<id>.awsapps.com/start)."
  printf '%s' "$url"
}

ensure_sso_session() {
  local url="$1" current separator=''
  if ini_has_section "sso-session $SSO_SESSION"; then
    current="$(normalize_start_url "$(ini_get "sso-session $SSO_SESSION" sso_start_url)")"
    [[ "$current" == "$url" ]] ||
      die "SSO session '$SSO_SESSION' points to '$current', not '$url'. Run 'scripts/aws-sso.sh reset' to start over."
    ok "SSO session $(hl "$SSO_SESSION") is configured"
    return 0
  fi
  mkdir -p "$(dirname "$AWS_CONFIG")"
  backup_config
  if [[ -s "$AWS_CONFIG" ]]; then separator=$'\n'; fi
  {
    printf '%s[sso-session %s]\n' "$separator" "$SSO_SESSION"
    printf 'sso_start_url = %s\n' "$url"
    printf 'sso_region = %s\n' "$SSO_REGION"
    printf 'sso_registration_scopes = %s\n' "$SSO_SCOPES"
  } >>"$AWS_CONFIG"
  ok "SSO session $(hl "$SSO_SESSION") added to $AWS_CONFIG"
}

# --- SSO token cache ---

# Prints "<minutes left> <access token>" for the newest unexpired token of this
# portal, or nothing. The token is only kept in memory and passed to the AWS CLI.
cached_token_info() {
  local url="$1"
  compgen -G "$SSO_CACHE_DIR/*.json" >/dev/null || return 0
  jq -r -s --arg url "$url" '
    [ .[] | objects
      | select(.startUrl? == $url and ((.accessToken? | type) == "string"))
      | { token: .accessToken,
          exp: (try (.expiresAt | sub("\\.[0-9]+"; "") | sub("UTC$"; "Z") | fromdateiso8601) catch 0) } ]
    | map(select(.exp > now + 60))
    | sort_by(.exp) | last
    | if . == null then empty else "\(((.exp - now) / 60) | floor) \(.token)" end
  ' "$SSO_CACHE_DIR"/*.json 2>/dev/null || true
}

ensure_signed_in() {
  local url="$1" token_info
  token_info="$(cached_token_info "$url")"
  if [[ -n "$token_info" ]]; then
    ok "Signed in to the access portal ${DIM}($(human_minutes "${token_info%% *}") left)${RESET}"
    return 0
  fi
  info "Opening the browser to sign in to the access portal ${DIM}(MFA is required)${RESET}"
  hint "If it does not open, use the URL and code printed below."
  printf '\n' >&2
  # stdout goes to stderr so `eval "$(scripts/aws-sso.sh)"` only sees the export line.
  aws sso login --sso-session "$SSO_SESSION" >&2
  printf '\n' >&2
  [[ -n "$(cached_token_info "$url")" ]] || die "Sign-in finished but no valid token was cached."
  ok "Signed in to the access portal"
}

# --- Account and role discovery ---

ACCOUNT_ID=""
ROLE_NAME=""

discover_account() {
  local token="$1" account_name="$2" accounts ids count
  accounts="$(aws sso list-accounts --access-token "$token" --region "$SSO_REGION" --output json)" ||
    die "Could not list your AWS accounts."
  ids="$(jq -r --arg name "$account_name" '.accountList[] | select(.accountName == $name) | .accountId' <<<"$accounts")"
  count="$(printf '%s' "$ids" | grep -c . || true)"
  [[ "$count" -eq 1 ]] ||
    die "Your user has no access to account '$account_name' (or it is ambiguous). Ask the project owner for an assignment."
  ACCOUNT_ID="$ids"
}

discover_role() {
  local token="$1" account_id="$2" roles count role
  roles="$(aws sso list-account-roles --access-token "$token" --account-id "$account_id" \
    --region "$SSO_REGION" --output json | jq -r '.roleList[].roleName' | sort)" ||
    die "Could not list your roles in account $account_id."
  count="$(printf '%s' "$roles" | grep -c . || true)"
  [[ "$count" -gt 0 ]] || die "Your user has no permission set in this account."

  if [[ -n "$ROLE" ]]; then
    printf '%s\n' "$roles" | grep -qx -- "$ROLE" ||
      die "Role '$ROLE' is not assigned to you. Available: $(printf '%s' "$roles" | tr '\n' ' ')"
    ROLE_NAME="$ROLE"
  elif [[ "$count" -eq 1 ]]; then
    ROLE_NAME="$roles"
  else
    [[ -t 0 ]] || die "Several roles available ($(printf '%s' "$roles" | tr '\n' ' ')): pass --role."
    info "Choose the permission set for this profile:"
    PS3="  ${BLUE}?${RESET} Number: "
    # shellcheck disable=SC2086 # role names have no spaces; word splitting is intended
    select role in $roles; do
      if [[ -n "$role" ]]; then
        ROLE_NAME="$role"
        break
      fi
    done
    [[ -n "$ROLE_NAME" ]] || die "No role chosen."
  fi
}

# --- Profile ---

configure_profile() {
  local profile="$1" section="profile $1"
  if [[ "$(ini_get "$section" sso_session)" == "$SSO_SESSION" &&
    "$(ini_get "$section" sso_account_id)" == "$ACCOUNT_ID" &&
    "$(ini_get "$section" sso_role_name)" == "$ROLE_NAME" &&
    "$(ini_get "$section" region)" == "$CLI_REGION" ]]; then
    ok "Profile $(hl "$profile") is configured ${DIM}(role $ROLE_NAME)${RESET}"
    return 0
  fi
  if ini_has_section "$section"; then
    warn "Updating profile $(hl "$profile") ${DIM}(role $(ini_get "$section" sso_role_name) → $ROLE_NAME)${RESET}"
  fi
  backup_config
  aws configure set sso_session "$SSO_SESSION" --profile "$profile"
  aws configure set sso_account_id "$ACCOUNT_ID" --profile "$profile"
  aws configure set sso_role_name "$ROLE_NAME" --profile "$profile"
  aws configure set region "$CLI_REGION" --profile "$profile"
  aws configure set output json --profile "$profile"
  ok "Profile $(hl "$profile") written ${DIM}(role $ROLE_NAME)${RESET}"
}

IDENTITY_ARN=""

verify_profile() {
  local profile="$1" identity account
  identity="$(aws sts get-caller-identity --profile "$profile" --output json)" ||
    die "The profile '$profile' does not work. Try 'scripts/aws-sso.sh reset' and sign in again."
  account="$(jq -r '.Account' <<<"$identity")"
  IDENTITY_ARN="$(jq -r '.Arn' <<<"$identity")"
  [[ "$account" == "$ACCOUNT_ID" ]] ||
    die "The profile '$profile' reached account $account instead of $ACCOUNT_ID."
  ok "Credentials verified"
}

# --- Commands ---

cmd_login() {
  local env="$1" account_name profile url token_info token
  account_name="$(account_name_for "$env")"
  profile="$(profile_for "$env")"
  require_tools
  title "AWS SSO" "login · $env"

  url="$(resolve_start_url)"
  ensure_sso_session "$url"
  ensure_signed_in "$url"

  # Reuse the saved account and role unless a different role was asked for;
  # verify_profile catches assignments that no longer exist.
  ACCOUNT_ID="$(ini_get "profile $profile" sso_account_id)"
  ROLE_NAME="$(ini_get "profile $profile" sso_role_name)"
  if [[ -z "$ACCOUNT_ID" || -z "$ROLE_NAME" || (-n "$ROLE" && "$ROLE" != "$ROLE_NAME") ]]; then
    token_info="$(cached_token_info "$url")"
    token="${token_info#* }"
    discover_account "$token" "$account_name"
    discover_role "$token" "$ACCOUNT_ID"
  fi

  configure_profile "$profile"
  verify_profile "$profile"

  printf '\n' >&2
  table_row ok "Profile" "$profile"
  table_row info "Account" "$ACCOUNT_ID"
  table_row info "Role" "$ROLE_NAME"
  table_row info "Region" "$CLI_REGION"
  table_row ok "Identity" "$IDENTITY_ARN"
  table_print
  printf '\n' >&2
  if [[ "$CALLER_PROFILE" == "$profile" ]]; then
    ok "AWS_PROFILE is already $(hl "$profile") in this shell"
  else
    hint "Use it in this shell with: export AWS_PROFILE=$profile"
    hint "Or sign in and export in one step: eval \"\$(scripts/aws-sso.sh)\""
  fi
  printf '\n' >&2
  printf 'export AWS_PROFILE=%s\n' "$profile"
}

cmd_status() {
  local env="$1" profile url token_info identity healthy=1
  profile="$(profile_for "$env")"
  require_tools
  title "AWS SSO" "status · $env"

  url="$(normalize_start_url "$(ini_get "sso-session $SSO_SESSION" sso_start_url)")"
  if [[ -z "$url" ]]; then
    table_row warn "SSO session" "$SSO_SESSION (not configured)"
    table_print
    printf '\n' >&2
    hint "Set it up with: scripts/aws-sso.sh"
    return 1
  fi
  table_row ok "SSO session" "$SSO_SESSION"
  table_row info "Portal" "$url"

  token_info="$(cached_token_info "$url")"
  if [[ -n "$token_info" ]]; then
    table_row ok "Sign-in" "active, $(human_minutes "${token_info%% *}") left"
  else
    table_row warn "Sign-in" "not signed in, or expired"
    healthy=0
  fi

  if ! ini_has_section "profile $profile"; then
    table_row warn "Profile" "$profile (not configured)"
    table_print
    printf '\n' >&2
    hint "Set it up with: scripts/aws-sso.sh"
    return 1
  fi
  table_row ok "Profile" "$profile"
  table_row info "Account" "$(ini_get "profile $profile" sso_account_id)"
  table_row info "Role" "$(ini_get "profile $profile" sso_role_name)"
  table_row info "Region" "$(ini_get "profile $profile" region)"

  if [[ "$CALLER_PROFILE" == "$profile" ]]; then
    table_row ok "AWS_PROFILE" "$profile"
  else
    table_row warn "AWS_PROFILE" "${CALLER_PROFILE:-unset} (expected $profile)"
    healthy=0
  fi

  if [[ -n "$token_info" ]]; then
    if identity="$(aws sts get-caller-identity --profile "$profile" --query Arn --output text 2>/dev/null)"; then
      table_row ok "Identity" "$identity"
    else
      table_row warn "Identity" "the profile returns no identity"
      healthy=0
    fi
  fi

  table_print
  if [[ "$healthy" -eq 0 ]]; then
    printf '\n' >&2
    hint "Sign in and export the profile with: eval \"\$(scripts/aws-sso.sh)\""
  fi
  printf '\n' >&2
}

cmd_logout() {
  require_tools
  title "AWS SSO" "logout"
  warn "'aws sso logout' signs out of every AWS SSO session in this CLI, not only Sobreplano's."
  confirm "Sign out?" || {
    info "Cancelled."
    return 0
  }
  aws sso logout >&2
  ok "Signed out"
  hint "Sign in again with: eval \"\$(scripts/aws-sso.sh)\""
}

cmd_reset() {
  local sections tmp
  title "AWS SSO" "reset"
  if [[ ! -f "$AWS_CONFIG" ]]; then
    info "$AWS_CONFIG does not exist: nothing to reset."
    return 0
  fi
  sections="$(awk -v session="[sso-session $SSO_SESSION]" '
    { line = $0; sub(/[ \t\r]+$/, "", line) }
    line == session || line ~ /^\[profile sobreplano-[a-z0-9-]+\]$/ { print "      • " line }' "$AWS_CONFIG")"
  if [[ -z "$sections" ]]; then
    info "No Sobreplano sections in $AWS_CONFIG: nothing to reset."
    return 0
  fi
  info "These sections will be removed from $AWS_CONFIG (other profiles stay untouched):"
  printf '%s%s%s\n' "$CYAN" "$sections" "$RESET" >&2
  confirm "Remove them?" || {
    info "Cancelled."
    return 0
  }
  backup_config
  tmp="$(mktemp)"
  # shellcheck disable=SC2064 # expand now: $tmp is local and gone when the trap runs
  trap "rm -f '$tmp'" EXIT
  awk -v session="[sso-session $SSO_SESSION]" '
    { line = $0; sub(/[ \t\r]+$/, "", line) }
    line ~ /^[ \t]*\[/ { skip = (line == session || line ~ /^\[profile sobreplano-[a-z0-9-]+\]$/) }
    !skip { print }' "$AWS_CONFIG" >"$tmp"
  cat "$tmp" >"$AWS_CONFIG" # keeps the file's permissions
  ok "Removed"
  hint "Cached sign-ins are untouched; drop them too with: scripts/aws-sso.sh logout"
}

# --- Arguments ---

COMMAND="login"
ENVIRONMENT="$DEFAULT_ENVIRONMENT"
START_URL=""
ROLE=""
ASSUME_YES=0
command_given=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h | --help) COMMAND="help" && shift ;;
    -y | --yes) ASSUME_YES=1 && shift ;;
    --start-url)
      [[ $# -ge 2 ]] || die "--start-url needs a value."
      START_URL="$2" && shift 2
      ;;
    --start-url=*) START_URL="${1#*=}" && shift ;;
    --role)
      [[ $# -ge 2 ]] || die "--role needs a value."
      ROLE="$2" && shift 2
      ;;
    --role=*) ROLE="${1#*=}" && shift ;;
    -*) die "Unknown option: $1 (see 'scripts/aws-sso.sh help')." ;;
    *)
      if [[ "$command_given" -eq 0 ]] && is_command "$1"; then
        COMMAND="$1"
        command_given=1
      elif account_name_for "$1" >/dev/null; then
        ENVIRONMENT="$1"
      else
        die "Unknown command or environment: '$1'. Environments: $ENVIRONMENTS."
      fi
      shift
      ;;
  esac
done

case "$COMMAND" in
  login) cmd_login "$ENVIRONMENT" ;;
  status) cmd_status "$ENVIRONMENT" ;;
  logout) cmd_logout ;;
  reset) cmd_reset ;;
  help) usage ;;
esac
