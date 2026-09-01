"""
Block-level Markdown parsing.

Builds a tree of block nodes (headings, paragraphs, lists, list items,
blockquotes, code fences, tables, horizontal rules) via a real recursive
parser operating on indentation and block boundaries - not per-line regex
substitution. This is what makes nesting (lists inside lists, lists inside
blockquotes, etc.) correct at arbitrary depth: a list item's content is
parsed by recursing into this same block parser on its own indented
sub-lines, rather than pattern-matching each line independently.
"""
import re

from mdlive.md_inline import extract_leading_checkbox, render_inline, escape_text

_ATX_HEADING_RE = re.compile(r'^(#{1,6})\s+(.*?)\s*#*\s*$')
_FENCE_RE = re.compile(r'^(\s*)(```|~~~)(.*)$')
_HR_RE = re.compile(r'^\s*([-*_])\s*(?:\1\s*){2,}$')
_UL_ITEM_RE = re.compile(r'^(\s*)([-*+])\s+(.*)$')
_OL_ITEM_RE = re.compile(r'^(\s*)(\d+)[.)]\s+(.*)$')
_BLOCKQUOTE_RE = re.compile(r'^(\s*)>\s?(.*)$')
_TABLE_SEP_RE = re.compile(r'^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$')


class Node:
    __slots__ = ("kind", "attrs", "children", "text")

    def __init__(self, kind, text=None, **attrs):
        self.kind = kind
        self.text = text
        self.attrs = attrs
        self.children = []

    def __repr__(self):
        return f"Node({self.kind!r}, text={self.text!r}, attrs={self.attrs}, children={len(self.children)})"


