"""Dependency-free regression checks against the real geometry/control functions.

AST extraction avoids importing the PDF/font stack; these checks do not render PDFs.
Run directly with Python or through pytest when the full stack is installed.
"""
import ast
import copy
import math
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
from typing import Any
from journal_pdf.boundary_ports import BoundaryGeometry, rectangular_path_bounds


SOURCE = Path(__file__).resolve().parents[1] / 'journal_pdf'


def load_functions(filename, names, context):
    tree = ast.parse((SOURCE / filename).read_text(encoding='utf-8'))
    body = [node for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
    exec(compile(ast.Module(body=body, type_ignores=[]), str(SOURCE / filename), 'exec'), context)


class FinalLayoutRegressions(unittest.TestCase):
    def setUp(self):
        self.context = {'math': math, 'Any': Any, 'copy': copy, 'Scene': object,
                        '__package__': 'journal_pdf', 'PT_PER_MM': 72 / 25.4,
                        'BoundaryGeometry': BoundaryGeometry, 'rectangular_path_bounds': rectangular_path_bounds}
        load_functions('common.py', {'FigureError', 'contains', 'intersects', 'segment_hits'}, self.context)
        load_functions('text_geometry.py', {'oblique','polygons','texts_intersect','segment_intersects_text',
                                           'arrow_intersects_text','rotate_point','ink_polygons','convex_intersects'}, self.context)
        load_functions('scene.py', {'audit_scene'}, self.context)
        load_functions('server.py', {'apply_changes'}, self.context)

    def scene(self, bbox, *, container=False, owner=None):
        return types.SimpleNamespace(width=100, height=100, size=8, template='', paths=[], assets=[],
            nodes=[{'id': 'frame', 'rect': [20, 20, 50, 50], 'kind': 'rectangle',
                    'container': container, 'width': .5}],
            texts=[{'id': 'label', 'owner': owner, 'position': {'bbox': bbox}}],
            node_groups=[], layout_evidence={})

    def test_unbound_label_crossing_rectangle_border_is_blocked(self):
        for bbox in ([15, 25, 25, 35], [25, 15, 35, 25],
                     [45, 25, 55, 35], [25, 45, 35, 55]):
            with self.subTest(bbox=bbox):
                issues = self.context['audit_scene'](self.scene(bbox))
                self.assertTrue(any(i['code'] == 'text_shape_collision' for i in issues))

    def test_stroke_touching_ink_is_blocked(self):
        issues = self.context['audit_scene'](self.scene([10, 25, 19.9, 35]))
        self.assertTrue(any(i['code'] == 'text_shape_collision' for i in issues))

    def test_safe_text_inside_container_is_allowed(self):
        self.assertEqual(self.context['audit_scene'](self.scene([25, 25, 35, 35], container=True)), [])

    def test_distant_external_label_is_allowed(self):
        self.assertEqual(self.context['audit_scene'](self.scene([5, 25, 15, 35])), [])

    def test_outside_top_override_is_available_without_mutating_original(self):
        original = {'kind': 'chart', 'legend_placement': 'source-region'}
        changed = self.context['apply_changes'](original, {'legend_placement': 'outside-top'})
        self.assertEqual(changed['legend_placement'], 'outside-top')
        self.assertEqual(original['legend_placement'], 'source-region')
        gallery = (SOURCE / 'gallery.py').read_text(encoding='utf-8')
        self.assertIn('<option value="outside-top">', gallery)
        self.assertNotIn('8 → 7 → 6 pt', gallery)

    def test_invalid_legend_override_remains_blocked(self):
        with self.assertRaises(self.context['FigureError']):
            self.context['apply_changes']({'kind': 'chart'}, {'legend_placement': 'arbitrary'})

    def test_layout_build_count_records_every_measured_attempt(self):
        load_functions('render.py', {'compile_figure'}, self.context)
        for width_per_pt, exact, expected in ((20, True, 1), (30, True, 18), (30, False, 1)):
            with self.subTest(width_per_pt=width_per_pt, exact=exact):
                builds = []
                def build(spec, reg, size):
                    builds.append(size)
                    return types.SimpleNamespace(width=size * width_per_pt, height=100, size=size,
                        paths=[{'exact_terminal': exact}], layout_evidence={})
                editorial = types.ModuleType('journal_pdf.editorial')
                editorial.scale_scene = lambda scene, factor: scene
                self.context.update(DIAGRAMS={'synthetic': build}, audit_scene=lambda scene: [])
                with patch.dict(sys.modules, {'journal_pdf.editorial': editorial}):
                    scene = self.context['compile_figure']({'kind': 'synthetic'}, None, None, None)
                self.assertEqual(len(builds), expected)
                self.assertEqual(scene.layout_evidence['layout_build_count'], len(builds))


if __name__ == '__main__':
    unittest.main()
