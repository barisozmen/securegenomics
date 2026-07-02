#!/usr/bin/env python3
"""Launch SecureGenomics Desktop.

    python3 run.py                # native window (pywebview) if available, else browser
    python3 run.py --browser      # force the browser fallback
    python3 run.py --no-open      # start the server only (open the printed URL yourself)
    python3 run.py --port 8850    # pin the port (default: an ephemeral free port)

The backend imports the real ``securegenomics`` CLI package. If the CLI is
installed (``bash setup.sh`` / ``pip install -e .``) that install is used;
otherwise this script adds the sibling ``src/`` tree to ``sys.path`` so the app
runs straight from a checkout with no install step.
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path


def _ensure_cli_importable() -> None:
    try:
        import securegenomics  # noqa: F401
        return
    except ImportError:
        pass
    src = Path(__file__).resolve().parent.parent / "src"
    if (src / "securegenomics").is_dir():
        sys.path.insert(0, str(src))
    try:
        import securegenomics  # noqa: F401
    except ImportError as exc:
        sys.exit(
            "Could not import the SecureGenomics CLI. Install it with "
            "`bash setup.sh` in the repo root, or run this from a full checkout.\n"
            f"({exc})"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="SecureGenomics Desktop")
    parser.add_argument("--browser", action="store_true", help="Force browser mode")
    parser.add_argument("--no-open", action="store_true", help="Start server only")
    parser.add_argument("--port", type=int, default=0, help="Port (default: ephemeral)")
    args = parser.parse_args()

    _ensure_cli_importable()

    # Import after sys.path is set so the bridge can import the CLI engine.
    from securegenomics_desktop import server as server_module
    from securegenomics_desktop.server import DesktopServer

    srv = DesktopServer(port=args.port)
    print(f"SecureGenomics Desktop → {srv.url}")

    if args.no_open:
        srv.start_in_thread()
        print("Server running. Press Ctrl+C to stop.")
        try:
            import time
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            srv.shutdown()
        return

    if not args.browser:
        try:
            import webview  # type: ignore

            srv.start_in_thread()
            window = webview.create_window(
                "Gencrypt",
                srv.url,
                width=1240,
                height=820,
                min_size=(940, 640),
            )
            server_module.WEBVIEW_WINDOW = window
            webview.start()  # blocks until the window closes
            srv.shutdown()
            return
        except ImportError:
            print("pywebview not installed — falling back to the browser.")
            print("For a native window: pip install pywebview")

    # Browser fallback.
    srv.start_in_thread()
    webbrowser.open(srv.url)
    print("Opened in your browser. Press Ctrl+C to stop.")
    try:
        import time
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
