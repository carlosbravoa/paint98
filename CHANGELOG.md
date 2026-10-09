# Changelog

Improvements are collected under "Unreleased" and shipped together in the
next snap release.

## Unreleased

## 1.0.4

- Gradient fills: dragging now only traces the direction (a dashed line
  from a start marker to an end marker, plus the reach circle for radial
  gradients); the area is filled once, when the button is released. This
  also removes the slowdown of redrawing the whole fill on every move.
- The tool box has Undo and Redo buttons in its bottom row.
- A single click on the foreground or background swatch opens Edit Colors.
- Edit Colors always shows the colour spectrum and the Hue/Sat/Lum and
  Red/Green/Blue fields; the "Define Custom Colors >>" button is gone.

## 1.0.3

- Ctrl + mouse wheel zooms smoothly in and out (100% to 800%, about 20%
  per notch, settling on whole sizes like 200% when close), keeping the
  spot under the mouse pointer in place. Touchpads zoom continuously.

## 1.0.2 (stable)

- Fill and Magic Wand start with 2% tolerance, so filling an area of a
  painted picture covers its slightly uneven colours instead of looking
  like it did nothing.
- The text box can be resized and moved while you type: drag one of its
  8 handles to resize (the text re-wraps as you drag), or drag its dotted
  frame to move it. The right mouse button cancels the drag.
- Fixed: dragging the picture's resize handle failed to draw its outline
  (regression from the previous bug-fix round).

## 1.0.1 (beta)

- Store description, screenshots and banner.

## 1.0.0 (beta)

- First release in the Snap Store.
