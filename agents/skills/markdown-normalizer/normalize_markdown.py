#!/usr/bin/env python3
"""Normalize a Markdown file to ASCII prose wrapped at 80 columns.

Usage:
    normalize_markdown.py --check FILE.md
    normalize_markdown.py FILE.md
"""

from __future__ import annotations

import argparse
import os
import re
import stat
import sys
import tempfile
import textwrap
import unicodedata
from pathlib import Path
from typing import Iterable

WRAP_WIDTH = 80
EXIT_OK = 0
EXIT_NEEDS_ATTENTION = 1
EXIT_UNSAFE_INPUT = 2

FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})(.*)$")
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}(?:\s|$)")
THEMATIC_BREAK_RE = re.compile(
    r"^\s{0,3}(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$"
)
SETEXT_UNDERLINE_RE = re.compile(r"^\s{0,3}(?:=+|-+)\s*$")
LIST_ITEM_RE = re.compile(
    r"^(\s*)([-+*]|\d{1,9}[.)])(?:([ \t]+)(.*))?$"
)
BLOCKQUOTE_RE = re.compile(r"^\s{0,3}>\s?(.*)$")
LINK_REFERENCE_RE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*\S")
TABLE_DELIMITER_RE = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$"
)
TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
HTML_START_RE = re.compile(r"^\s{0,3}(?:<!--|</?[A-Za-z][^>]*>)")
INLINE_CODE_RE = re.compile(r"(`+)(.+?)\1")
HARD_BREAK_RE = re.compile(r"(?: {2,}|\\)$")

ASCII_REPLACEMENTS = str.maketrans(
    {
        "\u00a0": " ",
        "\u00ad": "",
        "\u2000": " ",
        "\u2001": " ",
        "\u2002": " ",
        "\u2003": " ",
        "\u2004": " ",
        "\u2005": " ",
        "\u2006": " ",
        "\u2007": " ",
        "\u2008": " ",
        "\u2009": " ",
        "\u200a": " ",
        "\u202f": " ",
        "\u205f": " ",
        "\u3000": " ",
        "\u200b": "",
        "\u200c": "",
        "\u200d": "",
        "\u2060": "",
        "\ufeff": "",
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
        "\u2212": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201b": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u201f": '"',
        "\u2032": "'",
        "\u2033": '"',
        "\u2034": "'''",
        "\u2035": "'",
        "\u2036": '"',
        "\u2039": "'",
        "\u203a": "'",
        "\u00ab": '"',
        "\u00bb": '"',
        "\u2026": "...",
        "\u2022": "-",
        "\u2023": "-",
        "\u2043": "-",
        "\u2044": "/",
        "\u2215": "/",
        "\u00d7": "x",
        "\u00f7": "/",
        "\u00a9": "(c)",
        "\u00ae": "(r)",
        "\u2122": "(tm)",
        "\u2190": "<-",
        "\u2192": "->",
        "\u2194": "<->",
        "\u21d0": "<=",
        "\u21d2": "=>",
        "\u21d4": "<=>",
        "\u00b4": "'",
        "\u02bc": "'",
        "\u02c6": "^",
        "\u02dc": "~",
    }
)


class UnsafeMarkdownFile(Exception):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise UnsafeMarkdownFile(message)


def normalize_ascii(text: str) -> str:
    replaced = text.translate(ASCII_REPLACEMENTS)
    decomposed = unicodedata.normalize("NFKD", replaced)
    without_marks = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    return without_marks.translate(ASCII_REPLACEMENTS)


def normalize_outside_inline_code(line: str) -> str:
    pieces: list[str] = []
    cursor = 0
    for match in INLINE_CODE_RE.finditer(line):
        pieces.append(normalize_ascii(line[cursor : match.start()]))
        pieces.append(match.group(0))
        cursor = match.end()
    pieces.append(normalize_ascii(line[cursor:]))
    return "".join(pieces)


def frontmatter_end(lines: list[str]) -> int | None:
    if not lines or lines[0].strip() != "---":
        return None
    for index in range(1, len(lines)):
        if lines[index].strip() in {"---", "..."}:
            return index
    return None


def strip_blockquote_prefixes(line: str) -> str:
    while True:
        match = BLOCKQUOTE_RE.match(line)
        if match is None:
            return line
        line = match.group(1)


