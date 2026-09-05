"""Tests for the parser-level contract that abc_parser.parse_abc() promises: every
diagnostic's line number survives the header-folding and voice-splitting machinery in
splitHeaderVoices/buildVoiceRows, node offsets survive from parse to validate, and the
function never raises even when a tune cannot be parsed.
"""
import unittest
from unittest.mock import patch

from pyparsing import ParseException, Word, alphas

from abc_parser import Severity, parse_abc, abc_voice


def _diagnostics_with_fragment(diagnostics, fragment):
    return [d for d in diagnostics if fragment in d.message]


class ParseAbcTests(unittest.TestCase):
    def test_misplaced_symbol_reports_correct_line_through_header_machinery(self):
        # Every case shifts where the music actually sits relative to the raw line count.
        cases = [
            (
                'a %% directive, a folded (+:) continued field, and a comment line before the row',
                '%%MIDI program 1\n'
                'X:1\n'
                'T:Test\n'
                'N:a note\n'
                '+:continued note\n'
                'K:C\n'
                '% a comment line\n'
                'A B [C>E] |]\n',
                'misplaced symbol: >', 8, 'A B [C>E] |]',
            ),
            (
                'a field on its own line is folded into the row that follows it',
                'X:1\n'
                'T:Test\n'
                'K:G\n'
                'abc|\n'
                'M:3/4\n'
                'de#f|\n',
                'misplaced symbol: #', 6, 'de#f|',
            ),
        ]
        for description, abc_text, fragment, expected_line, expected_excerpt in cases:
            with self.subTest(description=description):
                diagnostics = parse_abc(abc_text)
                matches = _diagnostics_with_fragment(diagnostics, fragment)
                self.assertEqual(len(matches), 1)
                self.assertEqual(matches[0].severity, Severity.ERROR)
                self.assertEqual(matches[0].position.line, expected_line)
                self.assertEqual(matches[0].position.excerpt, expected_excerpt)

    def test_illegal_duration_and_body_only_header_field_report_offending_line(self):
        abc_text = (
            'X:1\n'
            'T:Test\n'
            'K:C\n'
            'A3/7 B |\n'
            '[C:body header field] c d |]\n'
        )
        diagnostics = parse_abc(abc_text)
        expectations = [
            ('illegal duration', 4),
            ('illegal header field in body', 5),
        ]
        for fragment, expected_line in expectations:
            with self.subTest(fragment=fragment):
                matches = _diagnostics_with_fragment(diagnostics, fragment)
                self.assertEqual(len(matches), 1)
                self.assertEqual(matches[0].position.line, expected_line)

    def test_unparseable_tune_returns_error_diagnostic_without_raising(self):
        # Force the ParseException branch that a well-formed voice text never
        # actually reaches (abc_voice tolerates almost anything), so the
        # never-raises contract is exercised directly.
        try:
            Word(alphas).parse_string('123')
        except ParseException as err:
            synthetic_failure = err
        abc_text = 'X:1\nT:Test\nK:C\nA B c |]\n'
        with patch.object(abc_voice, 'parse_string', side_effect=synthetic_failure):
            diagnostics = parse_abc(abc_text)
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0].severity, Severity.ERROR)
        self.assertIsNotNone(diagnostics[0].position)

    def test_two_voice_tune_reports_each_voice_error_on_its_own_line(self):
        abc_text = (
            'X:1\n'
            'T:Two Voices\n'
            'K:C\n'
            'V:1\n'
            'A B [C>E] |]\n'
            'V:2\n'
            'D E F |\n'
            'G A [F>A] |]\n'
        )
        diagnostics = parse_abc(abc_text)
        matches = _diagnostics_with_fragment(diagnostics, 'misplaced symbol: >')
        self.assertEqual(len(matches), 2)
        for match, expected_line in zip(matches, (5, 8)):
            with self.subTest(expected_line=expected_line):
                self.assertEqual(match.position.line, expected_line)


if __name__ == '__main__':
    unittest.main()
