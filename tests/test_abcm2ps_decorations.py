"""Tests for the decorations abc_transform defines for abcm2ps, run through the bundled
abcm2ps with the options of the score panel: it must accept every definition and draw each
navigation phrase right-aligned, in the font of tempo text.
"""
import glob
import os
import re
import subprocess
import tempfile
import unittest

import abc_decorations
from abc_parser import Severity
from abc_tools import get_default_path_for_executable
from abc_transform import abcm2ps_decoration_definitions
from tool_run import abcm2ps_line_severity

TEMPO_TEXT = 'Allegro'
TUNE_HEADER = 'X:1\nM:4/4\nL:1/4\nQ:"%s"\nK:C\n' % TEMPO_TEXT
PRINTED_NAVIGATION_WORDS = abc_decorations.abcm2ps_navigation_words()
SCORE_PANEL_OPTIONS = ['-v', '-A']    # as abc_tools.abc_to_svg runs abcm2ps for the score panel
FONT_OR_TEXT_RE = re.compile(r'style="(font:[^"]*)"|<text[^>]*>([^<]*)</text>')


def render_svg(abc):
    """Runs the bundled abcm2ps on abc and returns (diagnostic lines, SVG text)."""
    with tempfile.TemporaryDirectory() as directory:
        source = os.path.join(directory, 'tune.abc')
        with open(source, 'w') as f:
            f.write(abc)
        result = subprocess.run([get_default_path_for_executable('abcm2ps')] + SCORE_PANEL_OPTIONS
                                + ['-O', os.path.join(directory, 'tune.svg'), source],
                                capture_output=True, text=True)
        svg = ''.join(open(path).read() for path in sorted(glob.glob(os.path.join(directory, 'tune*.svg'))))
    return (result.stdout + result.stderr).splitlines(), svg


def text_fonts(svg):
    """Maps each text abcm2ps drew to the font style in effect where it stands: the last one before it."""
    fonts, font = {}, None
    for match in FONT_OR_TEXT_RE.finditer(svg):
        if match.group(1):
            font = match.group(1)
        else:
            fonts[match.group(2)] = font
    return fonts


class NavigationWordsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bars = '|'.join('!%s!C D E F' % d.name for d in PRINTED_NAVIGATION_WORDS)
        cls.lines, cls.svg = render_svg(abcm2ps_decoration_definitions + TUNE_HEADER + bars + '|]\n')

    def test_abcm2ps_accepts_every_definition(self):
        errors = [line for line in self.lines if abcm2ps_line_severity(line) is Severity.ERROR]
        self.assertEqual(errors, [])

    def test_each_phrase_is_drawn_right_aligned(self):
        for d in PRINTED_NAVIGATION_WORDS:
            with self.subTest(d.name):
                self.assertIn('text-anchor="end">%s</text>' % d.musicxml.text, self.svg)

    def test_each_phrase_is_drawn_in_the_tempo_font(self):
        fonts = text_fonts(self.svg)
        for d in PRINTED_NAVIGATION_WORDS:
            with self.subTest(d.name):
                self.assertEqual(fonts.get(d.musicxml.text), fonts[TEMPO_TEXT])


if __name__ == '__main__':
    unittest.main()
