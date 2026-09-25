"""Tests for the glissandos and slides of abc2xml: each open line of a kind gets its own MusicXML
number, and a stop without an open line of its kind writes nothing.
"""
import unittest

from tests.abc2xml_support import parse_score

TUNE_HEADER = 'X:1\nM:4/4\nL:1/4\nK:C\n'


def lines(body):
    """Converts a tune and returns, per note, its (tag, type, number) glissando and slide notations."""
    return [[(n.tag, n.get('type'), n.get('number')) for n in note.iter() if n.tag in ('glissando', 'slide')]
            for note in parse_score(TUNE_HEADER + body).iter('note')]


class LineNumberTests(unittest.TestCase):
    def test_numbering(self):
        cases = [
            ('nested glissandos', '!~(!A !~(!B !~)!c !~)!d|]\n',
             [[('glissando', 'start', '1')], [('glissando', 'start', '2')],
              [('glissando', 'stop', '2')], [('glissando', 'stop', '1')]]),
            ('a stop without a start writes nothing', '!~(!A !~)!B !~)!c d|]\n',
             [[('glissando', 'start', '1')], [('glissando', 'stop', '1')], [], []]),
            ('glissandos and slides are numbered apart', '!-(!A !~(!B !-)!c !~)!d|]\n',
             [[('slide', 'start', '1')], [('glissando', 'start', '1')],
              [('slide', 'stop', '1')], [('glissando', 'stop', '1')]]),
        ]
        for label, body, expected in cases:
            with self.subTest(label):
                self.assertEqual(lines(body), expected)


if __name__ == '__main__':
    unittest.main()
