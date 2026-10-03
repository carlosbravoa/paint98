# Ideas

Features that keep the classic look and feel but make Paint surprising and
modern. New tools live in the tool box options, settings in the panel next to
the colour box, and anything bigger in a classic-style dialog or tool window.

Status: `[ ]` to do, `[~]` in progress, `[x]` done.

## Top picks

1. [x] **Replay (timelapse).** Paint records the drawing as you work.
   View → Replay plays it back from an empty canvas; File → Save Replay As…
   exports an animated GIF to share. *(Done: View → Replay… (Ctrl+Shift+R),
   File → Save Replay As…; recording is in memory and restarts on New/Open.)*
2. [x] **Mirror / kaleidoscope drawing.** Symmetry modes (mirror, four-way,
   radial, kaleidoscope) copy every stroke around the centre of the picture.
   *(Done: Symmetry strip next to the colour box and Options → Symmetry;
   works with pencil, brush, airbrush, eraser, lines, curves and shapes.)*
3. [x] **Magic Wand selection.** Click to select every connected pixel of a
   similar colour (same tolerance slider as Fill), then move, recolour or
   delete it. *(Done: new tool in the tool box; Shift+click adds areas; options
   for touching-only or all similar colours; shaped selections show their real
   outline; Image → Recolor Selection (Ctrl+Shift+F) paints a selection with
   the foreground colour or a Fun Color.)*

## For kids

4. [ ] **Stickers (stamp tool).** Pixel-art stamps (stars, animals, sun,
   house…) placed with a click and sized with the Size slider.
5. [ ] **Coloring book.** File → New from Coloring Page… opens line drawings
   made for the fill tool.
6. [ ] **Stroke smoothing.** A stabiliser slider that steadies shaky lines.

## Invisible until you need it

7. [ ] **Pick a colour from anywhere on screen.** Eyedropper that samples
   other windows and the desktop through the desktop portal (works in the snap).
8. [ ] **Transparent background.** Save PNGs with transparency.
9. [ ] **Autosave and recovery.** "Paint found an unsaved picture…" after a
   crash, in a classic dialog.
10. [ ] **Pen tablet pressure.** Size and opacity follow stylus pressure.
11. [ ] **History window.** A small tool window listing every step; click to
    jump back several steps at once.

## Nostalgic surprises

12. [ ] **Tip of the Day** dialog at startup with funny tips and a "Show tips
    at startup" checkbox.
13. [ ] **Optional UI sounds** (original sounds in the classic spirit).
14. [ ] **Screensaver easter egg.** After idling in View Bitmap the picture
    bounces around like the old DVD logo; a Konami code unlocks a hidden
    "3D pipes"-style animation painted over the canvas.

## Bigger projects

15. [ ] **Layers**, presented in a classic tool window.
16. [ ] **Flipbook animation** with onion skinning and a frame strip,
    exported as GIF (shares the GIF encoder with Replay).

## Follow-ups noticed along the way

17. [ ] Movable symmetry centre (drag the centre point on the canvas).
18. [ ] Rewrite git history to drop `paint.png` from the first commit before
    making the repository public.
