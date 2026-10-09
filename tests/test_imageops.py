"""Pixel operations: transforms, masks, flood fill regions and line maths."""

import unittest

from . import helpers  # noqa: F401  (isolated home)
from .helpers import BLACK, BLUE, GREEN, RED, WHITE, count_color, filled, paint_rect, pixel, surface_bytes

from paint98 import imageops


def mask_count(mask):
    """Number of fully set pixels in an A8 mask."""
    mask.flush()
    w, h, stride = mask.get_width(), mask.get_height(), mask.get_stride()
    data = bytes(mask.get_data())
    return sum(data[y * stride:y * stride + w].count(255) for y in range(h))


def mask_at(mask, x, y):
    mask.flush()
    return bytes(mask.get_data())[y * mask.get_stride() + x]


def quadrants(w=4, h=2):
    """w x h picture: left half red, right half blue, top-left pixel green."""
    s = filled(w, h, RED)
    paint_rect(s, w // 2, 0, w - w // 2, h, BLUE)
    paint_rect(s, 0, 0, 1, 1, GREEN)
    return s


class PixelTests(unittest.TestCase):
    def test_pixel_round_trip(self):
        for rgb in (BLACK, WHITE, (1, 2, 3), (255, 128, 0)):
            self.assertEqual(imageops.pixel_to_rgb(imageops.rgb_to_pixel(rgb)), rgb)

    def test_new_surface_fill_and_minimum_size(self):
        s = imageops.new_surface(3, 2, RED)
        self.assertEqual((s.get_width(), s.get_height()), (3, 2))
        self.assertEqual(count_color(s, RED), 6)
        self.assertEqual(imageops.new_surface(0, 0).get_width(), 1)

    def test_get_pixel_outside_is_none(self):
        s = filled(2, 2)
        self.assertIsNone(pixel(s, 2, 0))
        self.assertIsNone(pixel(s, -1, 0))

    def test_copy_surface_is_independent_and_can_crop(self):
        s = quadrants()
        c = imageops.copy_surface(s)
        paint_rect(s, 0, 0, 4, 2, BLACK)
        self.assertEqual(pixel(c, 0, 0), GREEN)
        part = imageops.copy_surface(c, 2, 0, 2, 2)
        self.assertEqual((part.get_width(), part.get_height()), (2, 2))
        self.assertEqual(count_color(part, BLUE), 4)

    def test_size_limits(self):
        imageops.check_size(imageops.MAX_SIDE, 10)
        with self.assertRaises(imageops.TooBig):
            imageops.check_size(imageops.MAX_SIDE + 1, 10)
        with self.assertRaises(imageops.TooBig):
            imageops.check_size(10000, 10000)  # over MAX_PIXELS
        with self.assertRaises(imageops.TooBig):
            imageops.new_surface(imageops.MAX_SIDE + 1, 1)


class TransformTests(unittest.TestCase):
    def test_flip_horizontal_and_vertical(self):
        s = quadrants()
        h = imageops.flip(s, True)
        self.assertEqual(pixel(h, 3, 0), GREEN)
        self.assertEqual(pixel(h, 0, 1), BLUE)
        v = imageops.flip(s, False)
        self.assertEqual(pixel(v, 0, 1), GREEN)
        self.assertEqual(surface_bytes(imageops.flip(h, True)), surface_bytes(s))

    def test_rotate(self):
        s = quadrants(4, 2)
        r90 = imageops.rotate(s, 90)
        self.assertEqual((r90.get_width(), r90.get_height()), (2, 4))
        self.assertEqual(pixel(r90, 1, 0), GREEN)  # clockwise: top-left goes top-right
        r270 = imageops.rotate(s, 270)
        self.assertEqual(pixel(r270, 0, 3), GREEN)
        r180 = imageops.rotate(s, 180)
        self.assertEqual(pixel(r180, 3, 1), GREEN)
        self.assertEqual(surface_bytes(imageops.rotate(r90, 270)), surface_bytes(s))
        self.assertEqual(surface_bytes(imageops.rotate(s, 360)), surface_bytes(s))

    def test_scale_nearest_neighbour(self):
        s = quadrants(4, 2)
        big = imageops.scale(s, 8, 4)
        self.assertEqual((big.get_width(), big.get_height()), (8, 4))
        self.assertEqual(count_color(big, GREEN), 4)
        self.assertEqual(count_color(big, BLUE), 16)
        small = imageops.scale(s, 2, 1)
        self.assertEqual(pixel(small, 1, 0), BLUE)
        with self.assertRaises(imageops.TooBig):
            imageops.scale(s, imageops.MAX_SIDE + 1, 1)

    def test_skew_keeps_every_pixel(self):
        # Edges in their own colours: a lost or doubled row/column shows up.
        s = filled(10, 10, RED)
        paint_rect(s, 0, 0, 1, 10, GREEN)
        paint_rect(s, 9, 0, 1, 10, BLUE)
        paint_rect(s, 0, 0, 10, 1, BLACK)
        for kh, kv in ((45, 0), (0, 45), (-45, 0), (30, 30), (10, -20), (60, 0), (-89, 0)):
            out = imageops.skew(s, kh, kv, bg=WHITE)
            counts = [count_color(out, c) for c in (RED, GREEN, BLUE, BLACK)]
            self.assertEqual(counts, [72, 9, 9, 10], "skew %d, %d" % (kh, kv))

    def test_skew_size_and_corners(self):
        s = filled(10, 10, RED)
        out = imageops.skew(s, 45, 0, bg=WHITE)
        self.assertEqual((out.get_width(), out.get_height()), (19, 10))
        self.assertEqual(pixel(out, 18, 0), WHITE)
        clear = imageops.skew(s, 45, 0)  # no background: transparent corners
        self.assertEqual(mask_at(imageops.alpha_mask(clear), 18, 0), 0)
        same = imageops.skew(s, 0, 0)
        self.assertEqual(surface_bytes(same), surface_bytes(s))

    def test_invert_twice_is_identity(self):
        s = quadrants()
        orig = surface_bytes(s)
        imageops.invert(s)
        self.assertEqual(pixel(s, 0, 0), (255, 0, 255))
        self.assertEqual(pixel(s, 3, 0), (255, 255, 0))
        imageops.invert(s)
        self.assertEqual(surface_bytes(s), orig)

    def test_black_and_white(self):
        s = filled(3, 1, (250, 250, 250))
        paint_rect(s, 1, 0, 1, 1, (10, 10, 10))
        paint_rect(s, 2, 0, 1, 1, (255, 255, 0))  # bright yellow
        imageops.to_black_and_white(s)
        self.assertEqual([pixel(s, x, 0) for x in range(3)], [WHITE, BLACK, WHITE])

    def test_key_out_makes_colour_transparent(self):
        s = quadrants()
        out = imageops.key_out(s, BLUE)
        a = imageops.alpha_mask(out)
        self.assertEqual(mask_count(a), 4)
        self.assertEqual(mask_at(a, 3, 0), 0)
        self.assertEqual(mask_at(a, 0, 0), 255)


class MaskTests(unittest.TestCase):
    def test_region_mask_is_contiguous(self):
        s = filled(10, 10, WHITE)
        paint_rect(s, 5, 0, 1, 10, BLACK)  # wall splits the picture in two
        mask, bbox = imageops.region_mask(s, 0, 0)
        self.assertEqual(mask_count(mask), 50)
        self.assertEqual(bbox, (0, 0, 4, 9))
        self.assertEqual(mask_at(mask, 7, 7), 0)

    def test_region_mask_follows_holes_and_bends(self):
        s = filled(9, 9, WHITE)
        # A U shape: the region must wind around it.
        paint_rect(s, 2, 2, 5, 1, BLACK)
        paint_rect(s, 2, 2, 1, 5, BLACK)
        paint_rect(s, 6, 2, 1, 5, BLACK)
        mask, _ = imageops.region_mask(s, 4, 4)
        self.assertEqual(mask_count(mask), 81 - 13)

    def test_region_mask_tolerance(self):
        s = filled(4, 1, (100, 100, 100))
        paint_rect(s, 2, 0, 2, 1, (104, 104, 104))
        self.assertEqual(mask_count(imageops.region_mask(s, 0, 0, 0)[0]), 2)
        self.assertEqual(mask_count(imageops.region_mask(s, 0, 0, 2)[0]), 4)  # 2% = 5 levels
        self.assertEqual(mask_count(imageops.region_mask(s, 0, 0, 100)[0]), 4)

    def test_region_mask_outside_is_none(self):
        self.assertIsNone(imageops.region_mask(filled(3, 3), 3, 0))
        self.assertIsNone(imageops.region_mask(filled(3, 3), -1, 0))

    def test_similar_mask_is_global(self):
        s = filled(10, 10, WHITE)
        paint_rect(s, 0, 0, 2, 2, RED)
        paint_rect(s, 8, 8, 2, 2, RED)
        mask, bbox = imageops.similar_mask(s, 0, 0)
        self.assertEqual(mask_count(mask), 8)
        self.assertEqual(bbox, (0, 0, 9, 9))

    def test_color_mask(self):
        self.assertEqual(mask_count(imageops.color_mask(quadrants(), BLUE)), 4)

    def test_alpha_edges_is_the_outline(self):
        s = imageops.new_surface(5, 5)  # transparent
        paint_rect(s, 1, 1, 3, 3, RED)
        self.assertEqual(mask_count(imageops.alpha_edges(s)), 8)

    def test_bytes_to_mask_handles_stride(self):
        w, h = 3, 2  # stride is padded to 4
        mask = imageops.bytes_to_mask(bytes([255, 0, 255, 0, 255, 0]), w, h)
        self.assertEqual([mask_at(mask, x, y) for y in range(h) for x in range(w)], [255, 0, 255, 0, 255, 0])


class GeometryTests(unittest.TestCase):
    def test_bresenham_endpoints_and_continuity(self):
        for x0, y0, x1, y1 in ((0, 0, 10, 3), (5, 5, -3, 9), (2, 2, 2, 2), (0, 0, 0, -7)):
            pts = imageops.bresenham(x0, y0, x1, y1)
            self.assertEqual(pts[0], (x0, y0))
            self.assertEqual(pts[-1], (x1, y1))
            self.assertEqual(len(pts), max(abs(x1 - x0), abs(y1 - y0)) + 1)
            for (ax, ay), (bx, by) in zip(pts, pts[1:]):
                self.assertLessEqual(max(abs(bx - ax), abs(by - ay)), 1)

    def test_disc_and_square_offsets(self):
        self.assertEqual(imageops.disc_offsets(1), [(0, 0)])
        self.assertEqual(len(imageops.square_offsets(3)), 9)
        disc = imageops.disc_offsets(7)
        self.assertIn((0, 0), disc)
        self.assertNotIn((-3, -3), disc)  # corners are cut
        self.assertEqual(len(set(disc)), len(disc))
        self.assertEqual(sorted(disc), sorted((-x, -y) for x, y in disc))  # symmetric


if __name__ == "__main__":
    unittest.main()
