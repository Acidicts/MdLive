"""
Inline-level Markdown parsing: bold, italic, inline code, strikethrough,
links, images, and task-list checkboxes. Escapes raw HTML by default,
except for the checkbox markup this module itself emits.

Parses recursively so formatting nests correctly inside list items, table
cells, blockquotes, etc. - anywhere render_inline() is called on text.
"""
import html
import re

# Order matters: code spans are matched first (their contents must not be
# interpreted as further markdown), then images (must be checked before
# links, since image syntax is "!" + link syntax), then links, then the
# remaining emphasis/strikethrough forms.
_CODE_SPAN_RE = re.compile(r'(`+)(.+?)\1')
_IMAGE_RE = re.compile(r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)')
_LINK_RE = re.compile(r'\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)')
_BOLD_ITALIC_RE = re.compile(r'(\*\*\*|___)(.+?)\1')
_BOLD_RE = re.compile(r'(\*\*|__)(.+?)\1')
# Asterisk italics: no boundary restriction (can trigger mid-word).
_ITALIC_ASTERISK_RE = re.compile(r'\*([^*\s](?:[^*]*[^*\s])?)\*')
# Underscore italics: require a non-word-char (or string start/end) on both
# sides, so "snake_case_name" is not partially italicized - standard
# Markdown convention.
_ITALIC_UNDERSCORE_RE = re.compile(r'(?<![\w])_([^_\s](?:[^_]*[^_\s])?)_(?![\w])')
_STRIKE_RE = re.compile(r'~~(.+?)~~')
_CHECKBOX_RE = re.compile(r'^\[([ xX])\]\s+')
_AUTOLINK_RE = re.compile(r'<(https?://[^\s>]+)>')


def _escape(text: str) -> str:
    return html.escape(text, quote=False)


def escape_text(text: str) -> str:
    """Public wrapper for HTML-escaping raw text (used for code block content)."""
    return _escape(text)


def extract_leading_checkbox(text: str):
    """
    If text starts with a task-list marker ("[ ] " / "[x] " / "[X] "),
    return (checked: bool, remaining_text). Otherwise return None.

    This is applied once, per list item, before general inline parsing -
    it's a structural marker (like a list bullet), not an inline span, so
    it's intentionally not part of render_inline()'s regex chain.
    """
    match = _CHECKBOX_RE.match(text)
    if not match:
        return None
    checked = match.group(1).lower() == "x"
    return checked, text[match.end():]


def render_inline(text: str) -> str:
    """Render inline Markdown spans in `text` to an HTML string."""
    return _render_span(text)


def _render_span(text: str) -> str:
    # Protect already-built HTML (code spans, links, images, autolinks) as
    # placeholders so the later escape pass and emphasis regexes never see
    # or mangle their generated tags.
    placeholders = []

    def stash(rendered_html: str) -> str:
        placeholders.append(rendered_html)
        return f'\x00{len(placeholders) - 1}\x00'

    def stash_code(match):
        content = _escape(match.group(2).strip())
        return stash(f'<code>{content}</code>')

    text = _CODE_SPAN_RE.sub(stash_code, text)

    def autolink(match):
        url = match.group(1)
        safe_url = _escape(url)
        return stash(f'<a href="{safe_url}">{safe_url}</a>')

    text = _AUTOLINK_RE.sub(autolink, text)

    # Images before links (image syntax is a superset prefix of link syntax).
    def image(match):
        alt, src, title = match.group(1), match.group(2), match.group(3)
        title_attr = f' title="{_escape(title)}"' if title else ""
        return stash(f'<img src="{_escape(src)}" alt="{_escape(alt)}"{title_attr}>')

    text = _IMAGE_RE.sub(image, text)

    def link(match):
        label, href, title = match.group(1), match.group(2), match.group(3)
        title_attr = f' title="{_escape(title)}"' if title else ""
        # Link label text can itself contain emphasis, so recurse.
        inner = _render_span(label)
        return stash(f'<a href="{_escape(href)}"{title_attr}>{inner}</a>')

    text = _LINK_RE.sub(link, text)

    # Escape any remaining raw text (everything that isn't already-built
    # HTML stashed above). We do this now, before emphasis markers are
    # converted to tags, so a literal "<" typed by the user doesn't become
    # part of an HTML tag.
    text = _escape_outside_placeholders(text, placeholders)

    # Bold+italic, then bold, then italic - longest marker sequences first
    # so "**bold**" isn't partially consumed by the italic pattern.
    text = _BOLD_ITALIC_RE.sub(lambda m: f'<strong><em>{m.group(2)}</em></strong>', text)
    text = _BOLD_RE.sub(lambda m: f'<strong>{m.group(2)}</strong>', text)
    # Asterisk italics can trigger mid-word; underscore italics require a
    # word boundary on both sides (standard Markdown convention - otherwise
    # "snake_case_name" would get partially italicized).
    text = _ITALIC_ASTERISK_RE.sub(lambda m: f'<em>{m.group(1)}</em>', text)
    text = _ITALIC_UNDERSCORE_RE.sub(lambda m: f'<em>{m.group(1)}</em>', text)
    text = _STRIKE_RE.sub(lambda m: f'<del>{m.group(1)}</del>', text)

    # Restore stashed HTML.
    for i, rendered_html in enumerate(placeholders):
        text = text.replace(f'\x00{i}\x00', rendered_html)

    return text


def _escape_outside_placeholders(text: str, placeholders) -> str:
    """Escape HTML-special characters, but leave \\x00N\\x00 placeholders
    (already-rendered code/link/image/autolink spans) untouched."""
    if not placeholders:
        return _escape(text)
    parts = re.split(r'(\x00\d+\x00)', text)
    out = []
    for part in parts:
        if re.fullmatch(r'\x00\d+\x00', part):
            out.append(part)
        else:
            out.append(_escape(part))
    return "".join(out)
