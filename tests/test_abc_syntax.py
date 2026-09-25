"""Tests for the lyric alignment of the shared front end: a '|' in a verse resynchronises it to
the next bar line of the music, and with %%graceword a grace group shares the syllable slot of the
note it precedes; notes left without a syllable and syllables left without a note are recorded.
"""
import unittest

from abc_syntax import parse_tune

TUNE_HEADER = 'X:1\nM:4/4\nL:1/4\nK:C\n'


def align(body, header=''):
    """Parses a one-voice tune and returns (per note: step prefixed with 'g' for a grace note, and the text
    of its first lyric object), the steps of the bare notes, and the texts of the surplus syllables."""
    voice = parse_tune(header + TUNE_HEADER + body).voices[0]
    elements = [e for measure in voice.measures for e in measure]
    notes = [('g' if hasattr(e, 'grace') else '') + e.pitch.t[-2] for e in elements if e.name == 'note']
    lyrics = [e.objs[0].t[0] if e.objs else None for e in elements if e.name == 'note']
    block = next(e for e in elements if e.name == 'lyr_blk')
    bare = [note.pitch.t[-2] for verse, note in block.bareNotes]
    surplus = [syl.t[0] for verse, syl in block.surplus]
    return list(zip(notes, lyrics)), bare, surplus


class LyricAlignmentTests(unittest.TestCase):
    def test_bar_resynchronisation(self):
        cases = [
            ('an early bar leaves the rest of the bar bare', 'A B | c d |\nw:la | lo lu\n',
             [('A', 'la'), ('B', '*'), ('c', 'lo'), ('d', 'lu')], ['B'], []),
            ('syllables beyond the bar are surplus', 'A B | c d |\nw:la li le | lo\n',
             [('A', 'la'), ('B', 'li'), ('c', 'lo'), ('d', '*')], ['d'], ['le']),
        ]
        for label, body, expected, bare, surplus in cases:
            with self.subTest(label):
                self.assertEqual(align(body), (expected, bare, surplus))

    def test_graceword(self):
        cases = [
            ('the grace group takes the syllable, its note a melisma', '%%graceword 1\n', '{g}A B|\nw:la\n',
             [('gg', 'la'), ('A', '_'), ('B', '*')], ['B'], []),
            ('without graceword the grace note takes nothing', '', '{g}A B|\nw:la\n',
             [('gg', None), ('A', 'la'), ('B', '*')], ['B'], []),
            ('a grace group before a bare note is filled too', '%%graceword 1\n', 'A {g}B|\nw:la\n',
             [('A', 'la'), ('gg', '*'), ('B', '*')], ['B'], []),
        ]
        for label, header, body, expected, bare, surplus in cases:
            with self.subTest(label):
                self.assertEqual(align(body, header), (expected, bare, surplus))


if __name__ == '__main__':
    unittest.main()
