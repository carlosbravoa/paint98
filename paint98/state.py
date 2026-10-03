"""Shared editor state: colours, palette, current tool and tool options."""

from gi.repository import GObject

from .funpaints import FUN_PALETTE, is_fun, solid


def _hex(h):
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


DEFAULT_PALETTE = [_hex(h) for h in (
    # top row
    "000000", "808080", "800000", "808000", "008000", "008080", "000080",
    "800080", "808040", "004040", "0080FF", "004080", "8000FF", "804000",
    # bottom row
    "FFFFFF", "C0C0C0", "FF0000", "FFFF00", "00FF00", "00FFFF", "0000FF",
    "FF00FF", "FFFF80", "00FF80", "80FFFF", "8080FF", "FF0080", "FF8040",
)]

TOOLS = [
    "free_select", "rect_select",
    "eraser", "fill",
    "pick", "magnifier",
    "pencil", "brush",
    "airbrush", "text",
    "line", "curve",
    "rectangle", "polygon",
    "ellipse", "rounded_rect",
    "magic_wand", "sticker",
]

TOOL_NAMES = {
    "free_select": "Free-Form Select",
    "rect_select": "Select",
    "eraser": "Eraser/Color Eraser",
    "fill": "Fill With Color",
    "pick": "Pick Color",
    "magnifier": "Magnifier",
    "pencil": "Pencil",
    "brush": "Brush",
    "airbrush": "Airbrush",
    "text": "Text",
    "line": "Line",
    "curve": "Curve",
    "rectangle": "Rectangle",
    "polygon": "Polygon",
    "ellipse": "Ellipse",
    "rounded_rect": "Rounded Rectangle",
    "magic_wand": "Magic Wand",
    "sticker": "Sticker",
}

TOOL_HELP = {
    "free_select": "Selects a free-form part of the picture to move, copy, or edit.",
    "rect_select": "Selects a rectangular part of the picture to move, copy, or edit.",
    "eraser": "Erases a portion of the picture, using the selected eraser shape.",
    "fill": "Fills an area with the current drawing color.",
    "pick": "Picks up a color from the picture for drawing.",
    "magnifier": "Changes the magnification.",
    "pencil": "Draws a free-form line one pixel wide.",
    "brush": "Draws using a brush with the selected shape and size.",
    "airbrush": "Draws using an airbrush of the selected size.",
    "text": "Inserts text into the picture.",
    "line": "Draws a straight line with the selected line width.",
    "curve": "Draws a curved line with the selected line width.",
    "rectangle": "Draws a rectangle with the selected fill style.",
    "polygon": "Draws a polygon with the selected fill style.",
    "ellipse": "Draws an ellipse with the selected fill style.",
    "rounded_rect": "Draws a rounded rectangle with the selected fill style.",
    "magic_wand": "Selects an area of similar color. Shift+click adds more areas to the selection.",
    "sticker": "Stamps a sticker. Drag to stamp a trail; pick stickers in the Sticker Book.",
}

BLANK_PALETTE = [(255, 255, 255)] * 28

DEFAULT_HELP = "For Help, click Help Topics on the Help Menu."

ERASER_SIZES = [4, 6, 8, 10]
AIRBRUSH_SIZES = [9, 16, 24]
MAGNIFY_LEVELS = [1, 2, 6, 8]
# (kind, size) - kinds: circle, square, slash, backslash
BRUSH_SHAPES = [
    ("circle", 7), ("circle", 4), ("circle", 1),
    ("square", 8), ("square", 5), ("square", 2),
    ("slash", 8), ("slash", 5), ("slash", 2),
    ("backslash", 8), ("backslash", 5), ("backslash", 2),
]


