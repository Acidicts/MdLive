# mdlive

Serve a Markdown file as live-updating HTML over a local port.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/yourname/mdlive/main/install.sh | bash
```

(Replace `yourname/mdlive` in `install.sh` and this README with your actual GitHub repo.)

Or via pip, for development:

```bash
pip install -e .
```

## Usage

```bash
mdlive notes.md --port 8000
```

Open `http://127.0.0.1:8000`. Edit `notes.md` and the page reloads automatically.

## Publishing releases (for maintainers)

Every push to `main` triggers `.github/workflows/release.yml`, which:

1. Builds a standalone binary for Linux (x86_64, arm64) and macOS (x86_64, arm64) via PyInstaller.
2. Publishes/updates a rolling GitHub release tagged `latest` with those binaries attached.

`install.sh` always pulls from that `latest` tag, so the one-liner always gets the newest build from `main`.

### Setup checklist before first use

- [ ] Push this repo to GitHub under your account/org.
- [ ] Update `REPO="yourname/mdlive"` in `install.sh` to match.
- [ ] Update the raw URL in this README's install command to match.
- [ ] Push to `main` (or run the workflow manually via "Run workflow") to trigger the first build.
- [ ] Confirm the `latest` release appears under the repo's Releases tab with 4 binary assets attached.

### Local build/test before pushing

```bash
pip install -e ".[dev]"
pyinstaller mdlive.spec
./dist/mdlive --help
```
