"""Every tool, driven with simulated mouse input through the canvas.

Each test draws on a white 120 x 90 picture (black foreground, white
background) and checks the pixels that result, and that undo/redo restore
the picture exactly."""

import unittest

from .helpers import (BLACK, BLUE, GREEN, RED, SHIFT, WHITE, CTRL, WindowTestCase, count_color,
                      flush_events, paint_rect)

from paint98 import funpaints, imageops  # noqa: E402
from paint98.state import TOOLS  # noqa: E402


class FreehandTests(WindowTestCase):
    def test_pencil_draws_a_one_pixel_line(self):
        self.use("pencil")
        before = self.snapshot()
        self.drag([(10, 10), (30, 10), (30, 20)])
        self.assertEqual(count_color(self.doc.surface, BLACK), 21 + 10)
        self.assertEqual(self.px(20, 10), BLACK)
        self.assertEqual(self.px(20, 11), WHITE)
        self.assertEqual(self.doc.history()[0][-1], "Pencil")
        self.assertUndoRestores(before)

    def test_right_button_uses_background_colour(self):
        self.state.set_bg(RED)
        self.use("pencil")
        self.drag([(5, 5), (15, 5)], button=3)
        self.assertEqual(count_color(self.doc.surface, RED), 11)

    def test_fast_moves_leave_no_gaps(self):
        self.use("pencil")
        self.drag([(0, 0), (119, 89)])
        self.assertEqual(count_color(self.doc.surface, BLACK), 120)

    def test_second_button_cancels_the_stroke(self):
        self.use("pencil")
        before = self.snapshot()
        self.press(10, 10)
        self.move(40, 10)
        self.press(40, 10, button=3)
        self.release(40, 10)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.doc.can_undo())
        self.assertFalse(self.doc.can_redo())

    def test_thick_pencil(self):
        self.use("pencil", pencil_size=5)
        self.click(50, 50)
        n = count_color(self.doc.surface, BLACK)
        self.assertGreater(n, 12)
        self.assertLessEqual(n, 25)

    def test_brush_shapes(self):
        for preset in range(12):
            with self.subTest(preset=preset):
                self.doc.new(self.W, self.H)
                self.state.choose_brush_preset(preset)
                self.use("brush")
                self.drag([(20, 20), (60, 40)])
                self.assertGreater(count_color(self.doc.surface, BLACK), 40)

    def test_opacity_blends(self):
        self.state.set_opacity("pencil", 50)
        self.use("pencil")
        self.drag([(10, 10), (20, 10)])
        r, g, b = self.px(15, 10)
        self.assertTrue(120 <= r <= 135 and r == g == b, (r, g, b))
        # Going back over the stroke does not build up past the opacity.
        self.drag([(10, 10), (20, 10), (10, 10)])
        self.assertTrue(55 <= self.px(15, 10)[0] <= 70)

    def test_fun_paint(self):
        self.state.set_fg(funpaints.FUN_PAINTS[0])
        self.use("brush")
        self.drag([(10, 40), (110, 40)])
        painted = self.W * self.H - count_color(self.doc.surface, WHITE)
        self.assertGreater(painted, 100)

    def test_eraser_paints_background(self):
        paint_rect(self.doc.surface, 0, 0, self.W, self.H, BLUE)
        self.state.set_bg(GREEN)
        self.use("eraser")
        before = self.snapshot()
        self.drag([(10, 10), (50, 10)])
        self.assertEqual(self.px(30, 10), GREEN)
        self.assertEqual(self.px(30, 40), BLUE)
        self.assertUndoRestores(before)

    def test_colour_eraser_only_replaces_foreground(self):
        paint_rect(self.doc.surface, 0, 0, 60, self.H, RED)
        paint_rect(self.doc.surface, 60, 0, 60, self.H, BLUE)
        self.state.set_fg(RED)
        self.state.set_bg(WHITE)
        self.use("eraser")
        self.drag([(40, 30), (80, 30)], button=3)
        self.assertEqual(self.px(50, 30), WHITE)  # red under the eraser: replaced
        self.assertEqual(self.px(70, 30), BLUE)   # other colours: untouched

    def test_airbrush_sprays_near_the_pointer(self):
        self.use("airbrush")
        before = self.snapshot()
        self.press(60, 45)
        for _ in range(10):
            self.move(60, 45)
        self.release(60, 45)
        self.assertIsNone(self.canvas.tool.timer)
        n = count_color(self.doc.surface, BLACK)
        self.assertGreater(n, 5)
        self.assertEqual(n, count_color(self.doc.surface, BLACK, (55, 40, 66, 51)))
        self.assertUndoRestores(before)


