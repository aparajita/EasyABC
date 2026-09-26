"""Tests for the repeat endings of abc2xml: with --songscribe, a second ending discontinues at the plain
bar that ends its first measure, unless its line ends before that bar.
"""
import unittest

import abc2xml

TUNE_HEADER = 'X:1\nM:4/4\nL:1/4\nK:C\n'
FIRST_ENDING = '|: A B c d |1 e f g a :|'


def endings(body, songscribe):
    """Converts a tune, each ABC line a score line, and returns its (measure, number, type) endings."""
    abc2xml.mxm.songscribe = songscribe
    score = abc2xml.mxm.parse(TUNE_HEADER + FIRST_ENDING + body, bOpt=True)
    return [(measure.get('number'), ending.get('number'), ending.get('type'))
            for measure in score.iter('measure') for ending in measure.iter('ending')]


class EndingTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(setattr, abc2xml.mxm, 'songscribe', abc2xml.mxm.songscribe)

    def test_endings(self):
        first = [('2', '1', 'start'), ('2', '1', 'stop')]
        cases = [
            ('a second ending discontinues at its first plain bar', True,
             '2 "Am" [ce] "^x" !trill!d A | e f g a |]\n',
             first + [('3', '2', 'start'), ('3', '2', 'discontinue')]),
            ('a line break after the bar still discontinues it', True,
             '2 a b c d |\n e f g a |]\n',
             first + [('3', '2', 'start'), ('3', '2', 'discontinue')]),
            ('a measure spanning a line break leaves it open', True,
             '2 a b\n c d | e f g a |]\n',
             first + [('3', '2', 'start'), ('4', '2', 'stop')]),
            ('a third ending stays open', True,
             '3 a b c d | e f g a |]\n',
             first + [('3', '3', 'start'), ('4', '3', 'stop')]),
            ('an explicit rbend keeps its type', True,
             '2 a b !rbend!c d | e f g a |]\n',
             first + [('3', '2', 'start'), ('3', '2', 'stop')]),
            ('without --songscribe the second ending stays open', False,
             '2 a b c d | e f g a |]\n',
             first + [('3', '2', 'start'), ('4', '2', 'stop')]),
        ]
        for label, songscribe, body, expected in cases:
            with self.subTest(label):
                self.assertEqual(endings(body, songscribe), expected)


if __name__ == '__main__':
    unittest.main()
