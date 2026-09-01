import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

import uvicorn

from mdlive.server import MDLiveServer

REPO = "Acidicts/MdLive"
RELEASE_URL_TEMPLATE = "https://github.com/{repo}/releases/download/latest/{asset}"


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
    """
    Resolve the path to the actual installed mdlive executable, not the
    PyInstaller-extracted temp directory (sys.executable inside a frozen
    binary points at the real launcher, so this is safe for both frozen
    and non-frozen (pip-installed) runs).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    # Running via `python -m` or pip-installed console script: fall back to
    # locating the mdlive script on PATH.
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

        # Sanity check the downloaded binary actually runs before replacing
        # the current one.
        result = subprocess.run(
            [str(tmp_path), "--help"], capture_output=True, timeout=10
        )
        if result.returncode != 0:
            print("Downloaded binary failed to run. Aborting update.", file=sys.stderr)
            sys.exit(1)

        # Atomic replace. On Linux/macOS this works even while the current
        # process is executing from current_path, since the running process
        # holds its own inode reference.
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
    server = MDLiveServer(args.file)
    uvicorn.run(server.app, host=args.host, port=args.port, log_level="info")


def main():
    # Handle update/uninstall as reserved subcommands before argparse sees
    # them, so a file literally named "update" or "uninstall" in the CWD
    # can never be misinterpreted as the subcommand (argparse's positional +
    # subparser interaction is ambiguous in exactly that case).
    if len(sys.argv) > 1 and sys.argv[1] == "update":
        update_parser = argparse.ArgumentParser(prog="mdlive update")
        cmd_update(update_parser.parse_args(sys.argv[2:]))
        return

    if len(sys.argv) > 1 and sys.argv[1] == "uninstall":
        uninstall_parser = argparse.ArgumentParser(prog="mdlive uninstall")
        uninstall_parser.add_argument(
            "-y", "--yes", action="store_true", help="Skip the confirmation prompt"
        )
        cmd_uninstall(uninstall_parser.parse_args(sys.argv[2:]))
        return

    parser = argparse.ArgumentParser(
        description=(
            "Serve a Markdown file with live reload.\n\n"
            "Other commands:\n"
            "  mdlive update      Update mdlive to the latest release\n"
            "  mdlive uninstall   Remove the mdlive binary"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("file", help="Path to the .md file")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    cmd_serve(args)


if __name__ == "__main__":
    main()