class ShapeTests(WindowTestCase):
    def test_line(self):
        self.use("line")
        before = self.snapshot()
        self.drag([(10, 10), (50, 50), (100, 20)])
        self.assertIsNone(self.canvas.preview)
        self.assertEqual(self.px(10, 10), BLACK)
        self.assertEqual(self.px(100, 20), BLACK)
        self.assertEqual(self.px(50, 50), WHITE)  # only the final line is drawn
        self.assertEqual(count_color(self.doc.surface, BLACK), 91)
        self.assertUndoRestores(before)

    def test_line_preview_before_release(self):
        self.use("line")
        self.press(10, 10)
        self.move(60, 10)
        self.assertIsNotNone(self.canvas.preview)
        self.assertEqual(count_color(self.doc.surface, BLACK), 0)
        self.release(60, 10)

    def test_shift_constrains_line_to_45_degrees(self):
        self.use("line")
        self.drag([(10, 10), (52, 50)], mods=SHIFT)
        black = count_color(self.doc.surface, BLACK)
        self.assertTrue(self.px(50, 50) == BLACK or self.px(52, 52) == BLACK)
        self.assertIn(black, (41, 42, 43))

    def test_line_width(self):
        self.use("line", line_width=5)
        self.drag([(10, 40), (100, 40)])
        self.assertEqual(self.px(50, 38), BLACK)
        self.assertEqual(self.px(50, 43), WHITE)

    def test_rectangle_styles(self):
        self.state.set_bg(RED)
        expected = {0: (BLACK, WHITE), 1: (BLACK, RED), 2: (BLACK, BLACK)}
        for style, (edge, inside) in expected.items():
            with self.subTest(style=style):
                self.doc.new(self.W, self.H)
                self.use("rectangle", fill_style=style)
                self.drag([(10, 10), (40, 30)])
                self.assertEqual(self.px(10, 10), edge)
                self.assertEqual(self.px(40, 30), edge)
                self.assertEqual(self.px(25, 20), inside)
                self.assertEqual(self.px(41, 31), WHITE)

    def test_rectangle_outline_pixel_count(self):
        self.use("rectangle", fill_style=0, line_width=1)
        self.drag([(10, 10), (19, 19)])
        self.assertEqual(count_color(self.doc.surface, BLACK), 36)

    def test_shift_makes_a_square(self):
        self.use("rectangle", fill_style=2)
        self.drag([(10, 10), (50, 25)], mods=SHIFT)  # squares to the longer side
        self.assertEqual(count_color(self.doc.surface, BLACK), 41 * 41)

    def test_rectangle_dragged_backwards(self):
        self.use("rectangle", fill_style=2)
        self.drag([(40, 30), (10, 10)])
        self.assertEqual(count_color(self.doc.surface, BLACK), 31 * 21)

    def test_ellipse_and_rounded_rect(self):
        for tool in ("ellipse", "rounded_rect"):
            with self.subTest(tool):
                self.doc.new(self.W, self.H)
                self.use(tool, fill_style=2)
                before = self.snapshot()
                self.drag([(10, 10), (70, 50)])
                n = count_color(self.doc.surface, BLACK)
                self.assertLess(n, 61 * 41)  # corners are cut
                self.assertGreater(n, 61 * 41 * 0.7)
                self.assertEqual(self.px(40, 30), BLACK)
                self.assertEqual(self.px(10, 10), WHITE)
                self.assertUndoRestores(before)

    def test_curve_takes_three_steps(self):
        self.use("curve")
        before = self.snapshot()
        self.drag([(10, 70), (110, 70)])
        self.assertTrue(self.canvas.tool.is_busy())
        self.assertEqual(self.snapshot(), before)  # still only a preview
        self.drag([(60, 10)])
        self.assertTrue(self.canvas.tool.is_busy())
        self.drag([(60, 10)])
        self.assertFalse(self.canvas.tool.is_busy())
        self.assertEqual(self.px(10, 70), BLACK)
        self.assertEqual(self.px(110, 70), BLACK)
        self.assertEqual(self.px(60, 70), WHITE)  # bent away from the straight line
        self.assertGreater(count_color(self.doc.surface, BLACK, (0, 0, self.W, 60)), 20)
        self.assertUndoRestores(before)

    def test_unfinished_curve_is_committed_on_tool_change(self):
        self.use("curve")
        self.drag([(10, 70), (110, 70)])
        self.state.set_tool("pencil")
        self.assertEqual(self.px(60, 70), BLACK)
        self.assertTrue(self.doc.can_undo())

    def test_undo_cancels_unfinished_curve(self):
        self.use("curve")
        self.drag([(10, 70), (110, 70)])
        self.assertTrue(self.win.toolbox.action_enabled("undo"))
        self.win.canvas_undo()
        self.assertFalse(self.canvas.tool.is_busy())
        self.assertIsNone(self.canvas.preview)
        self.assertFalse(self.doc.can_undo())

    def test_polygon_closes_on_double_click(self):
        self.use("polygon", fill_style=2)
        before = self.snapshot()
        self.drag([(10, 10), (100, 10)])
        self.click(100, 80)
        self.press(10, 80)
        self.release(10, 80)
        self.double_click(10, 80)
        self.assertFalse(self.canvas.tool.is_busy())
        self.assertEqual(self.px(55, 45), BLACK)
        self.assertUndoRestores(before)

    def test_polygon_closes_near_first_point(self):
        self.use("polygon", fill_style=0)
        self.drag([(10, 10), (100, 10)])
        self.click(55, 80)
        self.click(11, 11)
        self.assertFalse(self.canvas.tool.is_busy())
        self.assertEqual(self.px(55, 45), WHITE)  # outline only
        self.assertEqual(self.px(55, 10), BLACK)
        self.assertEqual(self.px(32, 45), BLACK)  # closing edge drawn

    def test_polygon_filled_with_background(self):
        self.state.set_bg(GREEN)
        self.use("polygon", fill_style=1)
        self.drag([(10, 10), (100, 10)])
        self.click(55, 80)
        self.click(10, 10)
        self.assertEqual(self.px(55, 30), GREEN)
        self.assertEqual(self.px(55, 10), BLACK)


