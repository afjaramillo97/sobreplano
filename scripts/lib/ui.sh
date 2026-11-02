# Terminal output helpers shared by the scripts in scripts/: colours, messages and tables.
#
# Source it after `set -euo pipefail`. Everything is written to stderr, so a
# script's stdout stays free for machine-readable output. Colours are used only
# when stderr is a terminal and NO_COLOR is unset. Bash 3.2 compatible.

# shellcheck disable=SC2034 # the colours are used by the scripts that source this file
if [[ -t 2 && -z "${NO_COLOR:-}" ]]; then
  BLUE=$'\033[34m' CYAN=$'\033[36m' GREEN=$'\033[32m' YELLOW=$'\033[33m' RED=$'\033[31m'
  BOLD=$'\033[1m' DIM=$'\033[2m' RESET=$'\033[0m'
else
  BLUE='' CYAN='' GREEN='' YELLOW='' RED='' BOLD='' DIM='' RESET=''
fi

info() { printf '  %s›%s %s\n' "$BLUE" "$RESET" "$*" >&2; }
ok() { printf '  %s✓%s %s\n' "$GREEN" "$RESET" "$*" >&2; }
warn() { printf '  %s!%s %s\n' "$YELLOW" "$RESET" "$*" >&2; }
hint() { printf '  %s→ %s%s\n' "$DIM" "$*" "$RESET" >&2; }
die() {
  printf '\n  %s✗ Error:%s %s\n\n' "$RED$BOLD" "$RESET" "$*" >&2
  exit 1
}

# Highlights a value (profile, role, URL) inside a message.
hl() { printf '%s%s%s' "$CYAN" "$1" "$RESET"; }

repeat() {
  local i out=''
  for ((i = 0; i < $2; i++)); do out+="$1"; done
  printf '%s' "$out"
}

# Prints the header of a command: "Sobreplano · <tool>  <subtitle>" and a rule.
title() {
  printf '\n  %sSobreplano · %s%s  %s%s%s\n' "$BOLD" "$1" "$RESET" "$DIM" "$2" "$RESET" >&2
  printf '  %s%s%s\n\n' "$DIM" "$(repeat '─' 44)" "$RESET" >&2
}

# --- Key/value tables: collect rows with table_row, draw them with table_print. ---
# Widths are measured on plain text, so labels and values must be ASCII without
# colour codes; the state icon is drawn in its own fixed-width slot.

TABLE_STATE=()
TABLE_LABEL=()
TABLE_VALUE=()

table_row() { # state (ok | warn | info) label value
  TABLE_STATE+=("$1")
  TABLE_LABEL+=("$2")
  TABLE_VALUE+=("$3")
}

table_print() {
  local i n="${#TABLE_LABEL[@]}" lw=0 vw=0 icon color value_color
  for ((i = 0; i < n; i++)); do
    if ((${#TABLE_LABEL[i]} > lw)); then lw=${#TABLE_LABEL[i]}; fi
    if ((${#TABLE_VALUE[i]} > vw)); then vw=${#TABLE_VALUE[i]}; fi
  done
  printf '  %s╭%s┬%s╮%s\n' "$DIM" "$(repeat '─' $((lw + 4)))" "$(repeat '─' $((vw + 2)))" "$RESET" >&2
  for ((i = 0; i < n; i++)); do
    value_color=''
    case "${TABLE_STATE[i]}" in
      ok) icon='✓' color="$GREEN" ;;
      warn) icon='!' color="$YELLOW" value_color="$YELLOW" ;;
      *) icon='·' color="$DIM" ;;
    esac
    printf '  %s│%s %s%s%s %s%s%s%*s %s│%s %s%s%s%*s %s│%s\n' \
      "$DIM" "$RESET" "$color" "$icon" "$RESET" \
      "$BOLD" "${TABLE_LABEL[i]}" "$RESET" $((lw - ${#TABLE_LABEL[i]})) '' \
      "$DIM" "$RESET" "$value_color" "${TABLE_VALUE[i]}" "$RESET" $((vw - ${#TABLE_VALUE[i]})) '' \
      "$DIM" "$RESET" >&2
  done
  printf '  %s╰%s┴%s╯%s\n' "$DIM" "$(repeat '─' $((lw + 4)))" "$(repeat '─' $((vw + 2)))" "$RESET" >&2
  TABLE_STATE=()
  TABLE_LABEL=()
  TABLE_VALUE=()
}
