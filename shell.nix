{ pkgs ? import <nixpkgs> {} }:

let
  python = pkgs.python312;
in
pkgs.mkShell {
  name = "aito-accounting-demo";

  buildInputs = [
    # Python
    python
    pkgs.uv

    # Node / Next.js frontend (future)
    pkgs.nodejs_20
    pkgs.corepack

    # Playwright system dependencies
    pkgs.playwright-driver.browsers

    # Dev tools
    pkgs.jq
    pkgs.curl
    pkgs.httpie
    pkgs.watchexec
  ];

  shellHook = ''
    # Let uv manage the virtualenv
    export UV_PYTHON_PREFERENCE=only-system

    # Sync deps on shell entry
    if [ -f pyproject.toml ]; then
      uv sync --quiet 2>/dev/null || true
    fi

    # Playwright browser path (use nix-managed browsers)
    export PLAYWRIGHT_BROWSERS_PATH="${pkgs.playwright-driver.browsers}"
    export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

    # Project env. No AITO_API_URL / AITO_API_KEY defaults here: src/config.py
    # lets an exported variable win over .env, so a default exported by the
    # shell would silently shadow the .env credentials. (The old URL default,
    # localhost:8200, was this demo's own API port, not an Aito engine.)
    export PYTHONDONTWRITEBYTECODE=1
    export PYTHONUNBUFFERED=1

    # Remind if Aito key is missing
    if [ -z "''${AITO_API_KEY:-}" ] && [ ! -f .env ]; then
      echo ""
      echo "  AITO_API_KEY not set. Export it or add to .env"
      echo "  export AITO_API_KEY=your-key-here"
      echo ""
    fi

    echo ""
    echo "Aito Accounting Demo — run ./do help for available commands"
    echo ""
  '';
}