class FillTests(WindowTestCase):
    def test_fill_stays_inside_the_lines(self):
        self.use("rectangle", fill_style=0)
        self.drag([(10, 10), (50, 50)])
        self.use("fill", fill_mode=0)
        self.state.set_fg(RED)
        before = self.snapshot()
        self.click(30, 30)
        self.assertEqual(count_color(self.doc.surface, RED), 39 * 39)
        self.assertEqual(self.px(5, 5), WHITE)
        self.assertEqual(self.doc.history()[0][-1], "Fill With Color")
        self.assertUndoRestores(before)

    def test_filling_with_the_same_colour_is_no_step(self):
        self.use("fill", fill_mode=0, tolerance=0)
        self.state.set_fg(WHITE)
        self.click(30, 30)
        self.assertFalse(self.doc.can_undo())

    def test_tolerance(self):
        paint_rect(self.doc.surface, 0, 0, 60, self.H, (250, 250, 250))
        self.state.set_fg(RED)
        self.use("fill", fill_mode=0, tolerance=0)
        self.click(100, 10)
        self.assertEqual(count_color(self.doc.surface, RED), 60 * self.H)
        self.win.canvas_undo()
        self.state.tolerance = 5
        self.click(100, 10)
        self.assertEqual(count_color(self.doc.surface, RED), self.W * self.H)

    def test_click_outside_does_nothing(self):
        self.use("fill", fill_mode=0)
        self.click(200, 200)
        self.assertFalse(self.doc.can_undo())

    def test_linear_gradient_fills_on_release(self):
        self.state.set_fg(BLACK)
        self.state.set_bg(WHITE)
        self.use("fill", fill_mode=1)
        before = self.snapshot()
        self.press(0, 45)
        self.move(60, 45)
        self.assertTrue(self.canvas.tool.is_busy())
        self.assertEqual(self.snapshot(), before)  # only traced while dragging
        self.render(self.canvas)  # the trace overlay draws without errors
        self.release(119, 45)
        self.assertFalse(self.canvas.tool.is_busy())
        left, mid, right = self.px(0, 45)[0], self.px(60, 45)[0], self.px(119, 45)[0]
        self.assertLess(left, 10)
        self.assertGreater(right, 245)
        self.assertTrue(110 < mid < 145, mid)
        self.assertEqual(self.px(60, 0), self.px(60, 89))  # same along the gradient's normal
        self.assertUndoRestores(before)

    def test_radial_gradient(self):
        self.use("fill", fill_mode=2)
        self.drag([(60, 45), (100, 45)])
        self.assertLess(self.px(60, 45)[0], 10)
        self.assertGreater(self.px(119, 45)[0], 245)
        self.assertEqual(self.px(40, 45), self.px(80, 45))

    def test_gradient_click_spans_the_area(self):
        self.use("fill", fill_mode=1)
        self.click(60, 45)
        self.assertLess(self.px(0, 10)[0], 10)
        self.assertGreater(self.px(119, 10)[0], 240)

    def test_undo_while_tracing_a_gradient(self):
        self.use("fill", fill_mode=1)
        self.press(10, 10)
        self.move(50, 50)
        self.win.canvas_undo()
        self.assertFalse(self.canvas.tool.is_busy())
        self.release(50, 50)
        self.assertFalse(self.doc.can_undo())
        self.assertEqual(count_color(self.doc.surface, WHITE), self.W * self.H)


