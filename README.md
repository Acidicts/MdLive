# mdlive

Serve a Markdown file as live-updating HTML over a local port.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/Acidicts/MdLive/main/install.sh | bash
```

Or via pip, for development:

```bash
pip install -e .
```

## Usage

```bash
mdlive notes.md --port 8000
```

Open `http://127.0.0.1:8000`. Edit `notes.md` and the page reloads automatically.

## Markdown renderer

mdlive uses its own built-in Markdown renderer (`mdlive/md_block.py` + `mdlive/md_inline.py`) instead of a third-party library. It's a real two-pass parser - block structure first, then inline spans - so nesting (lists inside lists, checklists inside lists, blockquotes inside lists, etc.) is handled correctly at any depth by construction, rather than by pattern-matching that can silently break on deeper nesting.

Supported:

- Headings (`#` through `######`, plus setext `===`/`---` underline style)
- Paragraphs, blockquotes (nestable, with lazy continuation lines)
- Ordered and unordered lists, nestable to any depth, tight or loose
- GitHub-style task lists (`- [ ]` / `- [x]` / `- [X]`) as real, correctly-checked `<input type="checkbox">` elements at any nesting depth
- Fenced code blocks (` ``` ` / `~~~`) with language class for syntax highlighters
- Tables with column alignment (`:---`, `:---:`, `---:`)
- Horizontal rules (`---`, `***`, `___`)
- Bold, italic, bold+italic, strikethrough, inline code, links, images, autolinks (`<https://...>`)
- HTML-escaping throughout, so raw HTML/script content in a document renders as visible text rather than executing

Not supported (yet): reference-style links (`[text][ref]`), footnotes, definition lists, HTML block passthrough. These weren't needed for the current use case; contributions welcome.

## Updating and uninstalling

```bash
mdlive update
```

Downloads the latest release binary and replaces the currently running one in place. Works from any Linux/macOS install location; no need to re-run `install.sh`.

```bash
mdlive uninstall
```

Removes the mdlive binary. Prompts for confirmation; pass `-y`/`--yes` to skip the prompt (e.g. `mdlive uninstall -y`).

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
