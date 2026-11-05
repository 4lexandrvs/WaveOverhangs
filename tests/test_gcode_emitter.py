import unittest

from plugin.gcode_emitter import inject_layer_paths


class GCodeEmitterTests(unittest.TestCase):
    def test_inserts_paths_and_restores_absolute_e_mode_and_coordinate(self):
        source = "G92 E5.0\n;LAYER_CHANGE\n;Z:0.2\nG1 X10 Y10 E5.5\n"
        paths = {0.2: [[(1.0, 2.0), (2.0, 2.0)]]}
        result, count = inject_layer_paths(source, paths, height_by_z={0.2: 0.2})
        self.assertEqual(count, 1)
        self.assertIn("M83 ; Wave Overhangs: temporary relative extrusion", result)
        self.assertIn(";TYPE:Wave Overhangs", result)
        self.assertIn("M82 ; Wave Overhangs: restore absolute extrusion", result)
        self.assertIn("G92 E5 ; Wave Overhangs: restore absolute E coordinate", result)
        self.assertLess(result.index("G92 E5 ; Wave Overhangs"),
                        result.index("G1 X10 Y10 E5.5"))
        self.assertTrue(result.endswith("\n"))

    def test_keeps_relative_e_mode(self):
        source = "M83\n;LAYER_CHANGE\n;Z:0.4\nG1 X10 Y10 E0.2\n"
        paths = {0.4: [[(0.0, 0.0), (1.0, 0.0)]]}
        result, count = inject_layer_paths(source, paths, height_by_z={0.4: 0.2})
        self.assertEqual(count, 1)
        self.assertNotIn("M82 ; Wave Overhangs", result)
        self.assertNotIn("M83 ; Wave Overhangs: temporary", result)

    def test_does_not_change_gcode_without_matching_layer(self):
        source = ";LAYER_CHANGE\n;Z:0.2\nG1 X10 Y10 E1.0\n"
        result, count = inject_layer_paths(source, {0.4: [[(0, 0), (1, 0)]]})
        self.assertEqual(count, 0)
        self.assertEqual(result, source)

    def test_requires_exact_layer_height(self):
        source = ";LAYER_CHANGE\n;Z:0.2\nG1 X10 Y10 E1.0\n"
        with self.assertRaisesRegex(ValueError, "layer height"):
            inject_layer_paths(source, {0.2: [[(0, 0), (1, 0)]]})

    def test_rejects_additional_tool(self):
        source = "T1\n;LAYER_CHANGE\n;Z:0.2\n"
        with self.assertRaisesRegex(ValueError, "multiple-tool"):
            inject_layer_paths(source, {0.2: [[(0, 0), (1, 0)]]},
                               height_by_z={0.2: 0.2})

    def test_rejects_volumetric_extrusion(self):
        source = "M200 D1.75\n;LAYER_CHANGE\n;Z:0.2\n"
        with self.assertRaisesRegex(ValueError, "volumetric"):
            inject_layer_paths(source, {0.2: [[(0, 0), (1, 0)]]},
                               height_by_z={0.2: 0.2})


if __name__ == "__main__":
    unittest.main()
