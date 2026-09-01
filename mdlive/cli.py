import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

REPO = "Acidicts/MdLive"
RELEASE_URL_TEMPLATE = "https://github.com/{repo}/releases/download/latest/{asset}"
DEFAULT_PORT = 8000


def _detect_asset_name() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "linux":
        os_name = "linux"
    elif system == "darwin":
        os_name = "darwin"
    else:
        print(f"Unsupported OS for auto-update: {system}", file=sys.stderr)
        sys.exit(1)

    if machine in ("x86_64", "amd64"):
        arch = "x86_64"
    elif machine in ("aarch64", "arm64"):
        arch = "arm64"
    else:
        print(f"Unsupported architecture for auto-update: {machine}", file=sys.stderr)
        sys.exit(1)

    return f"mdlive-{os_name}-{arch}"


def _current_binary_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    which = shutil.which("mdlive")
    if which:
        return Path(which).resolve()
    return Path(sys.argv[0]).resolve()


def cmd_update(args):
    current_path = _current_binary_path()
    print(f"Current binary: {current_path}")

    if not current_path.exists() or not os.access(current_path.parent, os.W_OK):
        print(
            f"Cannot write to {current_path.parent}. "
            "Try running with elevated permissions, or reinstall manually with:\n"
            f"  curl -fsSL https://raw.githubusercontent.com/{REPO}/main/install.sh | bash",
            file=sys.stderr,
        )
        sys.exit(1)

    asset_name = _detect_asset_name()
    url = RELEASE_URL_TEMPLATE.format(repo=REPO, asset=asset_name)
    print(f"Downloading latest release ({asset_name})...")

    tmp_fd, tmp_path_str = tempfile.mkstemp(
        prefix="mdlive-update-", dir=str(current_path.parent)
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(tmp_fd, "wb") as tmp_file:
            with urllib.request.urlopen(url, timeout=30) as response:
                if response.status != 200:
                    print(f"Download failed: HTTP {response.status}", file=sys.stderr)
                    sys.exit(1)
                shutil.copyfileobj(response, tmp_file)

        tmp_path.chmod(0o755)

        result = subprocess.run(
            [str(tmp_path), "--help"], capture_output=True, timeout=10
        )
        if result.returncode != 0:
            print("Downloaded binary failed to run. Aborting update.", file=sys.stderr)
            sys.exit(1)

        tmp_path.replace(current_path)
        print(f"Updated mdlive at {current_path}")
    except Exception as exc:
        print(f"Update failed: {exc}", file=sys.stderr)
        tmp_path.unlink(missing_ok=True)
        sys.exit(1)


def cmd_uninstall(args):
    current_path = _current_binary_path()

    if not args.yes:
        answer = input(f"Remove {current_path}? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted.")
            return

    try:
        current_path.unlink()
        print(f"Removed {current_path}")
    except FileNotFoundError:
        print(f"{current_path} was already removed.")
    except PermissionError:
        print(
            f"Permission denied removing {current_path}. "
            f"Try: rm {current_path}",
            file=sys.stderr,
        )
        sys.exit(1)


def cmd_serve(args):
    from mdlive.server import MDLiveServer

    server = MDLiveServer(args.file)

    if args.no_tui or not sys.stdout.isatty():
        import uvicorn

        uvicorn.run(server.app, host=args.host, port=args.port, log_level="info")
    else:
        from mdlive.tui import MDLiveTUI

        tui = MDLiveTUI(server, host=args.host, port=args.port)
        tui.run()


def _api_request(method: str, port: int, path: str, data: dict | None = None):
    url = f"http://127.0.0.1:{port}{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            err = json.loads(body)
            print(f"Error: {err.get('error', body)}", file=sys.stderr)
        except Exception:
            print(f"Error: HTTP {e.code} - {body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError:
        print(
            f"Error: No mdlive server running on port {port}. "
            "Start one first with: mdlive <file>",
            file=sys.stderr,
        )
        sys.exit(1)


def cmd_add(args):
    result = _api_request(
        "POST",
        args.port,
        "/api/add",
        {"file": args.file, "path": args.url_path},
    )
    print(f"Added {result['file']} at {result['path']}")


def cmd_remove(args):
    result = _api_request(
        "DELETE",
        args.port,
        "/api/remove",
        {"path": args.url_path},
    )
    print(f"Removed {result['path']}")


HELP_TEXT = """\
mdlive - serve markdown files with live reload

Usage:
  mdlive <file>                   Start server, serve <file> at /
  mdlive add <file> <path>        Add <file> at /<path>
  mdlive remove <path>            Remove /<path>
  mdlive update                   Update mdlive binary
  mdlive uninstall                Remove the mdlive binary

Options:
  --no-tui                        Run without the TUI (headless/CI)
"""


def main():
    argv = sys.argv[1:]

    if not argv or argv[0] in ("-h", "--help"):
        print(HELP_TEXT)
        return

    subcommand = argv[0]

    if subcommand == "update":
        p = argparse.ArgumentParser(prog="mdlive update")
        cmd_update(p.parse_args(argv[1:]))
        return

    if subcommand == "uninstall":
        p = argparse.ArgumentParser(prog="mdlive uninstall")
        p.add_argument("-y", "--yes", action="store_true")
        cmd_uninstall(p.parse_args(argv[1:]))
        return

    if subcommand == "add":
        p = argparse.ArgumentParser(
            prog="mdlive add",
            description="Add a markdown file to the running server at a URL path",
        )
        p.add_argument("file", help="Path to the .md file")
        p.add_argument("url_path", help="URL path (e.g. 'docs' -> /docs)")
        p.add_argument("--port", type=int, default=DEFAULT_PORT)
        cmd_add(p.parse_args(argv[1:]))
        return

    if subcommand == "remove":
        p = argparse.ArgumentParser(
            prog="mdlive remove",
            description="Remove a URL path from the running server",
        )
        p.add_argument("url_path", help="URL path to remove (e.g. 'docs' -> /docs)")
        p.add_argument("--port", type=int, default=DEFAULT_PORT)
        cmd_remove(p.parse_args(argv[1:]))
        return

    # Default: serve <file>
    p = argparse.ArgumentParser(
        prog="mdlive",
        description="Serve a Markdown file with live reload",
    )
    p.add_argument("file", help="Path to the .md file")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--no-tui", action="store_true", help="Run without the TUI (headless)")
    args = p.parse_args(argv)
    cmd_serve(args)


if __name__ == "__main__":
    main()
