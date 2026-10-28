---
name: tscon-know-how
description: How to build, debug, and explain apps using the @micahdb/tscon WebGL2 text-mode graphics library.
---

# Using @micahdb/tscon

tscon renders a `<canvas>` as a grid of fixed character cells via WebGL2: text
is compiled to packed 16-bit glyph cells, composited in a CPU-side framebuffer,
and drawn as one instanced-quad GPU call. Install `@micahdb/tscon` and import
from the package root. Exact signatures and per-API doc comments live in the
installed package (`node_modules/@micahdb/tscon/dist/*.d.ts`); consult them for
signatures. This skill carries what they do not state: the mental model, the
behavioural invariants, and the downstream practices.

API map (roles, not signatures):

- **`Canvas`**: owns the WebGL2 context, cell-grid dimensions, palette, the
  built-in bitmap font and an optional application-provided user font, and all
  mouse/wheel/keyboard state. Everything else is constructed from it.
- **Text pipeline**: `textGlyphs` / `textToLines` compile escape-formatted text
  into a `Glyphs` grid; supporting types `Anchor`, `Rect`, `Colour`, `PALETTE`,
  `TAB_WIDTH`.
- **Presenters**: `Terminal` draws a glyph framebuffer; `Renderer` +
  `textureGlyphs` / `TexGlyphMode` draw a texture as cells. Both draw onto a
  `Canvas`.
- **3D support**: `Mat4` / `Vec4`, `compileProgram` / `getAttribLocations` /
  `getUniformLocations`, `loadTexture` / `loadCubeMap`, and `renderCp437`
  (custom font atlas generation).

## The four paradigms

Everything in tscon follows from four decisions. Internalize them before the
API.

1. **Cell-grid thinking.** There are no pixels downstream. Layout, hit-testing,
   scrolling, and regions (`Rect`) are all integer `{row, col, rows, cols}`. The
   screen is `canvas.rows` by `canvas.cols` cells of roughly 8x16 CSS px
   (`Canvas.CELL_WIDTH/CELL_HEIGHT`). If you want sub-cell precision, you are
   fighting the paradigm; reposition by cells instead.
2. **Text-as-data.** Content is a plain string with escape sequences
   (`\fX`/`\FX`/`\bX`/`\BX` colours, `\aX{...}` anchors, `\\`, backslash-newline
   continuation, tabs, word wrap). `textGlyphs(text, cols, wrap)` compiles it
   once per width into a `Glyphs` grid. Styling lives in the text, not in code.
   Escape digits clamp (colours to 0-7 with `F`/`B` adding 8, anchor groups to
   0-9) and characters outside CP437 render blank.
3. **GPU-first rendering.** The CPU only packs bytes (2 per cell); the shaders
   do all rasterization: font sampling, colouring, cursor inversion,
   texture-to-ASCII conversion. Compile glyphs when text or width changes, not
   per frame.
4. **Anchors as the interaction bridge.** `\aX{options}` occupies zero columns
   but records `{row, col, options}` into `Glyphs.anchors[X]`; whatever string
   sits between the braces comes back verbatim as the anchor's `options` field
   (or `null` when the braces are absent or empty). Downstream code turns those
   positions into live components (links, headings, image slots) by hit-testing
   cell rects at the anchor position and blitting its own glyphs over them.
   Anchor group digits and options conventions (e.g. `text|url`) are app-defined
   channels.

## How it works internally

### Glyph cells and the zero sentinel

One cell = one `u16`: `[ fg(4) | bg(4) | CP437 char(8) ]`. Two bytes per cell
keeps the framebuffer tiny, makes blits plain `Uint16Array` memcpys, and lets
the GPU read the same buffer as two byte attributes with no unpacking.

A cell of exactly `0` (a space on the default colour) is *blank*: the shader
clips its quad off-screen, so it never paints. This makes Terminal a transparent
overlay: text drawn late in the frame floats over textures drawn earlier.
`textGlyphs` omits default-colour trailing spaces for this reason; a space with
a non-default background is a real, painted cell. A related trick: colour byte 0
doubles as "default" (white-on-black) when the char is nonzero, so true
black-on-black is unexpressible, which is harmless because it would be
invisible.

### Blit vs draw

The split is deliberate. `terminal.blit(glyphs, src, dst)` is pure memory work:
it requires `src` and `dst` to have identical dimensions (mismatch logs to
console and skips), shifts negative origins into bounds, clips overflow to the
canvas, and copies rows, all on internal copies of the rects, so the objects you
pass are never modified. Compositing belongs on the CPU because it is frequent,
order-dependent, and clip-heavy. `terminal.draw()` is the frame's only GPU
touch: upload the whole framebuffer, bind the fonts, one instanced draw covering
every cell. `Renderer.draw(tglyphs, texture, dst)` has the same contract:
`tglyphs.rows/cols` must equal `dst.rows/cols` exactly (mismatch logs and
skips), and `dst` may extend past the canvas because the shader clips.

