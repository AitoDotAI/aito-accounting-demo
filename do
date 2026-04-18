#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cmd_help() {
  cat <<EOF
Usage: ./do <command>

Commands:
  help          Show this help
  dev           Start the backend API server (port 8200)
  demo          Open the HTML demo in a browser
  load-data     Upload sample data to Aito
  reset-data    Drop and reload all Aito tables
  test          Run the test suite
  fmt           Format code
  check         Run all pre-merge checks (test + fmt)

EOF
}

cmd_dev() {
  echo "Starting Ledger Pro API on http://localhost:8000"
  cd "$SCRIPT_DIR"
  uv run uvicorn src.app:app --reload --port 8200
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

cmd_load_data() {
  cd "$SCRIPT_DIR"
  uv run python -m src.data_loader
}

cmd_reset_data() {
  cd "$SCRIPT_DIR"
  uv run python -m src.data_loader --reset
}

cmd_test() {
  cd "$SCRIPT_DIR"
  uv run pytest tests/ -v
}

cmd_fmt() {
  echo "No formatter configured yet."
}

cmd_check() {
  cmd_test
  cmd_fmt
}

case "${1:-help}" in
  help)       cmd_help ;;
  dev)        cmd_dev ;;
  demo)       cmd_demo ;;
  load-data)  cmd_load_data ;;
  reset-data) cmd_reset_data ;;
  test)       cmd_test ;;
  fmt)        cmd_fmt ;;
  check)      cmd_check ;;
  *)
    echo "Unknown command: $1" >&2
    cmd_help
    exit 1
    ;;
esac
