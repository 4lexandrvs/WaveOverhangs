import unittest

from plugin.gcode_emitter import inject_layer_paths


class GCodeEmitterTests(unittest.TestCase):
    def test_inserts_paths_and_restores_absolute_e_mode(self):
        source = ";LAYER_CHANGE\n;Z:0.2\nG1 X10 Y10 E1.0\n"
        paths = {0.2: [[(1.0, 2.0), (2.0, 2.0)]]}
        result, count = inject_layer_paths(source, paths)
        self.assertEqual(count, 1)
        self.assertIn("M83 ; Wave Overhangs: temporary relative extrusion", result)
        self.assertIn(";TYPE:Wave Overhangs", result)
        self.assertIn("M82 ; Wave Overhangs: restore absolute extrusion", result)
        self.assertLess(result.index("M82 ; Wave Overhangs"), result.index("G1 X10 Y10 E1.0"))

    def test_keeps_relative_e_mode(self):
        source = "M83\n;LAYER_CHANGE\n;Z:0.4\nG1 X10 Y10 E0.2\n"
        paths = {0.4: [[(0.0, 0.0), (1.0, 0.0)]]}
        result, count = inject_layer_paths(source, paths)
        self.assertEqual(count, 1)
        self.assertNotIn("M82 ; Wave Overhangs", result)
        self.assertNotIn("M83 ; Wave Overhangs: temporary", result)

    def test_does_not_change_gcode_without_matching_layer(self):
        source = ";LAYER_CHANGE\n;Z:0.2\nG1 X10 Y10 E1.0\n"
        result, count = inject_layer_paths(source, {0.4: [[(0, 0), (1, 0)]]})
        self.assertEqual(count, 0)
        self.assertEqual(result, source)


if __name__ == "__main__":
    unittest.main()
