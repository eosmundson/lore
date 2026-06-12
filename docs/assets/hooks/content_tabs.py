"""mkdocs hook: render comment-delimited tab groups as Material content tabs.

Doc sources author per-platform/per-variant tabs in a GitHub-clean
convention -- `<!-- tabs:start -->`, then `<!-- tab -->` plus a bold title
line per tab, then `<!-- tabs:end -->` -- because raw pymdownx.tabbed syntax
(`=== "..."` with four-space-indented bodies) renders on GitHub as literal
text and unhighlighted backticks. This hook rewrites each well-formed group
into pymdownx.tabbed syntax before Markdown conversion: real tabs on the
site, clean Markdown on GitHub.

Each group is buffered and only converted once complete and well formed; a
malformed group is emitted verbatim with a warning, which `mkdocs build
--strict` treats as fatal. Markers inside code fences are content, never
markers -- format.md documents this convention inside fenced examples.

Convention reference:
docs/developing/doc-standards/canon/format.md#content-tabs
"""

import logging
import re

log = logging.getLogger("mkdocs.hooks.content_tabs")

TABS_START = "<!-- tabs:start -->"
TAB = "<!-- tab -->"
TABS_END = "<!-- tabs:end -->"

TITLE = re.compile(r"\*\*(.+?)\*\*")
FENCE_OPEN = re.compile(r"(`{3,}|~{3,})")


def on_page_markdown(markdown, *, page, **kwargs):
    """Rewrite comment-delimited tab groups into pymdownx.tabbed syntax."""
    if TABS_START not in markdown:
        return markdown
    return _transform(markdown.split("\n"), page.file.src_uri)


def _indent(line):
    return line[: len(line) - len(line.lstrip())]


def _scan_fence(stripped, fence):
    """Track fenced-code state; returns the fence state after this line."""
    if fence is None:
        m = FENCE_OPEN.match(stripped)
        if m:
            return (m.group(1)[0], len(m.group(1)))
        return None
    char, length = fence
    if stripped and set(stripped) == {char} and len(stripped) >= length:
        return None
    return fence


def _transform(lines, src):
    out = []
    fence = None
    group = None  # buffered source lines of the open group, or None
    indent = ""
    start = 0  # 1-based line number of the open group's tabs:start

    for num, line in enumerate(lines, start=1):
        stripped = line.strip()
        in_fence = fence is not None
        fence = _scan_fence(stripped, fence)

        if group is None:
            if not in_fence and stripped == TABS_START:
                group = [line]
                indent = _indent(line)
                start = num
            else:
                out.append(line)
        elif not in_fence and stripped == TABS_START:
            _warn(src, num, "nested '<!-- tabs:start -->'")
            out.extend(group)
            out.append(line)
            group = None
        elif not in_fence and stripped == TABS_END:
            group.append(line)
            if _indent(line) != indent:
                _warn(src, num, "'<!-- tabs:end -->' not at the group's indentation")
                out.extend(group)
            else:
                out.extend(_render_group(group, indent, src, start))
            group = None
        else:
            group.append(line)

    if group is not None:
        _warn(src, start, "unclosed '<!-- tabs:start -->'")
        out.extend(group)
    return "\n".join(out)


def _render_group(group, indent, src, start):
    """Convert one buffered group, or return it verbatim if malformed."""
    tabs = []  # (title, content-lines) pairs
    fence = None
    content = None  # current tab's content list; None before the first tab
    want_title = False
    tab_line = start  # line number of the most recent <!-- tab --> marker

    for offset, line in enumerate(group[1:-1], start=1):
        stripped = line.strip()
        in_fence = fence is not None
        fence = _scan_fence(stripped, fence)
        num = start + offset

        if not in_fence and stripped == TAB:
            if want_title:
                return _malformed(
                    group, src, tab_line, "'<!-- tab -->' missing its bold-only title"
                )
            if _indent(line) != indent:
                return _malformed(
                    group, src, num, "'<!-- tab -->' not at the group's indentation"
                )
            want_title = True
            tab_line = num
        elif want_title:
            if not stripped:
                continue
            m = TITLE.fullmatch(stripped)
            if m is None or _indent(line) != indent:
                return _malformed(
                    group,
                    src,
                    num,
                    "'<!-- tab -->' not followed by a bold-only title at the group's indentation",
                )
            if '"' in m.group(1):
                return _malformed(group, src, num, "tab title contains a double quote")
            if "*" in m.group(1):
                return _malformed(group, src, num, "tab title contains '*'")
            content = []
            tabs.append((m.group(1), content))
            want_title = False
        elif content is None:
            if stripped:
                return _malformed(
                    group, src, num, "content before the first '<!-- tab -->'"
                )
        else:
            content.append(line)

    if want_title:
        return _malformed(
            group, src, tab_line, "'<!-- tab -->' missing its bold-only title"
        )
    if len(tabs) < 2:
        return _malformed(
            group, src, start, f"{len(tabs)} tab(s); a group needs at least two"
        )

    out = []
    for title, body in tabs:
        while body and not body[-1].strip():
            body.pop()
        while body and not body[0].strip():
            body.pop(0)
        out.append(f'{indent}=== "{title}"')
        out.append("")
        out.extend("    " + line if line.strip() else line for line in body)
        out.append("")
    while out and not out[-1].strip():
        out.pop()
    return out


def _warn(src, num, reason):
    log.warning("%s:%d: tab group left unconverted: %s", src, num, reason)


def _malformed(group, src, num, reason):
    _warn(src, num, reason)
    return group
