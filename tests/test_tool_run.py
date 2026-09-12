"""Tests for the tool_run module: abc2midi_line_severity and abcm2ps_line_severity
grade one printed line each, and ToolRun.severity combines diagnostic-line severities
with the run's return code into the single severity the status bar reports.
"""
import unittest

from abc_parser import Severity
from tool_run import ABC2MIDI, ToolRun, abc2midi_line_severity, abcm2ps_line_severity


class Abc2midiLineSeverityTests(unittest.TestCase):
    def test_ignored_instruction_lines_are_informational_for_every_decoration(self):
        for decoration in ('port', 'fall', 'arpeggio'):
            with self.subTest(decoration=decoration):
                line = 'Warning in line-char 7-1 : instruction !%s! ignored' % decoration
                self.assertEqual(abc2midi_line_severity(line), Severity.INFO)

    def test_other_lines_take_the_severity_their_prefix_names(self):
        cases = [
            ('5.03 April 26 2025 abc2midi', Severity.INFO),
            ('Error in line-char 3-0 : Field not allowed in tune body', Severity.ERROR),
            ('Warning in line-char 8-8 : Line of music without lyrics', Severity.WARNING),
            ('writing MIDI file t.mid', Severity.INFO),
        ]
        for line, expected in cases:
            with self.subTest(line=line):
                self.assertEqual(abc2midi_line_severity(line), expected)


class Abcm2psLineSeverityTests(unittest.TestCase):
    def test_grades_real_abcm2ps_output(self):
        cases = [
            ('stdin:8:11: error: Bad length divisor', Severity.ERROR),
            ("   8 [C:bad] G3/7 A |]", Severity.INFO),
            ('                 ^', Severity.INFO),
            ('stdin:6:11: error: Decoration !fall! not defined', Severity.ERROR),
            ('stdin:6:11: warning: Not enough words for lyric line', Severity.WARNING),
            ('stdin:6:16: warning: Line underfull (365pt of 682pt)', Severity.WARNING),
            ('abcm2ps-8.14.18 (2026-01-28)', Severity.INFO),
            ('File stdin', Severity.INFO),
            ('Output written on stdin001.svg (3237 bytes)', Severity.INFO),
        ]
        for line, expected in cases:
            with self.subTest(line=line):
                self.assertEqual(abcm2ps_line_severity(line), expected)


class ToolRunSeverityTests(unittest.TestCase):
    def test_severity_combines_diagnostic_lines_and_return_code(self):
        cases = [
            ('a clean run', '', 0, Severity.INFO),
            (
                'a warning line and an unprefixed line',
                'Warning in line-char 8-8 : Line of music without lyrics\nwriting MIDI file t.mid',
                0,
                Severity.WARNING,
            ),
            (
                'a warning line and an error line',
                'Warning in line-char 8-8 : Line of music without lyrics\n'
                'Error in line-char 3-0 : Field not allowed in tune body',
                0,
                Severity.ERROR,
            ),
            ('only the version banner but a non-zero return code', '5.03 April 26 2025 abc2midi', 1, Severity.ERROR),
        ]
        for description, stdout, returncode, expected in cases:
            with self.subTest(description=description):
                run = ToolRun(ABC2MIDI, stdout, '', returncode)
                self.assertEqual(run.severity, expected)


if __name__ == '__main__':
    unittest.main()