### Fonts

Two font sources, selected per character:

- **Built-in bitmap font** (Modern DOS 8x16 CP437): bit-packed into a GPU
  integer texture and sampled bit-exact with a sharp-bilinear reconstruction
  (texel centres snap, edges blend), so glyphs stay crisp at the fractional cell
  sizes DPR scaling produces. Box-drawing and shade characters (CP437 codes
  176-223) always use it.
- **Optional user font** (`canvas.user_font`): a float texture laid out as a
  32x8 CP437 atlas, used for all other characters. Generate one from any font
  with `renderCp437(offscreen2dCanvas, cssFont)` (it forces the 2:1 cell aspect
  and leaves box-drawing chars to the bitmap font), upload with `loadTexture`,
  then set `terminal.use_user_font = true` / `renderer.use_user_font = true`.
  Both flags auto-reset to the bitmap font while `user_font` is null, so async
  loading is safe: hold the texture in a nullable field and assign it inside the
  frame loop once it resolves.

### Renderer: textures as cells

`textureGlyphs(rows, cols, mode)` builds a `u32` grid, one cell packed as
`[ row(8) | mode(8) | col(16) ]`. Keep grids at or under 256 rows, which is also
the canvas's row cap. Modes (`TexGlyphMode`):

- `SAMPLE`: show the texture as-is; each cell is a UV window into it.
- `GLYPHS`: convert each cell to a coloured character. Hue is snapped to the
  nearest of 8 palette directions, 4x4 Bayer dithering picks between the two
  nearest, and luminance maps onto the ramp ` .,-:;=!*#$@`; the background stays
  black. Use under text.
- `BG_GLYPHS`: like `GLYPHS`, but the background also carries colour, making it
  brighter and more accurate. Use when no text sits on top.
- `MIX` / `ROWS` / `COLS`: alternate `SAMPLE` and `GLYPHS` per cell by
  checkerboard, row, or column.

The texture is sampled once per cell in the vertex shader, so conversion cost
scales with cells, not pixels. Hovering a `SAMPLE` cell inverts its colours;
glyph-mode cells swap fg/bg.

### Canvas: grid, resize, input

- **Arbitrary placement is supported.** Mouse coordinates are computed relative
  to the element's bounding rectangle, so the canvas works anywhere on a page,
  including embedded inside a scrolling document where it is only occasionally
  in view. `Canvas` derives the device-pixel buffer from
  `clientWidth/Height * devicePixelRatio`. For a page-style app, size the
  element with CSS to fill the viewport:
  `position: fixed; inset: 0; width/height: 100svw/100svh;` plus
  `touch-action: none; user-select: none`.
- **Grid size**: `rows = round(height / (16 * DPR))` clamped to [1, 256], `cols`
  likewise over 8 px clamped to [1, 1024]. Cells then stretch to fill the buffer
  exactly, so actual cell size is usually fractional (the bitmap font's
  sharp-bilinear covers this).
- **`Canvas` is an `EventTarget`.** `"resize"` fires only when the cell counts
  change; pixel-only resizes silently update the buffer and cell size. `"wheel"`
  is a `CustomEvent` whose `detail.rows` is already in whole rows; pixel-mode
  deltas accumulate across events until they cross a cell height, so trackpads
  scroll smoothly.
- **Input state, in cell units**: `mouse_row/col` (`undefined` while the pointer
  is off-canvas; guard before arithmetic), `mouse_down`, `mouse_down_row/col`
  (press origin; hit-test clicks against this so a drag that leaves the rect
  still counts), `mouse_click` (true for one frame after release; components
  consume it, the app resets it at end of frame), `mouse_owner` (a drag claims
  this string; other components yield while it is set), `class_name` (components
  set a cursor class here; the app syncs it to `document.body`). Keyboard
  scrolling (j/k/arrows, `0` = jump to top, hold-to-repeat) is built in and
  emits the same `"wheel"` events. It engages only while the pointer is over the
  canvas or the canvas has DOM focus (the constructor adds `tabindex=0` unless
  the app set its own, so keyboard-only users can tab to it), it never fires
  while focus is in a text input, and it stops when the pointer leaves or focus
  moves away. All mouse state resets on resize and window blur.

## Recipe 1: bootstrap and frame loop

1. **HTML/CSS.** Place and size the canvas with CSS. For a page-style app make
   it fill the viewport (CSS in the Canvas section above); an embedded canvas
   inside a larger page works too. If content must survive without WebGL2,
   pre-render the same text to a `<pre>` fallback at build time and hide it once
   a WebGL2 context is acquired (this is what the author's site micahdb.com
   does). Done when: the canvas fills its intended area and `new Canvas(el)`
   does not throw.
