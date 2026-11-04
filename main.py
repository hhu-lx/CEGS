"""Run the dashboard from PyCharm or the legacy CLI simulation."""

from __future__ import annotations

import os
import sys


def run_web() -> None:
    """Start the FastAPI dashboard for the standard IDE Run action."""
    import uvicorn

    uvicorn.run(
        "src.app:app",
        host=os.getenv("CESYNERGY_HOST", "127.0.0.1"),
        port=int(os.getenv("CESYNERGY_PORT", "8000")),
        reload=False,
    )


def run_cli() -> None:
    """Preserve the previous command-line simulation entry point."""
    from src.simulation.orchestrator import main as cli_main

    cli_main()


def main() -> None:
    if "--cli" in sys.argv[1:]:
        sys.argv = [sys.argv[0]] + [arg for arg in sys.argv[1:] if arg != "--cli"]
        run_cli()
    else:
        run_web()


if __name__ == "__main__":
    main()