def parse(text: str) -> Node:
    """Parse a full Markdown document into a root Node tree."""
    lines = text.split("\n")
    root = Node("root")
    _parse_blocks(lines, 0, len(lines), root)
    return root


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _parse_blocks(lines, start, end, parent):
    i = start
    while i < end:
        line = lines[i]

        if line.strip() == "":
            i += 1
            continue

        # Fenced code block.
        fence_match = _FENCE_RE.match(line)
        if fence_match:
            indent, fence_marker, info = fence_match.groups()
            lang = info.strip()
            code_lines = []
            j = i + 1
            closing = re.compile(rf'^{re.escape(indent)}{re.escape(fence_marker)}\s*$')
            while j < end and not closing.match(lines[j]):
                code_lines.append(lines[j])
                j += 1
            node = Node("code", text="\n".join(code_lines), lang=lang)
            parent.children.append(node)
            i = j + 1
            continue

        # ATX heading.
        heading_match = _ATX_HEADING_RE.match(line)
        if heading_match:
            level = len(heading_match.group(1))
            node = Node("heading", text=heading_match.group(2), level=level)
            parent.children.append(node)
            i += 1
            continue

        # Horizontal rule (checked before list items, since "---" could
        # otherwise be mistaken for something else, and before setext
        # headings below expect a preceding paragraph line).
        if _HR_RE.match(line) and line.strip() not in ("-", "*", "_"):
            parent.children.append(Node("hr"))
            i += 1
            continue

        # Blockquote: gather contiguous quoted lines (allowing "lazy"
        # continuation lines with no ">"), strip one leading "> " per line,
        # then recursively parse the dedented content as its own block
        # sequence - this is what makes nested blockquotes/lists inside
        # a blockquote work.
        bq_match = _BLOCKQUOTE_RE.match(line)
        if bq_match:
            quoted_lines = []
            j = i
            while j < end:
                m = _BLOCKQUOTE_RE.match(lines[j])
                if m:
                    quoted_lines.append(m.group(2))
                    j += 1
                elif lines[j].strip() != "" and quoted_lines:
                    # Lazy continuation of the quote paragraph.
                    quoted_lines.append(lines[j])
                    j += 1
                else:
                    break
            node = Node("blockquote")
            _parse_blocks(quoted_lines, 0, len(quoted_lines), node)
            parent.children.append(node)
            i = j
            continue

        # Table: a header row followed by a separator row of the form
        # |---|---| (or without leading/trailing pipes).
        if "|" in line and i + 1 < end and _TABLE_SEP_RE.match(lines[i + 1]):
            header_cells = _split_table_row(line)
            align_cells = _split_table_row(lines[i + 1])
            aligns = [_cell_alignment(c) for c in align_cells]
            body_rows = []
            j = i + 2
            while j < end and "|" in lines[j] and lines[j].strip() != "":
                body_rows.append(_split_table_row(lines[j]))
                j += 1
            node = Node("table", header=header_cells, aligns=aligns, rows=body_rows)
            parent.children.append(node)
            i = j
            continue

        # List (ordered or unordered). Gather all contiguous lines that
        # belong to this specific list - same indentation AND same marker
        # type (ordered vs unordered), since a "1." list and a "-" list at
        # the same indent are two different lists, not one continuing -
        # then split into items and recurse into each item's own content
        # as its own block sequence. This recursion is what gives
        # arbitrary-depth nesting for free: a sub-list four levels deep is
        # parsed by the same _parse_blocks function operating on that
        # item's indented slice of lines, with no dependency on how deep
        # we already are.
        ul_match = _UL_ITEM_RE.match(line)
        ol_match = _OL_ITEM_RE.match(line)
        if ul_match or ol_match:
            list_indent = len(ul_match.group(1)) if ul_match else len(ol_match.group(1))
            ordered = ol_match is not None
            list_end = _find_list_end(lines, i, end, list_indent, ordered)
            list_node = Node("list", ordered=ordered)
            _parse_list_items(lines, i, list_end, list_indent, ordered, list_node)
            parent.children.append(list_node)
            i = list_end
            continue

        # Paragraph: gather contiguous non-blank, non-special lines. A
        # single-line paragraph immediately followed by a "===" or "---"
        # underline is a setext heading (h1/h2 respectively) rather than a
        # literal paragraph - handled after gathering, below.
        j = i
        para_lines = []
        while j < end and lines[j].strip() != "":
            l = lines[j]
            if (
                _FENCE_RE.match(l)
                or _ATX_HEADING_RE.match(l)
                or _UL_ITEM_RE.match(l)
                or _OL_ITEM_RE.match(l)
                or _BLOCKQUOTE_RE.match(l)
                or (_HR_RE.match(l) and l.strip() not in ("-", "*", "_"))
                # Stop before a setext underline so it isn't swallowed
                # into this paragraph's text - it terminates the paragraph
                # and (per the check above, re-run on this shorter
                # para_lines) is only actually consumed as a heading when
                # para_lines has exactly one line.
                or (
                    para_lines
                    and (re.fullmatch(r'=+', l.strip()) or re.fullmatch(r'-+', l.strip()))
                )
            ):
                break
            para_lines.append(l.strip())
            j += 1
        if para_lines:
            if (
                len(para_lines) == 1
                and j < end
                and re.fullmatch(r'=+', lines[j].strip())
            ):
                parent.children.append(Node("heading", text=para_lines[0], level=1))
                i = j + 1
            elif (
                len(para_lines) == 1
                and j < end
                and re.fullmatch(r'-+', lines[j].strip())
            ):
                parent.children.append(Node("heading", text=para_lines[0], level=2))
                i = j + 1
            else:
                parent.children.append(Node("paragraph", text=" ".join(para_lines)))
                i = j
        else:
            i += 1


def _is_item_marker(line: str, ordered: bool):
    """Return the regex match for `line` if it's a list-item marker of the
    given type (ordered/unordered), else None. Used to distinguish "this
    is the same list continuing" from "this is a different list starting"."""
    if ordered:
        return _OL_ITEM_RE.match(line)
    return _UL_ITEM_RE.match(line)


