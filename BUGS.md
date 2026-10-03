# Known bugs

Found in a full review sweep on 2026-10-03 (four parallel reviews of tools &
selections, window/files/settings, image algorithms/GIF/replay, and UI
widgets/snap packaging). Most were reproduced with `tools/shot.py` scripts;
"(code)" marks findings derived from reading the code only.

Status: `[ ]` open, `[x]` fixed.

All 39 were fixed on 2026-10-03 and re-tested with the same reproduction
scripts (headless, plus real key events under X11 for #11/#12). #14 and #30
were verified by reading the code only (the native file chooser can't run
headless); #17 now uses Paint98's own Print Preview window.

## High: data loss or the app can't start

1. [x] **Redo after undoing a moved selection loses the pixels.** Undo of a
   lifted selection drops the floating pixels, and the redo stack receives the
   picture with the hole already erased. Same for paste → undo → redo.
   `canvas.py` `lift_selection` / `undo` / `redo`.
2. [x] **Undo in the middle of a drag also undoes the previous action.** Line,
   shapes, curve, polygon, gradient fill, new selections and text-box drags
   haven't pushed an undo step yet, but `Canvas.undo` cancels the drag *and*
   calls `doc.undo()`. `canvas.py` `undo`.
3. [x] **A file name that isn't valid UTF-8 bricks start-up.** The path goes
   into the title and recent files (surrogate escapes → `UnicodeEncodeError`),
   is saved to settings.json, and every later launch crashes in
   `refresh_recent`. Use `GLib.filename_display_name()` for labels/titles.
4. [x] **settings.json with wrong types crashes start-up** (e.g.
   `"tolerance": "x"`, `"window_size": [1,2,3]`, top level `[]`,
   `"opacity": [1]`). Validate every key defensively in `load_settings` /
   `restore_tool_settings`.

## Medium

5. [x] **Skew crashes for some angle pairs** (`tan(h)·tan(v) = 1`, e.g. 45/45,
   30/60) because both skews are applied in one non-invertible matrix; large
   angles create gigantic surfaces (89° → 28140 px wide). Apply horizontal then
   vertical skew (like the original) and cap the result size.
   `imageops.skew`, `window.on_stretch_skew`.
6. [x] **Images or sizes beyond cairo's 32767 px limit raise uncaught
   `cairo.Error`** (open a 40000×2 PNG, Attributes 40000, big stretch); dialogs
   leak and no message is shown. Catch, warn, and set a sane maximum size.
7. [x] **Selection handles on the right/bottom edge resize the canvas
   instead** (e.g. after Select All). Check selection handles before canvas
   resize handles. `canvas.on_press` / hover.
8. [x] **The canvas-resize hit zone covers the last 2 image pixels** and the
   new size is computed from the pointer, not the grab offset, so clicking
   near the edge shrinks the picture by a pixel. `canvas.resize_handle_at`.
9. [x] **Second mouse button doesn't cancel freehand strokes** (pencil, brush,
   eraser, airbrush, sticker) or a selection move, unlike the shape tools.
10. [x] **Symmetry copies come out dotted on canvases with mixed odd/even
    width/height** (90°/270°/diagonal copies; `round` to even on .5).
    Use `math.floor` in `symmetry.map_points`.
11. [x] **Typing in a text box steals keys from focused widgets.** While a
    text box is open, digits typed in the Opacity entry or Return/Escape in the
    font list go into the picture text. Only route keys to the text tool when
    the canvas has focus. `canvas.handle_key`.
12. [x] **App shortcuts fire while typing in a slider's number entry**
    (Delete clears the selection, Ctrl+Z undoes the picture). Let focused
    editables handle keys first.
13. [x] **Options → Edit Colors always edits palette cell 0.** The colour box
    swallows the click before the window records which cell was chosen.
    `colorbox.on_press` should report the index (signal).
14. [x] **Saving with an auto-added extension skips the overwrite check**
    (`photo` → silently overwrites `photo.png`), and may fail under the snap's
    portal, which only grants the exact picked name. Use the chosen filter to
    set the name before the dialog closes, or confirm again. (code)
15. [x] **Unsupported extensions are written as PNG data** (open `x.gif`,
    Save → PNG bytes in `x.gif`). Force a supported extension or warn.
16. [x] **Replay memory can grow to ~1.5 GB** when drawing over photos
    (≈0.5 MB per frame, thinning only after 3000 frames). Cap by total bytes
    or store frame diffs. `replay.Recorder`.
17. [x] **Print Preview can't work in the strict snap** (GTK launches an
    external previewer that isn't available). Handle the `preview` signal
    in-app or hide the item under `$SNAP`. (code)

## Low

18. [x] Black-and-white mode in Attributes is a sticky global setting:
    after converting one picture, later pictures can't be converted.
19. [x] Typing `inf` in number fields raises `OverflowError` (dialogs stay
    alive; Edit Colors handler raises).
20. [x] Ctrl+V while typing text commits the text and pastes an image.
21. [x] Skewing a selection fills new corners with the background colour
    instead of leaving them transparent (`bg` is never `None`).
22. [x] Thumbnail window closed with Alt+F4 leaves "Show Thumbnail" checked.
23. [x] Help → Keyboard shortcuts text is wrong (Repeat is F4, Select All is
    Ctrl+L, Color Box is Ctrl+A).
24. [x] Cancelling the "Save changes?" prompt still commits the floating
    selection / text; missing recent files stay in the menu; saving a sticker
    can raise unhandled `OSError`.
25. [x] Magnifier click without a prior hover crashes (`self.pos` is None)
    and zooms around the last hover point instead of the click.
26. [x] Sticker opacity is applied once per symmetry copy, so overlaps build
    up past the slider value.
27. [x] Grabbing a selection's handle makes it jump 1 px.
28. [x] A rect selection dragged entirely outside the picture creates a 1-px
    selection; a text box dragged above the picture lands at y=0.
29. [x] Double-clicking on the polygon tool's first click commits a dot.
30. [x] Right-click during a canvas-resize drag starts a tool stroke. (code)
31. [x] Invert ignores semi-transparent pixels; black-and-white makes them
    opaque.
32. [x] GIF palette building is slow with many colours (≈30 s for a photo).
    Cache box spreads in `gif._median_cut`.
33. [x] Main-thread slowness on very large pictures (4000×3000: tolerance
    fill/wand ≈2 s, invert ≈1.7 s, black-and-white ≈4 s).
34. [x] B/I/U buttons take focus from the canvas (caret disappears, input
    method resets).
35. [x] Alt+O is used twice (Options menu and the Opacity slider).
36. [x] Window class is `__main__.py` (set prgname / `StartupWMClass`).
37. [x] The launcher's `python -m` can pick up a `paint98/` folder from the
    current directory (use `python -P`).
38. [x] A number typed in a slider entry without Enter is lost when switching
    tools.
39. [x] The Sticker Book stays open (and acts on a dead window) after its
    main window closes.