class PaintState(GObject.Object):
    __gsignals__ = {
        "colors-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "palette-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "tool-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "options-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    # Tools that put paint on the picture and therefore have an opacity.
    PAINT_TOOLS = ("eraser", "fill", "pencil", "brush", "airbrush", "text", "line",
                   "curve", "rectangle", "polygon", "ellipse", "rounded_rect", "sticker")

    def __init__(self):
        super().__init__()
        self.fg = (0, 0, 0)
        self.bg = (255, 255, 255)
        self.original_palette = list(DEFAULT_PALETTE)
        # Starts blank (all white) so switching to it is clearly visible.
        self.custom_palette = list(BLANK_PALETTE)
        self.palette_mode = "original"  # "original", "custom" or "fun"
        self.last_plain = "original"     # where the O/C button returns to
        self.tool = "pencil"
        self.prev_tool = "pencil"
        self.transparent = False
        self.eraser_size = 1
        self.eraser_shape = "square"  # or "circle"
        # Pixel sizes driven by the Size slider. Brush and eraser presets in
        # the options box choose a shape and load their size here.
        self.pencil_size = 1
        self.brush_size = BRUSH_SHAPES[1][1]  # matches the default preset below
        self.eraser_px = ERASER_SIZES[self.eraser_size]
        self.sticker = "px:Star"
        self.sticker_size = 48
        self.sticker_recent = ["px:Star", "px:Heart", "px:Sun", "px:Cat"]
        self.fill_mode = 0  # 0 solid, 1 linear gradient, 2 radial gradient
        self.tolerance = 0  # percent (fill and magic wand)
        self.wand_global = False  # magic wand: all similar colours, not just touching ones
        self.opacity = {t: 100 for t in self.PAINT_TOOLS}  # percent, per tool
        self.airbrush_size = 0
        self.magnify = 1  # index into MAGNIFY_LEVELS
        self.brush = 1
        self.line_width = 1
        self.fill_style = 0  # 0 outline, 1 outline+fill, 2 fill only
        self.show_grid = True
        self.symmetry = "off"  # see symmetry.MODES
        self.font_family = "Arial"
        self.font_size = 10
        self.font_bold = False
        self.font_italic = False
        self.font_underline = False

    def set_fg(self, paint):
        # The foreground may be a FunPaint (rainbow, stars...) or a colour.
        self.fg = paint if is_fun(paint) else tuple(paint)
        self.emit("colors-changed")

    def set_bg(self, paint):
        # The background is always a plain colour (eraser, selections...).
        self.bg = solid(paint)
        self.emit("colors-changed")

    @property
    def palette(self):
        if self.palette_mode == "fun":
            return FUN_PALETTE
        if self.palette_mode == "custom":
            return self.custom_palette
        return self.original_palette

    @property
    def use_custom(self):
        return self.palette_mode == "custom"

    def set_palette_mode(self, mode):
        if mode not in ("original", "custom", "fun") or mode == self.palette_mode:
            return
        if mode != "fun":
            self.last_plain = mode
        self.palette_mode = mode
        self.emit("palette-changed")

    def set_use_custom(self, value):
        self.set_palette_mode("custom" if value else "original")

    def set_palette_color(self, index, rgb):
        """Edit a swatch. The original palette never changes: editing it
        switches to the custom palette and edits the same slot there."""
        self.palette_mode = self.last_plain = "custom"
        self.custom_palette[index] = tuple(rgb)
        self.emit("palette-changed")

    def set_palette(self, colors):
        """Load colours into the custom palette and show it."""
        pal = [tuple(c) for c in colors][:28]
        while len(pal) < 28:
            pal.append((255, 255, 255))
        self.custom_palette = pal
        self.palette_mode = self.last_plain = "custom"
        self.emit("palette-changed")

    def tool_opacity(self, tool=None):
        """Opacity of a tool as 0..1 (1 for tools without one)."""
        return self.opacity.get(tool or self.tool, 100) / 100.0

    def set_opacity(self, tool, percent):
        percent = max(1, min(100, int(percent)))
        if tool in self.opacity and self.opacity[tool] != percent:
            self.opacity[tool] = percent
            self.emit("options-changed")

    def set_tool(self, tool):
        if tool == self.tool:
            return
        self.prev_tool = self.tool
        self.tool = tool
        self.emit("tool-changed")

    def choose_brush_preset(self, index):
        self.brush = index
        self.brush_size = BRUSH_SHAPES[index][1]
        self.emit("options-changed")

    def choose_eraser_preset(self, shape, index):
        self.eraser_shape = shape
        self.eraser_size = index
        self.eraser_px = ERASER_SIZES[index]
        self.emit("options-changed")

    SIZE_LIMITS = {"pencil": (1, 50), "brush": (1, 64), "eraser": (2, 64), "sticker": (8, 256)}
    SIZE_ATTRS = {"pencil": "pencil_size", "brush": "brush_size", "eraser": "eraser_px",
                  "sticker": "sticker_size"}

    def choose_sticker(self, sid):
        """Make a sticker current and remember it among the recent ones."""
        self.sticker = sid
        self.sticker_recent = [sid] + [s for s in self.sticker_recent if s != sid][:5]
        if self.tool != "sticker":
            self.set_tool("sticker")
        self.emit("options-changed")

    def tool_size(self, tool=None):
        attr = self.SIZE_ATTRS.get(tool or self.tool)
        return getattr(self, attr) if attr else None

    def set_tool_size(self, tool, value):
        if tool not in self.SIZE_ATTRS:
            return
        lo, hi = self.SIZE_LIMITS[tool]
        self.set_option(self.SIZE_ATTRS[tool], max(lo, min(hi, int(value))))

    def set_option(self, name, value):
        if getattr(self, name) != value:
            setattr(self, name, value)
            self.emit("options-changed")