def _find_list_end(lines, start, end, list_indent, ordered):
    """
    Find the exclusive end index of the contiguous run of lines belonging
    to a single list: same indentation AND same marker type (ordered vs
    unordered) as the list's first item. A change in marker type at the
    same indent starts a new, separate list (e.g. a "-" list immediately
    followed by a "1." list at the same indent are two different lists),
    matching standard Markdown/CommonMark behavior.
    """
    j = start
    while j < end:
        cur = lines[j]
        if cur.strip() == "":
            # Blank line(s): the list continues past them only if the next
            # non-blank line is still part of this same list (same marker
            # type at this indent) or is a deeper-indented continuation.
            k = j + 1
            while k < end and lines[k].strip() == "":
                k += 1
            if k >= end:
                break
            nxt_indent = _indent_of(lines[k])
            if nxt_indent > list_indent:
                j = k
                continue
            if nxt_indent == list_indent and _is_item_marker(lines[k], ordered):
                j = k
                continue
            break

        cur_indent = _indent_of(cur)
        if cur_indent < list_indent:
            break
        if cur_indent == list_indent:
            if _is_item_marker(cur, ordered):
                j += 1
                continue
            # Same indent, but not a marker of this list's type (either
            # plain text continuation of the current item, or a different
            # list type starting - the latter case is handled by simply
            # not matching _is_item_marker, so we stop here and let the
            # caller re-enter block parsing, which will start a fresh list
            # detection for the new marker type).
            if _is_item_marker(cur, not ordered):
                break
            j += 1
            continue
        # cur_indent > list_indent: continuation content of the current
        # item (nested list, code block, extra paragraph, etc.).
        j += 1
    return j


def _parse_list_items(lines, start, end, list_indent, ordered, list_node):
    """Split the [start, end) line range (already known to belong to one
    list) into individual items, and recursively parse each item's own
    content."""
    j = start
    while j < end:
        line = lines[j]
        if line.strip() == "":
            j += 1
            continue

        match = _is_item_marker(line, ordered)
        if not match:
            # Lazy-continuation line belonging to the previous item's
            # trailing paragraph.
            if list_node.children:
                list_node.children[-1].children.append(
                    Node("paragraph", text=line.strip())
                )
            j += 1
            continue

        marker_text = match.group(3)
        item_lines = [marker_text]
        k = j + 1
        while k < end:
            nxt = lines[k]
            if nxt.strip() == "":
                # Peek past the blank line: if the next non-blank line is
                # a new item marker at this list's indent, the blank line
                # ends this item's content (not a continuation).
                m = k + 1
                while m < end and lines[m].strip() == "":
                    m += 1
                if m < end and _indent_of(lines[m]) <= list_indent and _is_item_marker(lines[m], ordered):
                    break
                item_lines.append("")
                k += 1
                continue
            nxt_indent = _indent_of(nxt)
            if nxt_indent > list_indent:
                # Dedent by exactly the marker width so nested block
                # parsing sees clean, zero-based indentation.
                dedent = list_indent + 2
                item_lines.append(nxt[dedent:] if len(nxt) > dedent else nxt.lstrip(" "))
                k += 1
            elif nxt_indent == list_indent and not _is_item_marker(nxt, ordered):
                if _is_item_marker(nxt, not ordered):
                    break
                item_lines.append(nxt.strip())
                k += 1
            else:
                break
        item_node = Node("list_item")
        _parse_list_item(item_lines, item_node)
        list_node.children.append(item_node)
        j = k


def _parse_list_item(item_lines, item_node):
    """
    Parse a single list item's content lines. The first line may carry a
    leading task-list checkbox marker ("[ ] " / "[x] "), which is detected
    and attached to the item node itself (not treated as inline text), so
    it renders as a real <input type="checkbox"> regardless of how deep
    this item is nested or whether it has its own child list - this is
    the specific bug this custom renderer exists to fix.
    """
    if item_lines:
        checkbox = extract_leading_checkbox(item_lines[0])
        if checkbox is not None:
            checked, remainder = checkbox
            item_node.attrs["checked"] = checked
            item_node.attrs["is_task"] = True
            item_lines = [remainder] + item_lines[1:]
    _parse_blocks(item_lines, 0, len(item_lines), item_node)


def _split_table_row(line: str):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    # Split on unescaped pipes.
    cells = re.split(r'(?<!\\)\|', line)
    return [c.strip().replace(r'\|', '|') for c in cells]