class ColourPickTests(WindowTestCase):
    def test_pick_colour_and_return_to_previous_tool(self):
        paint_rect(self.doc.surface, 0, 0, 10, 10, RED)
        paint_rect(self.doc.surface, 10, 0, 10, 10, BLUE)
        self.use("brush")
        self.use("pick")
        self.click(5, 5)
        self.assertEqual(self.state.fg, RED)
        self.click(15, 5, button=3)
        self.assertEqual(self.state.bg, BLUE)
        flush_events()
        self.assertEqual(self.state.tool, "brush")
        self.assertFalse(self.doc.can_undo())

    def test_magnifier_zooms_in_and_out(self):
        self.use("magnifier")
        self.state.magnify = 2  # 6x
        self.click(60, 45)
        self.assertEqual(self.canvas.zoom, 6)
        flush_events()
        self.use("magnifier")
        self.click(60, 45)
        self.assertEqual(self.canvas.zoom, 1)

    def test_drawing_when_zoomed(self):
        self.canvas.set_zoom(4)
        self.use("pencil")
        self.drag([(10, 10), (20, 10)])
        self.assertEqual(count_color(self.doc.surface, BLACK), 11)
        self.assertEqual(self.px(15, 10), BLACK)


class TextTests(WindowTestCase):
    def type_text(self, text):
        self.canvas.on_im_commit(self.canvas.im, text)

    def test_type_and_place_text(self):
        self.use("text")
        before = self.snapshot()
        self.drag([(10, 10), (110, 60)])
        tool = self.canvas.tool
        self.assertTrue(tool.is_busy())
        self.assertTrue(self.canvas.text_active())
        self.type_text("Hello")
        self.assertEqual(tool.text, "Hello")
        self.render()
        self.assertEqual(self.snapshot(), before)  # not on the picture yet
        self.click(5, 80)  # outside the box: place it
        self.assertFalse(tool.is_busy())
        self.assertGreater(count_color(self.doc.surface, BLACK, (10, 10, 111, 61)), 10)
        self.assertEqual(count_color(self.doc.surface, BLACK, (0, 61, self.W, self.H)), 0)
        self.assertEqual(self.doc.history()[0][-1], "Text")
        self.assertUndoRestores(before)

    def test_empty_box_adds_no_step(self):
        self.use("text")
        self.drag([(10, 10), (110, 60)])
        self.click(5, 80)
        self.assertFalse(self.doc.can_undo())

    def test_undo_removes_the_open_box(self):
        self.use("text")
        self.drag([(10, 10), (110, 60)])
        self.type_text("Hi")
        self.win.canvas_undo()
        self.assertFalse(self.canvas.tool.is_busy())
        self.assertFalse(self.doc.can_undo())
        self.assertEqual(count_color(self.doc.surface, WHITE), self.W * self.H)

    def test_box_can_be_moved(self):
        self.use("text")
        self.drag([(10, 10), (60, 40)])
        tool = self.canvas.tool
        x, y, w, h = tool.box
        part = None
        # Find a spot on the dotted frame (between the handles).
        for fx in range(x - 3, x + 3):
            self.move(fx, y + h // 2 + 3)
            if tool.box_part_at(fx, y + h // 2 + 3) == "frame":
                part = (fx, y + h // 2 + 3)
                break
        self.assertIsNotNone(part, "no frame spot found")
        self.drag([part, (part[0] + 20, part[1] + 10)])
        self.assertEqual(tool.box[:2], [x + 20, y + 10])


class SelectionTests(WindowTestCase):
    def select(self, x0, y0, x1, y1):
        self.use("rect_select")
        self.drag([(x0, y0), (x1, y1)])
        return self.canvas.selection

    def test_rectangle_selection(self):
        sel = self.select(10, 10, 29, 19)
        self.assertIsNotNone(sel)
        self.assertEqual((sel.x, sel.y, sel.w, sel.h), (10, 10, 20, 10))
        self.assertFalse(self.doc.can_undo())  # selecting changes nothing

    def test_selection_is_cut_to_the_picture(self):
        sel = self.select(100, 80, 300, 300)
        self.assertEqual((sel.x, sel.y, sel.w, sel.h), (100, 80, 20, 10))

    def test_move_selection(self):
        paint_rect(self.doc.surface, 10, 10, 10, 10, RED)
        self.state.set_bg(WHITE)
        before = self.snapshot()
        self.select(10, 10, 19, 19)
        self.drag([(15, 15), (65, 45)])
        self.canvas.commit_selection()
        self.assertEqual(self.px(15, 15), WHITE)
        self.assertEqual(count_color(self.doc.surface, RED, (60, 40, 70, 50)), 100)
        self.assertEqual(self.doc.history()[0][-1], "Move Selection")
        self.assertUndoRestores(before)

    def test_ctrl_drag_copies(self):
        paint_rect(self.doc.surface, 10, 10, 10, 10, RED)
        self.select(10, 10, 19, 19)
        self.drag([(15, 15), (65, 45)], mods=CTRL)
        self.canvas.commit_selection()
        self.assertEqual(count_color(self.doc.surface, RED), 200)

    def test_transparent_selection_lets_background_through(self):
        paint_rect(self.doc.surface, 60, 40, 30, 30, BLUE)
        paint_rect(self.doc.surface, 10, 10, 10, 10, RED)
        paint_rect(self.doc.surface, 12, 12, 6, 6, WHITE)
        self.state.transparent = True
        self.select(10, 10, 19, 19)
        self.drag([(11, 11), (61, 41)])
        self.canvas.commit_selection()
        self.assertEqual(self.px(65, 45), BLUE)  # white hole shows what's below
        self.assertEqual(self.px(60, 40), RED)

    def test_free_form_selection(self):
        paint_rect(self.doc.surface, 0, 0, self.W, self.H, RED)
        self.use("free_select")
        self.drag([(10, 10), (50, 10), (50, 50), (10, 50), (10, 10)])
        sel = self.canvas.selection
        self.assertIsNotNone(sel)
        self.assertIsNotNone(sel.mask)
        self.assertEqual((sel.x, sel.y), (10, 10))

    def test_magic_wand_selects_an_area(self):
        paint_rect(self.doc.surface, 20, 20, 30, 20, RED)
        paint_rect(self.doc.surface, 80, 20, 10, 10, RED)
        self.use("magic_wand", wand_global=False)
        self.click(30, 30)
        sel = self.canvas.selection
        self.assertEqual((sel.x, sel.y, sel.w, sel.h), (20, 20, 30, 20))
        self.click(85, 25, mods=SHIFT)  # add the second area
        sel = self.canvas.selection
        self.assertEqual((sel.x, sel.y, sel.w, sel.h), (20, 20, 70, 20))

    def test_magic_wand_global(self):
        paint_rect(self.doc.surface, 20, 20, 10, 10, RED)
        paint_rect(self.doc.surface, 80, 50, 10, 10, RED)
        self.use("magic_wand", wand_global=True)
        self.click(25, 25)
        sel = self.canvas.selection
        self.assertEqual((sel.x, sel.y, sel.w, sel.h), (20, 20, 70, 40))

    def test_switching_tool_drops_the_selection_in_place(self):
        paint_rect(self.doc.surface, 10, 10, 10, 10, RED)
        self.select(10, 10, 19, 19)
        self.drag([(15, 15), (45, 15)])
        self.state.set_tool("pencil")
        self.assertIsNone(self.canvas.selection)
        self.assertEqual(count_color(self.doc.surface, RED, (40, 10, 50, 20)), 100)

    def test_undo_while_moving_puts_the_picture_back(self):
        paint_rect(self.doc.surface, 10, 10, 10, 10, RED)
        before = self.snapshot()
        self.select(10, 10, 19, 19)
        self.drag([(15, 15), (45, 15)])
        self.win.canvas_undo()
        self.assertIsNone(self.canvas.selection)
        self.assertEqual(self.snapshot(), before)


class StickerTests(WindowTestCase):
    def test_stamp_and_trail(self):
        self.use("sticker", sticker_size=24)
        before = self.snapshot()
        self.click(60, 45)
        one = self.W * self.H - count_color(self.doc.surface, WHITE)
        self.assertGreater(one, 50)
        self.assertEqual(count_color(self.doc.surface, WHITE, (0, 0, 40, self.H)), 40 * self.H)
        self.assertUndoRestores(before)
        self.doc.new(self.W, self.H)
        self.drag([(15, 45), (105, 45)])
        trail = self.W * self.H - count_color(self.doc.surface, WHITE)
        self.assertGreater(trail, one * 3)
        self.assertEqual(len(self.doc.undo_stack), 1)  # the trail is one step


class SymmetryTests(WindowTestCase):
    def mirrored(self, x, y):
        return self.W - 1 - x, y

    def test_mirror_repeats_strokes(self):
        self.state.symmetry = "mirror"
        self.use("pencil")
        self.drag([(10, 10), (30, 20)])
        self.assertEqual(count_color(self.doc.surface, BLACK), 2 * 21)
        self.assertEqual(self.px(*self.mirrored(10, 10)), BLACK)
        self.assertEqual(self.px(*self.mirrored(30, 20)), BLACK)

    def test_every_mode_paints_copies(self):
        copies = {"mirror": 2, "quad": 4, "radial6": 6, "kaleido8": 8}
        self.doc.new(100, 100)
        for mode, n in copies.items():
            with self.subTest(mode):
                self.doc.new(100, 100)
                self.state.symmetry = mode
                self.use("rectangle", fill_style=2)
                self.drag([(20, 5), (24, 9)])
                # Rotated copies may lose a few pixels to rounding.
                self.assertGreaterEqual(count_color(self.doc.surface, BLACK), 25 * n * 0.75)

    def test_fill_ignores_symmetry(self):
        self.state.symmetry = "mirror"
        self.state.set_fg(RED)
        self.use("fill", fill_mode=0)
        self.click(5, 5)
        self.assertEqual(count_color(self.doc.surface, RED), self.W * self.H)


class AllToolsTests(WindowTestCase):
    """Every tool survives a full press/drag/release, a cancel and a redraw
    at every zoom level, without exceptions in callbacks."""

    def test_every_tool_handles_input_and_drawing(self):
        for zoom in (1, 4):
            self.canvas.set_zoom(zoom)
            for tool in TOOLS:
                with self.subTest(tool=tool, zoom=zoom):
                    self.use(tool)
                    self.move(30, 30)
                    self.render(self.canvas)
                    self.press(20, 20)
                    self.move(40, 30)
                    self.render(self.canvas)
                    self.release(50, 40)
                    self.render(self.canvas)
                    self.canvas.commit_all()
                    self.press(60, 60, button=3)
                    self.release(60, 60, button=3)
                    self.canvas.commit_all()
                    self.canvas.on_leave(self.canvas, None)
                    flush_events()
        self.canvas.set_zoom(1)

    def test_every_tool_ignores_clicks_outside(self):
        for tool in TOOLS:
            with self.subTest(tool=tool):
                self.use(tool)
                self.drag([(-50, -50), (-40, -45)])
                self.canvas.commit_all()
                flush_events()
        imageops.get_pixel(self.doc.surface, 0, 0)


if __name__ == "__main__":
    unittest.main()
