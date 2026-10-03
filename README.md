# Paint

A native GNOME paint program that looks and behaves like the classic
Windows 98 Paint: grey 3D chrome, navy title bar, the 16-tool tool box with
its options box, the 28-colour palette, the same menus, shortcuts, status bar
help text and dialogs.

It is written in Python with GTK 3 and cairo. All the chrome is drawn by the
app (`paint98/data/win98.css` plus hand-made pixel art in
`paint98/pixmaps.py`), so it looks the same whatever GTK theme you use.

## Features

| Area | What works |
| --- | --- |
| Tools | Free-form select, select, eraser / colour eraser (right button), fill, pick colour, magnifier, pencil, brush (12 shapes), airbrush, text, line, curve, rectangle, polygon, ellipse, rounded rectangle |
| Mouse | Left button uses the foreground colour, right button the background colour; Shift constrains lines to 45° and shapes to squares/circles; pressing the other button while drawing cancels |
| Selections | Move, Ctrl+drag to copy, Shift+drag to smear, stretch handles, opaque/transparent mode, right-click menu |
| File | New, Open, Save, Save As (PNG, BMP, JPEG, TIFF), Print Preview, Page Setup, Print, recent files, Set As Wallpaper (Tiled/Centered) |
| Edit | Undo, Repeat, Cut, Copy, Paste (system clipboard), Clear Selection, Select All, Copy To, Paste From |
| View | Tool box, colour box, status bar, text toolbar, zoom (normal, large, custom), grid, thumbnail, View Bitmap |
| Image | Flip/Rotate, Stretch/Skew, Invert Colors, Attributes (size, units, black and white), Clear Image, Draw Opaque |
| Options | Edit Colors (basic + custom colours, HSL/RGB editor), Get/Save Colors (`.pal`), Use Custom Palette |
| Beyond the original | Tool settings next to the colour box: opacity for every painting tool, size for pencil, brush and eraser (the brush and eraser presets pick a shape and starting size), tolerance for fill; linear and radial gradient fills (drag from the click point, foreground to background colour); round eraser shapes; switch between the original palette and your own custom palette (button at the right of the colour box); Fun Colors (rainbow button, or Options → Fun Colors): rainbow, pastel, fire, ocean, forest, neon and sunset paints that change colour as you draw, plus candy stripes, polka dots, stars, hearts, confetti, checkerboard and gold glitter patterns, and a row of bright crayon colours — they work with every painting tool; Replay: View → Replay… plays back how the picture was drawn and File → Save Replay As… exports an animated GIF; Symmetry: mirror, four-way, radial and kaleidoscope drawing (strip next to the colour box, or Options → Symmetry); Magic Wand selection with tolerance (Shift+click to add areas) and Image → Recolor Selection; Stickers: a Sticker Book (Ctrl+B) with classic pixel-art stickers, colour emoji and your own stickers saved from selections |

Keyboard shortcuts follow the original, including its quirks: Select All is
Ctrl+L and Ctrl+A toggles the colour box.

## Running from source

Needs Python 3, PyGObject, pycairo and GTK 3:

```sh
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0
./bin/paint98 [picture.png]
```

## Building the snap

```sh
snapcraft pack
sudo snap install --dangerous paint98_1.0.0_amd64.snap
paint98
```

The snap uses `core24` with the `gnome` extension. It is strictly confined:
files are opened through the desktop portal, and the wallpaper is written to
`~/snap/paint98/common/wallpaper/` and applied through GSettings.

## Development helpers

* `tools/gen_assets.py` regenerates the PNGs used by the stylesheet and the
  app icon.
* `tools/shot.py OUT.png [script.py]` renders the window off-screen to a PNG,
  optionally after running a script that drives the tools.
* `tools/live_shot.py OUTDIR [menu-index]` (with `GDK_BACKEND=x11`) captures
  the real window and an open menu.

## Ideas

Planned features are tracked in [IDEAS.md](IDEAS.md).

## License

MIT. See [LICENSE](LICENSE).
