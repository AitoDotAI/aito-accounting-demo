#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cmd_help() {
  cat <<EOF
Usage: ./do <command>

Commands:
  help          Show this help
  demo          Open the demo in a browser
  fmt           Format code
  test          Run the test suite
  check         Run all pre-merge checks (test + fmt)

EOF
}

cmd_demo() {
  local file="$SCRIPT_DIR/ledger-pro-demo.html"
  if [[ ! -f "$file" ]]; then
    echo "Error: ledger-pro-demo.html not found" >&2
    exit 1
  fi

  echo "Opening demo..."
  if command -v xdg-open &>/dev/null; then
    xdg-open "$file"
  elif command -v open &>/dev/null; then
    open "$file"
  else
    echo "Open manually: $file"
  fi
}

cmd_fmt() {
  echo "No source code to format yet."
}

cmd_test() {
  echo "No tests yet."
}

cmd_check() {
  cmd_test
  cmd_fmt
}

case "${1:-help}" in
  help)   cmd_help ;;
  demo)   cmd_demo ;;
  fmt)    cmd_fmt ;;
  test)   cmd_test ;;
  check)  cmd_check ;;
  *)
    echo "Unknown command: $1" >&2
    cmd_help
    exit 1
    ;;
esac
