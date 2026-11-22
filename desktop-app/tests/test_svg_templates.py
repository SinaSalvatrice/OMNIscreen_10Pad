"""Checks for read-only, externally editable SVG firmware theme templates."""
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
from screen_editor import SCREENS, STYLES, SVG_DIR, svg_metadata

class SvgTemplateTests(unittest.TestCase):
    def test_builtin_templates(self):
        for slug, name, index in SCREENS:
            for style in STYLES:
                with self.subTest(screen=slug, style=style):
                    data = svg_metadata(SVG_DIR / style / (slug + '.svg'), slug)
                    self.assertIn(data['preset'], range(3))
                    self.assertTrue(data['background'].startswith('#'))

    def test_reject_wrong_screen(self):
        filename = SVG_DIR / STYLES[0] / 'layer-list.svg'
        with self.assertRaises(ValueError):
            svg_metadata(filename, 'settings')

    def test_reject_invalid_svg(self):
        with TemporaryDirectory() as folder:
            filename = Path(folder) / 'bad.svg'
            filename.write_text('<svg><script>x</script></svg>', encoding='utf8')
            with self.assertRaises(ValueError):
                svg_metadata(filename, 'settings')

if __name__ == '__main__':
    unittest.main()
