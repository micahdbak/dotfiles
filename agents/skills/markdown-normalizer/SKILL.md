---
name: markdown-normalizer
description: Normalize Markdown prose to ASCII at 80 columns - convert typographic Unicode, report unnormalizable characters by line, and reflow paragraphs, lists, and blockquotes while preserving code and structural Markdown. Use when cleaning README, skill, or documentation files.
---

# Markdown Normalizer

The script is `normalize_markdown.py` beside this file. Run it from the skill
directory or through its installed path.

## Workflow

1. Check before writing:

   ```bash
   python3 normalize_markdown.py --check path/to/file.md
   ```

   Completion criterion: the command prints whether the file would change and
   exits 0 only when it is already normalized.

2. Normalize:

   ```bash
   python3 normalize_markdown.py path/to/file.md
   ```

   Completion criterion: the command prints `normalized` or reports that there
   are no formatting changes.

3. Fix reported characters by hand, then repeat step 1 until it exits 0 with no
   diagnostics.

## What it does

- Replaces common typographic characters: em and en dashes to `-`, curly quotes
  to `'` or `"`, ellipses to `...`, non-breaking spaces to spaces, arrows,
  symbols, and accented Latin letters decomposable by Unicode NFKD.
- Wraps paragraphs, list items, and blockquotes to 80 columns. List continuation
  indentation and blockquote prefixes count toward the width.
- Leaves structural Markdown out of wrapping: headings, tables, frontmatter
  layout, HTML blocks, link definitions, thematic breaks, and hard line breaks.
  Fenced and indented code blocks are left entirely unchanged, and inline code
  spans are left out of ASCII conversion and never split across lines. A long
  unbreakable token or preserved construct may remain longer than 80 columns.

## Remaining non-ASCII

Characters with no safe ASCII equivalent are reported with their line in the
normalized file:

```text
docs/README.md:42: cannot normalize '<character>' (U+2713 CHECK MARK)
```

This includes non-ASCII inside code, which the script leaves untouched for you
to review. Fix those lines, then rerun `--check`.

## Safety

The script exits 2 before reading or writing when the path is not a `.md` file,
is a symlink or not a regular file, is not owned by the caller, lacks read/write
permission, has an unwritable parent directory, or is not valid UTF-8. Writes
are atomic: it writes a temporary file in the same directory, fsyncs it,
preserves the original mode, and replaces the target.

## Exit codes

- `0` - normalized and no non-ASCII remains.
- `1` - `--check` found changes, or non-ASCII remains after normalization.
- `2` - unsafe input or write failure; the file was not changed.