def code_line_mask(lines: list[str]) -> list[bool]:
    mask: list[bool] = []
    fence: tuple[str, int] | None = None

    for line in lines:
        content = strip_blockquote_prefixes(line)
        if fence is not None:
            mask.append(True)
            match = FENCE_RE.match(content)
            if (
                match
                and match.group(1)[0] == fence[0]
                and len(match.group(1)) >= fence[1]
                and not match.group(2).strip()
            ):
                fence = None
            continue

        opening = FENCE_RE.match(content)
        if opening is not None:
            fence = (opening.group(1)[0], len(opening.group(1)))
            mask.append(True)
            continue

        mask.append(content.startswith(("    ", "\t")))

    return mask


def normalize_document(text: str) -> str:
    lines = text.splitlines()
    protected = code_line_mask(lines)

    normalized = [
        line if protected[index] else normalize_outside_inline_code(line)
        for index, line in enumerate(lines)
    ]
    return join_preserving_final_newline(normalized, text)


def detect_newline(text: str) -> str:
    if "\r\n" in text:
        return "\r\n"
    if "\r" in text:
        return "\r"
    return "\n"


def join_preserving_final_newline(lines: Iterable[str], source: str) -> str:
    newline = detect_newline(source)
    joined = newline.join(lines)
    return joined + newline if source.endswith(("\n", "\r")) else joined


def is_blank(line: str) -> bool:
    return not line.strip()


def is_fence_start(line: str) -> bool:
    return FENCE_RE.match(line) is not None


def is_heading(line: str) -> bool:
    return HEADING_RE.match(line) is not None


def is_thematic_break(line: str) -> bool:
    return THEMATIC_BREAK_RE.match(line) is not None


def is_blockquote(line: str) -> bool:
    return BLOCKQUOTE_RE.match(line) is not None


def is_list_item(line: str) -> bool:
    return LIST_ITEM_RE.match(line) is not None


def is_table_delimiter(line: str) -> bool:
    return TABLE_DELIMITER_RE.match(line) is not None


def is_table_row(line: str) -> bool:
    return TABLE_ROW_RE.match(line) is not None


def is_table_start(lines: list[str], index: int) -> bool:
    line = lines[index]
    if is_table_row(line) or is_table_delimiter(line):
        return True
    return (
        "|" in line
        and index + 1 < len(lines)
        and is_table_delimiter(lines[index + 1])
    )


def is_html_start(line: str) -> bool:
    return HTML_START_RE.match(line) is not None


def is_preserved_line(line: str) -> bool:
    return (
        is_heading(line)
        or is_thematic_break(line)
        or SETEXT_UNDERLINE_RE.match(line) is not None
        or LINK_REFERENCE_RE.match(line) is not None
    )


def is_indented_code(line: str) -> bool:
    return line.startswith(("    ", "\t"))


def is_block_start(lines: list[str], index: int) -> bool:
    line = lines[index]
    return (
        is_fence_start(line)
        or is_blockquote(line)
        or is_list_item(line)
        or is_table_start(lines, index)
        or is_html_start(line)
        or is_preserved_line(line)
    )


def copy_fenced_code(lines: list[str], start: int) -> tuple[list[str], int]:
    opening = FENCE_RE.match(lines[start])
    require(opening is not None, "expected a fenced code block")
    fence_character = opening.group(1)[0]
    fence_length = len(opening.group(1))

    block = [lines[start]]
    index = start + 1
    while index < len(lines):
        line = lines[index]
        block.append(line)
        index += 1
        closing = FENCE_RE.match(line)
        if (
            closing is not None
            and closing.group(1)[0] == fence_character
            and len(closing.group(1)) >= fence_length
            and not closing.group(2).strip()
        ):
            break
    return block, index


def copy_indented_code(lines: list[str], start: int) -> tuple[list[str], int]:
    block: list[str] = []
    index = start
    while index < len(lines):
        line = lines[index]
        if is_indented_code(line) or is_blank(line):
            block.append(line)
            index += 1
        else:
            break
    return block, index


def copy_table(lines: list[str], start: int) -> tuple[list[str], int]:
    block: list[str] = []
    index = start
    while index < len(lines) and "|" in lines[index] and not is_blank(lines[index]):
        block.append(lines[index])
        index += 1
    return block, index


def copy_html_block(lines: list[str], start: int) -> tuple[list[str], int]:
    block = [lines[start]]
    index = start + 1
    if "<!--" in lines[start] and "-->" not in lines[start]:
        while index < len(lines):
            block.append(lines[index])
            index += 1
            if "-->" in block[-1]:
                break
        return block, index

    while index < len(lines) and not is_blank(lines[index]):
        block.append(lines[index])
        index += 1
    return block, index


