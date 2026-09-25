"""Tests for the source positions of abc2xml's messages: a misplaced symbol and a broken rhythm symbol
without a note on both sides are reported with their source line and a caret under them.
"""
import unittest

import abc2xml
from tests.abc2xml_support import parse_score

TUNE_HEADER = 'X:1\nM:4/4\nL:1/4\nK:C\n'
BODY_LINE = TUNE_HEADER.count('\n') + 1


def report(body, message):
    """Converts a tune and returns (source line, the character under the caret) of the report of message."""
    abc2xml.getInfo()   # drop the messages of earlier conversions
    parse_score(TUNE_HEADER + body)
    lines = abc2xml.getInfo().splitlines()
    i = next(i for i, x in enumerate(lines) if x.endswith(message))
    line = int(lines[i].split(':')[0])
    excerpt, caret = lines[i + 1], lines[i + 2]
    return line, excerpt[caret.index('^')]


class ReportPositionTests(unittest.TestCase):
    def test_positions(self):
        cases = [
            ('misplaced symbol', 'A B c d|]\nA #B c d|]\n', '**misplaced symbol: #', (BODY_LINE + 1, '#')),
            ('broken rhythm at the end of a measure', 'A B c d>|]\n', 'error in broken rhythm: >', (BODY_LINE, '>')),
        ]
        for label, body, message, expected in cases:
            with self.subTest(label):
                self.assertEqual(report(body, message), expected)


if __name__ == '__main__':
    unittest.main()
