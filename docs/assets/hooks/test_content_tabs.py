"""Tests for the content_tabs mkdocs hook."""

import logging
from types import SimpleNamespace

import content_tabs
import pytest

LOGGER = "mkdocs.hooks.content_tabs"


def render(markdown):
    page = SimpleNamespace(file=SimpleNamespace(src_uri="how-to/test.md"))
    return content_tabs.on_page_markdown(markdown, page=page)


TOP_LEVEL = """\
intro

<!-- tabs:start -->

<!-- tab -->
**macOS / Linux**

```bash
echo mac
```

<!-- tab -->
**Windows**

```powershell
echo win
```

<!-- tabs:end -->

outro
"""


def test_page_without_tabs_is_untouched():
    assert render("# Title\n\nplain text\n") == "# Title\n\nplain text\n"


def test_top_level_group_converts():
    out = render(TOP_LEVEL)
    assert '=== "macOS / Linux"' in out
    assert '=== "Windows"' in out
    assert "<!-- tab" not in out
    assert "    ```bash" in out
    assert "    echo mac" in out
    assert "intro" in out and "outro" in out


def test_nested_in_list_group_keeps_relative_indentation():
    src = (
        "1. **Step.**\n"
        "\n"
        "    <!-- tabs:start -->\n"
        "\n"
        "    <!-- tab -->\n"
        "    **A**\n"
        "\n"
        "    ```bash\n"
        "    echo a\n"
        "    ```\n"
        "\n"
        "    <!-- tab -->\n"
        "    **B**\n"
        "\n"
        "    text b\n"
        "\n"
        "    <!-- tabs:end -->\n"
    )
    out = render(src)
    assert '    === "A"' in out
    assert "        ```bash" in out
    assert "        text b" in out


def test_three_tab_group():
    src = TOP_LEVEL.replace(
        "<!-- tabs:end -->",
        "<!-- tab -->\n**zsh**\n\nz\n\n<!-- tabs:end -->",
    )
    out = render(src)
    assert out.count('=== "') == 3


def test_markers_inside_fences_are_content():
    src = (
        "~~~markdown\n"
        "<!-- tabs:start -->\n"
        "<!-- tab -->\n"
        "**A**\n"
        "<!-- tabs:end -->\n"
        "~~~\n"
    )
    assert render(src) == src


def test_bold_line_in_body_stays_content():
    src = TOP_LEVEL.replace("echo mac\n```", "echo mac\n```\n\n**Note in body**")
    out = render(src)
    assert out.count('=== "') == 2
    assert "    **Note in body**" in out


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda s: s.replace("<!-- tabs:end -->\n", ""), "unclosed"),
        (
            lambda s: s.replace(
                "<!-- tab -->\n**macOS / Linux**",
                "stray text\n\n<!-- tab -->\n**macOS / Linux**",
            ),
            "content before the first",
        ),
        (
            lambda s: s.replace(
                "<!-- tab -->\n**macOS / Linux**", "<!-- tab -->\nnot a title"
            ),
            "bold-only title",
        ),
        (
            lambda s: s.replace(
                "<!-- tab -->\n**Windows**", "  <!-- tab -->\n**Windows**"
            ),
            "indentation",
        ),
        (
            lambda s: s.replace("<!-- tabs:end -->", "  <!-- tabs:end -->"),
            "indentation",
        ),
        (lambda s: s.replace("**Windows**", '**Win "x"**'), "double quote"),
    ],
)
def test_malformed_groups_pass_through_with_warning(caplog, mutate, reason):
    src = mutate(TOP_LEVEL)
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        out = render(src)
    assert out == src
    assert reason in caplog.text


def test_nested_start_warns_and_passes_through(caplog):
    src = TOP_LEVEL.replace(
        "<!-- tab -->\n**Windows**",
        "<!-- tabs:start -->\n\n<!-- tab -->\n**Windows**",
    )
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        out = render(src)
    assert out == src
    assert "nested" in caplog.text


def test_single_tab_group_warns(caplog):
    src = TOP_LEVEL.replace(
        "<!-- tab -->\n**Windows**\n\n```powershell\necho win\n```\n\n", ""
    )
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        out = render(src)
    assert out == src
    assert "at least two" in caplog.text


# ---------------------------------------------------------------------------
# Fix 1: trailing dangling <!-- tab --> reports its own line number
# ---------------------------------------------------------------------------

# Fixture (no leading blank lines so line numbers are predictable):
# Line 1: <!-- tabs:start -->
# Line 2: (blank)
# Line 3: <!-- tab -->
# Line 4: **Alpha**
# Line 5: (blank)
# Line 6: body
# Line 7: (blank)
# Line 8: <!-- tab -->   ← dangling, no title follows
# Line 9: <!-- tabs:end -->
_DANGLING_TAB_SRC = """\
<!-- tabs:start -->

<!-- tab -->
**Alpha**

body

<!-- tab -->
<!-- tabs:end -->
"""


def test_trailing_dangling_tab_warns_at_marker_line(caplog):
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        out = render(_DANGLING_TAB_SRC)
    assert out == _DANGLING_TAB_SRC
    # The dangling <!-- tab --> is at line 8; src_uri is "how-to/test.md"
    assert "how-to/test.md:8:" in caplog.text


# ---------------------------------------------------------------------------
# Fix 2: title containing '*' is rejected
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (
            lambda s: s.replace("**Windows**", "**A** **B**"),
            "'*'",
        ),
    ],
)
def test_star_in_title_is_malformed(caplog, mutate, reason):
    src = mutate(TOP_LEVEL)
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        out = render(src)
    assert out == src
    assert reason in caplog.text


# ---------------------------------------------------------------------------
# Fix 3a: two tab groups on one page both convert
# ---------------------------------------------------------------------------

TWO_GROUPS = """\
first

<!-- tabs:start -->

<!-- tab -->
**A**

body a

<!-- tab -->
**B**

body b

<!-- tabs:end -->

middle

<!-- tabs:start -->

<!-- tab -->
**C**

body c

<!-- tab -->
**D**

body d

<!-- tabs:end -->

last
"""


def test_two_groups_both_convert():
    out = render(TWO_GROUPS)
    assert out.count('=== "') == 4
    assert "<!-- tab" not in out
    assert "<!-- tabs:" not in out


# ---------------------------------------------------------------------------
# Fix 3b: fence inside tab body with marker-lookalike lines is preserved
# ---------------------------------------------------------------------------

FENCE_IN_BODY = """\
<!-- tabs:start -->

<!-- tab -->
**Tab1**

```markdown
<!-- tab -->
**X**
<!-- tabs:end -->
```

<!-- tab -->
**Tab2**

plain

<!-- tabs:end -->
"""


def test_fence_in_body_preserves_content():
    out = render(FENCE_IN_BODY)
    # Exactly 2 tabs rendered
    assert out.count('=== "') == 2
    # Fence content preserved (indented as body)
    assert "    <!-- tab -->" in out
    assert "    **X**" in out
    assert "    <!-- tabs:end -->" in out


# ---------------------------------------------------------------------------
# Fix 3c: warnings carry src_uri:line  (reuses test from fix 1 which already
# pins "how-to/test.md:8:" — this test makes the contract explicit)
# ---------------------------------------------------------------------------


def test_malformed_warning_includes_src_uri(caplog):
    # A group with a dangling tab at a known line; src_uri comes from render()
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        render(_DANGLING_TAB_SRC)
    assert "how-to/test.md:" in caplog.text