def wrap_paragraph(
    source_lines: list[str],
    width: int,
    initial_indent: str = "",
    subsequent_indent: str = "",
) -> list[str]:
    if not source_lines:
        return []

    last_line = source_lines[-1]
    hard_break = HARD_BREAK_RE.search(last_line)
    hard_break_suffix = ""
    if hard_break is not None:
        hard_break_suffix = hard_break.group(0)
        source_lines = [*source_lines[:-1], last_line[: hard_break.start()]]

    text = " ".join(line.strip() for line in source_lines)
    available_width = max(
        width, len(initial_indent) + 1, len(subsequent_indent) + 1
    )
    wrapped = textwrap.wrap(
        text,
        width=available_width,
        initial_indent=initial_indent,
        subsequent_indent=subsequent_indent,
        break_long_words=False,
        break_on_hyphens=False,
    )
    if not wrapped:
        wrapped = [initial_indent.rstrip()]
    if hard_break_suffix:
        wrapped[-1] += hard_break_suffix
    return wrapped


def leading_indentation(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def strip_continuation_indent(line: str, width: int) -> str:
    prefix = " " * width
    if line.startswith(prefix):
        return line[width:]
    return line.lstrip()


def wrap_list_item(
    lines: list[str], start: int, width: int
) -> tuple[list[str], int]:
    first = LIST_ITEM_RE.match(lines[start])
    require(first is not None, "expected a list item")
    indentation, marker, spacing, first_text = first.groups()
    spacing = spacing or " "
    first_text = first_text or ""
    first_prefix = f"{indentation}{marker}{spacing}"
    continuation_width = len(first_prefix)
    base_indent = leading_indentation(lines[start])

    item_lines = [first_text]
    index = start + 1
    while index < len(lines):
        line = lines[index]
        if is_blank(line):
            next_content = next(
                (
                    candidate
                    for candidate in range(index + 1, len(lines))
                    if not is_blank(lines[candidate])
                ),
                None,
            )
            if (
                next_content is not None
                and leading_indentation(lines[next_content]) > base_indent
            ):
                item_lines.append("")
                index += 1
                continue
            break

        line_indent = leading_indentation(line)
        if is_list_item(line) and line_indent <= base_indent:
            break
        if line_indent > base_indent:
            item_lines.append(line)
            index += 1
            continue
        if is_block_start(lines, index):
            break

        item_lines.append(line)
        index += 1

    item_text = "\n".join(
        [
            item_lines[0],
            *(
                strip_continuation_indent(line, continuation_width)
                for line in item_lines[1:]
            ),
        ]
    )
    inner = wrap_markdown(item_text, max(width - continuation_width, 1))
    inner_lines = inner.splitlines()

    if not inner_lines:
        return [first_prefix.rstrip()], index

    output = [
        first_prefix + inner_lines[0] if inner_lines[0] else first_prefix.rstrip()
    ]
    output.extend(
        " " * continuation_width + line if line else ""
        for line in inner_lines[1:]
    )
    return output, index


def wrap_blockquote(
    lines: list[str], start: int, width: int
) -> tuple[list[str], int]:
    inner_lines: list[str] = []
    index = start
    while index < len(lines):
        match = BLOCKQUOTE_RE.match(lines[index])
        if match is None:
            break
        inner_lines.append(match.group(1))
        index += 1

    inner = wrap_markdown("\n".join(inner_lines), max(width - 2, 1))
    quoted = ["> " + line if line else ">" for line in inner.splitlines()]
    return quoted, index


def collect_paragraph(
    lines: list[str], start: int
) -> tuple[list[str], int, bool]:
    block: list[str] = []
    index = start
    while index < len(lines):
        line = lines[index]
        if is_blank(line):
            break
        if block and SETEXT_UNDERLINE_RE.match(line):
            block.append(line)
            return block, index + 1, True
        if block and is_block_start(lines, index):
            break
        block.append(line)
        index += 1
        if HARD_BREAK_RE.search(line):
            break
    return block, index, False


def wrap_markdown(text: str, width: int = WRAP_WIDTH) -> str:
    lines = text.splitlines()
    output: list[str] = []
    index = 0

    frontmatter_last = frontmatter_end(lines)
    if frontmatter_last is not None:
        output.extend(lines[: frontmatter_last + 1])
        index = frontmatter_last + 1

    while index < len(lines):
        line = lines[index]

        if is_blank(line):
            output.append(line)
            index += 1
        elif is_fence_start(line):
            block, index = copy_fenced_code(lines, index)
            output.extend(block)
        elif is_list_item(line):
            block, index = wrap_list_item(lines, index, width)
            output.extend(block)
        elif is_blockquote(line):
            block, index = wrap_blockquote(lines, index, width)
            output.extend(block)
        elif is_table_start(lines, index):
            block, index = copy_table(lines, index)
            output.extend(block)
        elif is_html_start(line):
            block, index = copy_html_block(lines, index)
            output.extend(block)
        elif is_indented_code(line):
            block, index = copy_indented_code(lines, index)
            output.extend(block)
        elif is_preserved_line(line):
            output.append(line)
            index += 1
        else:
            block, index, is_setext = collect_paragraph(lines, index)
            output.extend(block if is_setext else wrap_paragraph(block, width))

    return join_preserving_final_newline(output, text)


def unresolved_non_ascii(text: str) -> list[tuple[int, str]]:
    diagnostics: list[tuple[int, str]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        seen: set[str] = set()
        for character in line:
            if ord(character) > 127 and character not in seen:
                diagnostics.append((line_number, character))
                seen.add(character)
    return diagnostics


def describe_character(character: str) -> str:
    codepoint = f"U+{ord(character):04X}"
    name = unicodedata.name(character, "UNKNOWN")
    return f"{character!r} ({codepoint} {name})"


def read_markdown(path: Path) -> tuple[str, int]:
    require(path.suffix.lower() == ".md", f"not a .md file: {path}")
    require(not path.is_symlink(), f"refusing to follow symlink: {path}")

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise UnsafeMarkdownFile(f"cannot open {path}: {error}") from error

    try:
        file_stat = os.fstat(descriptor)
        require(
            stat.S_ISREG(file_stat.st_mode),
            f"not a regular file: {path}",
        )
        require(
            file_stat.st_uid == os.geteuid(),
            f"owned by uid {file_stat.st_uid}, not caller uid {os.geteuid()}: {path}",
        )
        require(
            os.access(path, os.R_OK | os.W_OK),
            f"caller lacks read/write permission: {path}",
        )
        require(
            os.access(path.parent, os.W_OK),
            f"parent directory is not writable: {path.parent}",
        )
        with os.fdopen(
            descriptor, "r", encoding="utf-8", newline=""
        ) as file:
            descriptor = -1
            return file.read(), file_stat.st_mode
    except UnicodeDecodeError as error:
        raise UnsafeMarkdownFile(f"not valid UTF-8: {path}: {error}") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def write_atomically(path: Path, content: str, mode: int) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(
            descriptor, "w", encoding="utf-8", newline=""
        ) as file:
            descriptor = -1
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.chmod(temporary_name, stat.S_IMODE(mode))
        os.replace(temporary_name, path)
    except Exception:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize a Markdown file to ASCII prose wrapped at 80 columns."
        )
    )
    parser.add_argument("markdown_file", type=Path)
    parser.add_argument(
        "--check",
        action="store_true",
        help="report whether the file would change without writing it",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    path = arguments.markdown_file

    try:
        original, file_mode = read_markdown(path)
    except UnsafeMarkdownFile as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_UNSAFE_INPUT

    normalized = wrap_markdown(normalize_document(original), WRAP_WIDTH)
    changed = normalized != original
    diagnostics = unresolved_non_ascii(normalized)

    if arguments.check:
        if changed:
            print(f"{path}: would be normalized")
        elif diagnostics:
            print(f"{path}: has no formatting changes")
        else:
            print(f"{path}: is already normalized")
    elif changed:
        try:
            write_atomically(path, normalized, file_mode)
        except OSError as error:
            print(f"error: cannot write {path}: {error}", file=sys.stderr)
            return EXIT_UNSAFE_INPUT
        print(f"{path}: normalized")
    elif diagnostics:
        print(f"{path}: has no formatting changes")
    else:
        print(f"{path}: is already normalized")

    for line_number, character in diagnostics:
        print(
            f"{path}:{line_number}: cannot normalize "
            f"{describe_character(character)}",
            file=sys.stderr,
        )

    if diagnostics or (arguments.check and changed):
        return EXIT_NEEDS_ATTENTION
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