2. **Construct once:** `new Canvas(el)`, `new Terminal(canvas)`,
   `new Renderer(canvas)`. Done when: all three construct (they throw on missing
   WebGL2 or shader errors).
3. **Frame loop, in this exact order.** Ordering is what makes compositing work:

```ts
let resized = false;
canvas.addEventListener("resize", () => { resized = true; });

const draw = () => {
  if (canvas.rows < 8 || canvas.cols < 16) {      // too-small guard
    canvas.clear(); terminal.clear(); terminal.draw();
    requestAnimationFrame(draw); return;
  }
  if (resized) { // rebuild width-dependent state
    resized = false;
    content = textGlyphs(CONTENT, contentCols(), true);
  }

  canvas.clear(); // clears to palette black, resets class_name
  // ... render offscreen scenes, renderer.draw(...) backgrounds (Recipe 4) ...
  terminal.clear(); // reallocates framebuffer after resize; resets detail_text
  // ... update components, terminal.blit(...) back-to-front ...
  terminal.draw(); // text over the background
  // ... any renderer.draw(...) meant to paint OVER text ...

  canvas.mouse_click = false; // consume the one-frame flag
  if (document.body.className !== canvas.class_name) {
    document.body.className = canvas.class_name;
  }
  requestAnimationFrame(draw);
};
requestAnimationFrame(draw);
```

   Done when: one frame renders text over the background with blank cells
   transparent, hover feedback works, and narrowing the window re-wraps text
   cleanly.
4. **Resize** is the flag pattern above: the event only sets `resized`; the
   frame loop rebuilds everything width-dependent (content glyphs,
   `textureGlyphs` grids, projection matrices). Done when: no rebuild logic
   lives in the event handler itself.

## Recipe 2: content and anchor components

1. **Author content** as text with escapes. Link convention:
   `\a0{Text|URL}Visible_Text`; the anchor sits immediately before visible text
   of the same length, and link text uses underscores instead of spaces so word
   wrap (which breaks at spaces) keeps it on one line, because the component
   overlays exactly `text.length` cells. Done when:
   `textGlyphs(content, cols, true).anchors[0].length` equals your link count.
2. **Compile per width**:
   `content = textGlyphs(str, Math.min(80, canvas.cols - padding), true)` at
   boot and inside the resize branch only. Done when: the per-frame path
   contains no `textGlyphs` call for static content.
3. **Build components once, position them per frame.** Construct component
   objects from the initial anchors (options parsing is your convention), then
   each frame re-read positions from the *current* `content.anchors[group][i]`
   matched by index. Indices survive recompilation at new widths; rows do not:

```ts
// once:
const links = (content.anchors[0] ?? []).map((a) => {
  const [text = "", url = text] = (a.options ?? "").split("|");
  return new Link(terminal, text, url);
});

// every frame:
const anchors = content.anchors[0] ?? [];
for (const [i, link] of links.entries()) {
  const a = anchors[i]; if (!a) break;
  const row = a.row - scrollRow, col = a.col + PADDING_COLS;
  if (row < 0 || row >= canvas.rows) continue;      // scrolled off-screen
  const g = link.update(row, col);
  terminal.blit(g, { row: 0, col: 0, rows: 1, cols: g.cols },
                   { row, col, rows: 1, cols: g.cols });
}
```

   Done when: after a resize, hover and click still land on the right rows.
4. **Component contract.** `update(row, col)`: hit-test hover with
   `canvas.mouseAt`, activation with
   `canvas.mouseDownAt(...) && canvas.mouse_click`; on hover set
   `canvas.class_name = "pointer"` and `terminal.detail_text` (a status line the
   Terminal draws across the bottom row; reserve your own status row above it
   when detail text may be present, and set both every frame since `clear()`
   resets them); return cached one-row `Glyphs`, recompiling only when visual
   state changed:

```ts
class Link {
  private hovered: boolean | null = null;   // null forces first compile
  private glyphs: Glyphs | null = null;
  constructor(private terminal: Terminal, private text: string,
              private url: string) {}

  update(row: number, col: number): Glyphs {
    const c = this.terminal.canvas;
    const hot = c.mouseAt(row, col, 1, this.text.length);
    if (hot && c.mouseDownAt(row, col, 1, this.text.length) && c.mouse_click) {
      window.open(this.url, "_blank");
    } else if (hot) {
      c.class_name = "pointer";
      this.terminal.detail_text = ` Link: ${this.url} `;
    }
    if (this.glyphs === null || hot !== this.hovered) {
      this.hovered = hot;
      this.glyphs = textGlyphs(
        hot ? `\\f0\\F4${this.text}` : `\\F4\\b0${this.text}`,
        this.text.length, false);
    }
    return this.glyphs;
  }
}
```

   Done when: glyph recompilation happens on state transitions only (verify by
   counting `textGlyphs` calls).

