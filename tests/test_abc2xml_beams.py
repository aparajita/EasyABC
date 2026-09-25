"""Tests for the beam breaks of abc2xml: a note or rest written apart from the previous one by a space
breaks the beam, and each voice is measured within its own text only.
"""
import unittest

import abc2xml
from abc_syntax import parse_tune

TUNE_HEADER = 'X:1\nM:4/4\nL:1/8\nK:C\n'


def breaks(abc, voice_index=0):
    """Parses a tune and returns the beam break of every note and rest of one voice."""
    voice = parse_tune(abc).voices[voice_index]
    abc2xml.markBeamBreaks(voice)
    return [x.bbrk.t[0] for measure in voice.measures for x in measure if x.name in ('note', 'rest')]


class BeamBreakTests(unittest.TestCase):
    def test_a_space_breaks_the_beam(self):
        self.assertEqual(breaks(TUNE_HEADER + 'AB C z [CE]F|]\n'), [False, False, True, True, True, False, False])

    def test_a_voice_is_measured_within_its_own_text(self):
        voice = '[V:2] A B|]\n'
        two_voices = TUNE_HEADER + '[V:1] CDEF GABc cBAG FEDC|]\n' + voice
        self.assertEqual(breaks(two_voices, 1), breaks(TUNE_HEADER + voice))


if __name__ == '__main__':
    unittest.main()
