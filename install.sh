#!/usr/bin/env bash
set -euo pipefail

REPO="Acidicts/MdLive"
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

add_to_path() {
  local line="export PATH=\"$INSTALL_DIR:\$PATH\""
  local profile=""

  case "$(basename "${SHELL:-/bin/bash}")" in
    zsh)  profile="$HOME/.zshrc" ;;
    fish) profile="$HOME/.config/fish/config.fish"; line="set -gx PATH $INSTALL_DIR \$PATH" ;;
    bash) profile="$HOME/.bashrc" ;;
    *)    profile="$HOME/.profile" ;;
  esac

  if [ -f "$profile" ] && grep -qF "$INSTALL_DIR" "$profile"; then
    info "PATH already configured in $profile"
  else
    mkdir -p "$(dirname "$profile")"
    printf '\n# mdlive\n%s\n' "$line" >> "$profile"
    info "Added $INSTALL_DIR to PATH in $profile"
  fi

  info "Run: source $profile"
}

add_to_path

info "Run it with: mdlive yourfile.md"
info "Other commands: mdlive add <file> <path>  |  mdlive remove <path>  |  mdlive --help"
