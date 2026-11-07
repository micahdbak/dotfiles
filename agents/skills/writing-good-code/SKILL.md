---
name: writing-good-code
description: Writing good code - KISS, readability, naming, and comments. Use when implementing, refactoring, or reviewing code.
---

## Keep it simple

KISS: Keep It Simple, Stupid. Prefer the simplest design that solves the actual
problem. Fewer moving parts, fewer concepts, and fewer hidden states are easier
to understand, test, and change. Simple is not the same as short: a longer,
direct function is simpler than a clever one-liner that hides its control flow.

Reach for the language's standard library and existing idioms before adding an
abstraction or dependency. Abstract when a second real use case appears, not
when one might appear later. Performance work follows the same rule: measure
first, then simplify the hot path only where the measurement shows it matters.

## Readability first

Code should be readable in and of itself; comments should be unnecessary. When a
comment would explain what the code does, first try to make the code say it
instead. Rename variables and functions, extract a small function, or
restructure the branch so the intent is visible at the call site.

Readable code follows the language's idioms. Do not contort it into something
less familiar just to avoid a comment.

## Comments

A comment is justified when the code is already as readable as the language
allows, and the comment adds something the code cannot: why a non-obvious choice
was made, a constraint from outside the code, or a faster approach that would
otherwise look strange.

Keep comments short and utilitarian. Complement the code; never restate it.
Someone reading the comment is also reading the code, so use simple English to
explain only what is not obvious from the code itself.

## Performance

When improving performance, prefer a refactor aimed at a 10x improvement over a
cache that buys five percent. Always investigate a better architecture before a
hotfix. Large gains usually come from changing the shape of the work, not from
patching the current path.

## Dead code

When making a change, check what it deprecates. If the change leaves a function,
export, or dependency unreachable, remove it in the same change. Dead code is
not free: it still costs reading, searching, and maintenance, and it makes the
codebase look larger than it is.