def _cell_alignment(sep_cell: str):
    sep_cell = sep_cell.strip()
    left = sep_cell.startswith(":")
    right = sep_cell.endswith(":")
    if left and right:
        return "center"
    if right:
        return "right"
    if left:
        return "left"
    return None


def render_html(node: Node) -> str:
    """Render a parsed block tree (as returned by parse()) to an HTML string."""
    return _render_node(node)


def _render_node(node: Node) -> str:
    if node.kind == "root":
        return "".join(_render_node(c) for c in node.children)

    if node.kind == "heading":
        slug = _slugify(node.text)
        return f'<h{node.attrs["level"]} id="{slug}">{render_inline(node.text)}</h{node.attrs["level"]}>\n'

    if node.kind == "paragraph":
        return f'<p>{render_inline(node.text)}</p>\n'

    if node.kind == "hr":
        return '<hr>\n'

    if node.kind == "code":
        lang = node.attrs.get("lang") or ""
        lang_class = f' class="language-{lang}"' if lang else ""
        escaped = escape_text(node.text)
        return f'<pre><code{lang_class}>{escaped}\n</code></pre>\n'

    if node.kind == "blockquote":
        inner = "".join(_render_node(c) for c in node.children)
        return f'<blockquote>\n{inner}</blockquote>\n'

    if node.kind == "table":
        return _render_table(node)

    if node.kind == "list":
        tag = "ol" if node.attrs.get("ordered") else "ul"
        inner = "".join(_render_node(c) for c in node.children)
        return f'<{tag}>\n{inner}</{tag}>\n'

    if node.kind == "list_item":
        # "Tight" list rendering: if this item's content is just a leading
        # paragraph (optionally followed by nested sub-blocks like a child
        # list), render that first paragraph as plain inline text instead
        # of wrapping it in <p> - this matches how GitHub and most
        # Markdown renderers display lists (no extra paragraph spacing on
        # the item's own line, even when it has a nested sub-list), while
        # still preserving <p> wrapping for genuinely separate paragraphs
        # within the same item (loose-list content).
        if node.children and node.children[0].kind == "paragraph":
            first_text = node.children[0].text
            rest = node.children[1:]
            inner = render_inline(first_text) + "".join(_render_node(c) for c in rest)
        else:
            inner = "".join(_render_node(c) for c in node.children)

        if node.attrs.get("is_task"):
            checked_attr = " checked" if node.attrs.get("checked") else ""
            checkbox_html = f'<input type="checkbox" disabled{checked_attr}> '
            # Insert the checkbox at the very start of the item's rendered
            # content, whether that content is a single inline paragraph
            # or a paragraph followed by a nested sub-list - it always
            # attaches to the item itself, not to a specific descendant,
            # so it survives at any nesting depth.
            inner = checkbox_html + inner
        return f'<li>{inner}</li>\n'

    return ""


def _render_table(node: Node) -> str:
    def cell_html(cell_text, tag, align):
        style = f' style="text-align:{align}"' if align else ""
        return f'<{tag}{style}>{render_inline(cell_text)}</{tag}>'

    aligns = node.attrs["aligns"]
    header_cells = "".join(
        cell_html(c, "th", aligns[idx] if idx < len(aligns) else None)
        for idx, c in enumerate(node.attrs["header"])
    )
    body_rows_html = ""
    for row in node.attrs["rows"]:
        cells = "".join(
            cell_html(c, "td", aligns[idx] if idx < len(aligns) else None)
            for idx, c in enumerate(row)
        )
        body_rows_html += f'<tr>{cells}</tr>\n'
    return (
        '<table>\n<thead>\n'
        f'<tr>{header_cells}</tr>\n'
        '</thead>\n<tbody>\n'
        f'{body_rows_html}'
        '</tbody>\n</table>\n'
    )


_slug_seen = {}


def _slugify(text: str) -> str:
    base = re.sub(r'[^\w\s-]', '', text.strip().lower())
    base = re.sub(r'[\s]+', '-', base)
    return base or "section"


def render(text: str) -> str:
    """Parse and render a full Markdown document to HTML in one call."""
    _slug_seen.clear()
    tree = parse(text)
    return _render_node(tree)
