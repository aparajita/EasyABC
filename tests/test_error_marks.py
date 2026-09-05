"""Tests for the pure rules in error_marks: diagnostic_span() turns a Diagnostic's
SourcePosition into the (offset, length) span the squiggle indicator marks, and
span_at() finds the marked span under an editor position.
"""
import unittest

from abc_parser import Diagnostic, Severity, SourcePosition
from error_marks import diagnostic_span, span_at


class DiagnosticSpanTests(unittest.TestCase):
    def test_span_cases(self):
        cases = [
            (
                'excerpt found: marks the non-whitespace run at the column',
                'A B [C>E] |]',
                SourcePosition(line=1, excerpt='A B [C>E] |]', column=6),
                (6, 3),
            ),
            (
                'excerpt found at a nonzero offset in the line',
                '  A B [C>E] |]',
                SourcePosition(line=1, excerpt='A B [C>E] |]', column=6),
                (8, 3),
            ),
            (
                'column lands on whitespace: length is still at least 1',
                'A B [C>E] |]',
                SourcePosition(line=1, excerpt='A B', column=1),
                (1, 1),
            ),
            (
                'excerpt not found: the whole line minus its ending is marked',
                'different text entirely\r\n',
                SourcePosition(line=1, excerpt='not present', column=0),
                (0, len('different text entirely')),
            ),
        ]
        for description, line_text, position, expected in cases:
            with self.subTest(description=description):
                self.assertEqual(diagnostic_span(line_text, position), expected)


FIRST = Diagnostic('first', Severity.ERROR, None)
SECOND = Diagnostic('second', Severity.WARNING, None)
FIRST_SPAN = (10, 13, FIRST)
SECOND_SPAN = (20, 25, SECOND)
SPANS = [FIRST_SPAN, SECOND_SPAN]


class SpanAtTests(unittest.TestCase):
    def test_lookup_cases(self):
        cases = [
            ('position at a span start returns that span', SPANS, 10, FIRST_SPAN),
            ('position one before a span end returns that span', SPANS, 24, SECOND_SPAN),
            ('position exactly at a span end returns None', SPANS, 13, None),
            ('position between two spans returns None', SPANS, 15, None),
            ('empty span list returns None', [], 10, None),
        ]
        for description, spans, position, expected in cases:
            with self.subTest(description=description):
                self.assertIs(span_at(spans, position), expected)


if __name__ == '__main__':
    unittest.main()
