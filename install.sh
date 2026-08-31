#!/usr/bin/env bash
set -euo pipefail

REPO="yourname/mdlive"
INSTALL_DIR="${MDLIVE_INSTALL_DIR:-$HOME/.local/bin}"

info()  { printf '\033[1;34m==>\033[0m %s\n' "$1"; }
error() { printf '\033[1;31mError:\033[0m %s\n' "$1" >&2; exit 1; }

OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"

case "$ARCH" in
  x86_64|amd64) ARCH="x86_64" ;;
  aarch64|arm64) ARCH="arm64" ;;
  *) error "Unsupported architecture: $ARCH" ;;
esac

case "$OS" in
  linux) OS="linux" ;;
  darwin) OS="darwin" ;;
  *) error "Unsupported OS: $OS" ;;
esac

ASSET="mdlive-${OS}-${ARCH}"
URL="https://github.com/${REPO}/releases/download/latest/${ASSET}"

mkdir -p "$INSTALL_DIR"

info "Downloading ${ASSET}..."
if ! curl -fsSL "$URL" -o "$INSTALL_DIR/mdlive"; then
  error "Failed to download binary for ${OS}/${ARCH} from ${URL}"
fi

chmod +x "$INSTALL_DIR/mdlive"
info "Installed to $INSTALL_DIR/mdlive"

case ":$PATH:" in
  *":$INSTALL_DIR:"*) ;;
  *)
    info "Add this to your shell profile (e.g. ~/.bashrc):"
    echo "  export PATH=\"$INSTALL_DIR:\$PATH\""
    ;;
esac

info "Run it with: mdlive yourfile.md"