## Recipe 3: scrolling

Implement a pager: accumulate wheel rows, claim `mouse_owner` for drags, carry a
float offset with fling inertia, clamp, expose an integer row; blit the visible
slice of content. `blit`'s clipping handles overhang, so only the slice math is
yours:

```ts
let wheelRows = 0;
canvas.addEventListener("wheel", (e) => {
  wheelRows += (e as CustomEvent<{ rows: number }>).detail.rows;
});

let rowOffset = 0, velocity = 0;
let drag: { startRow: number; lastRow: number; offset: number } | null = null;

function updateScroll(contentRows: number): number {
  const max = Math.max(0, contentRows - canvas.rows);
  if (wheelRows !== 0) {
    if (!canvas.mouse_down) rowOffset += wheelRows;  // wheel ignored mid-drag
    wheelRows = 0; velocity = 0;                     // wheel cancels fling
  }

  if (canvas.mouse_down && canvas.mouse_row !== undefined) {
    if (canvas.mouse_owner === "") {
      canvas.mouse_owner = "pager";
      drag = { startRow: canvas.mouse_row, lastRow: canvas.mouse_row,
               offset: Math.round(rowOffset) };
    }
    if (canvas.mouse_owner === "pager" && drag) {
      velocity = Math.max(-2, Math.min(2, canvas.mouse_row - drag.lastRow));
      drag.lastRow = canvas.mouse_row;
      rowOffset = drag.offset - (canvas.mouse_row - drag.startRow);
    }
  } else {
    if (canvas.mouse_owner === "pager") {
      canvas.mouse_owner = ""; drag = null;
    }
    rowOffset -= velocity; velocity *= 0.95;
    if (Math.abs(velocity) < 0.01) velocity = 0;
  }
  rowOffset = Math.max(0, Math.min(max, rowOffset));
  return Math.round(rowOffset);
}
```

Done when: wheel, drag-with-fling, and the built-in j/k keys all scroll, and a
drag claimed by another component (`mouse_owner !== ""`) is not hijacked.

## Recipe 4: 3D or textured background

Render your scene into an offscreen FBO texture, then composite it with
`Renderer` *before* `terminal.draw()`.

1. **Own an FBO** (once): a fixed-size RGBA texture (e.g. 1024x1024), a
   `DEPTH_COMPONENT16` renderbuffer, and a framebuffer binding them. Done when:
   `checkFramebufferStatus` is complete.
2. **Respect the GL state boundary.** tscon's draw methods re-bind their own
   program, buffers, textures, and uniforms every call, but they assume the
   default framebuffer, a full-canvas viewport, and `DEPTH_TEST` off. Restore
   all three after your scene pass:

```ts
gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
gl.viewport(0, 0, 1024, 1024);
gl.enable(gl.DEPTH_TEST);
gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
// ... draw scene with compileProgram/Mat4 helpers ...
gl.bindFramebuffer(gl.FRAMEBUFFER, null);
gl.viewport(0, 0, canvas.width, canvas.height);
gl.disable(gl.DEPTH_TEST);
```

   Done when: the scene renders into the texture and the terminal still draws
   correctly afterward (state leaks surface as blank or wrongly-sized output).
3. **Aspect-correct for cells**: perspective aspect = `(0.5 * cols) / rows`,
   because cells are twice as tall as wide; a raw cell-count aspect
   double-stretches. Recompute on resize.
4. **Composite:** build
   `textureGlyphs(canvas.rows, canvas.cols, TexGlyphMode.GLYPHS)` (rebuild on
   resize) and call `renderer.draw` with `dst` =
   `{ row: 0, col: 0, rows: tglyphs.rows, cols: tglyphs.cols }` before
   `terminal.draw()`. Choose `GLYPHS` under text, `BG_GLYPHS` for fullscreen
   demos, `SAMPLE` for images that must stay photographic. Done when: the
   background appears as dithered coloured characters and text floats over it.

## Explaining tscon to a human

One paragraph, if asked why it is built this way: tscon treats the browser
canvas as a 1980s text-mode display, a fixed grid of character cells, but
implements it with modern GPU techniques. Text *is* the content model (styling
and interactivity markers are inline escapes), the CPU does only cheap memory
compositing (2 bytes per cell), and everything visual (font rasterization,
colouring, cursor highlighting, even turning live 3D renders into dithered
ASCII) runs in shaders over a single instanced draw. Interactivity is faked
honestly: anchors in the text mark positions, and small components re-render one
row of glyphs and hit-test cell rectangles each frame, which is how a character
grid ends up with links, scrolling, and hover effects that feel like a web page.
