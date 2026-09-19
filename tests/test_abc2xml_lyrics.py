"""Tests for the lyric alignment of abc2xml: with %%graceword a grace group shares the
syllable slot of the note it precedes, and an unescaped slash splits the syllable between
the first grace note and that principal note.
"""
import unittest
import warnings

with warnings.catch_warnings():
    warnings.simplefilter('ignore')     # pyparsing deprecation warnings from abc2xml's grammar
    import abc2xml

TUNE_HEADER = 'X:1\nM:4/4\nL:1/4\nK:C\n'
GRACEWORD = '%%graceword 1\n'


def convert(body, header=GRACEWORD):
    """Converts a tune and returns (note label, lyrics) per note: the label is the step,
    prefixed with 'g' for a grace note or 'z' for a rest; lyrics are (syllabic, text, extend)."""
    if not hasattr(abc2xml, 'abc_header'):
        abc2xml.abc_header, abc2xml.abc_voice, abc2xml.abc_scoredef, abc2xml.abc_percmap = abc2xml.abc_grammar()
        abc2xml.mxm = abc2xml.MusicXml()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        score = abc2xml.mxm.parse(header + TUNE_HEADER + body)
    notes = []
    for note in score.iter('note'):
        pitch = note.find('pitch')
        label = pitch.findtext('step') if pitch is not None else 'z'
        if note.find('grace') is not None:
            label = 'g' + label
        lyrics = []
        for lyric in note.findall('lyric'):
            extend = lyric.find('extend')
            lyrics.append((lyric.findtext('syllabic'), lyric.findtext('text'),
                           extend.get('type') if extend is not None else None))
        notes.append((label, lyrics))
    return notes


class GraceSyllableTests(unittest.TestCase):
    def test_alignment_cases(self):
        cases = [
            (
                'slash: grace part on the grace note, principal part on the main note',
                GRACEWORD, '{g}A B|\nw:O/All two\n',
                [('gG', [('single', 'O', None)]),
                 ('A', [('single', 'All', None)]),
                 ('B', [('single', 'two', None)])],
            ),
            (
                '= before the slash: the word continues from the grace note onto the main note',
                GRACEWORD, '{g}A B|\nw:O=/All two\n',
                [('gG', [('begin', 'O', None)]),
                 ('A', [('end', 'All', None)]),
                 ('B', [('single', 'two', None)])],
            ),
            (
                'trailing dash: the principal part begins a word that continues on the next note',
                GRACEWORD, '{g}A B|\nw:O/All-lu\n',
                [('gG', [('single', 'O', None)]),
                 ('A', [('begin', 'All', None)]),
                 ('B', [('end', 'lu', None)])],
            ),
            (
                'no slash: syllable on the grace note, melisma on the main note',
                GRACEWORD, '{g}A B|\nw:O two\n',
                [('gG', [('single', 'O', 'start')]),
                 ('A', [(None, None, 'stop')]),
                 ('B', [('single', 'two', None)])],
            ),
            (
                'no slash on a multi-note group: syllable on the first grace note, melisma on the rest and the main note',
                GRACEWORD, '{fe}A B|\nw:O two\n',
                [('gF', [('single', 'O', 'start')]),
                 ('gE', [(None, None, 'continue')]),
                 ('A', [(None, None, 'stop')]),
                 ('B', [('single', 'two', None)])],
            ),
            (
                'slash on a multi-note group: grace part covers the group, principal part on the main note',
                GRACEWORD, '{fe}A B|\nw:O/All two\n',
                [('gF', [('single', 'O', 'start')]),
                 ('gE', [(None, None, 'stop')]),
                 ('A', [('single', 'All', None)]),
                 ('B', [('single', 'two', None)])],
            ),
            (
                'empty grace part: the grace note gets no lyric',
                GRACEWORD, '{g}A B|\nw:/All two\n',
                [('gG', []),
                 ('A', [('single', 'All', None)]),
                 ('B', [('single', 'two', None)])],
            ),
            (
                'empty principal part: the main note gets no lyric',
                GRACEWORD, '{g}A B|\nw:O/ two\n',
                [('gG', [('single', 'O', None)]),
                 ('A', []),
                 ('B', [('single', 'two', None)])],
            ),
            (
                'escaped slash stays literal text on the grace note',
                GRACEWORD, '{g}A B|\nw:a\\/b two\n',
                [('gG', [('single', 'a/b', 'start')]),
                 ('A', [(None, None, 'stop')]),
                 ('B', [('single', 'two', None)])],
            ),
            (
                'extend in a grace slot covers every grace note and the main note',
                GRACEWORD, 'B {fe}A C|\nw:la _ two\n',
                [('B', [('single', 'la', 'start')]),
                 ('gF', [(None, None, 'continue')]),
                 ('gE', [(None, None, 'continue')]),
                 ('A', [(None, None, 'stop')]),
                 ('C', [('single', 'two', None)])],
            ),
            (
                'skip in a grace slot skips every grace note and the main note',
                GRACEWORD, '{fe}A C|\nw:* two\n',
                [('gF', []),
                 ('gE', []),
                 ('A', []),
                 ('C', [('single', 'two', None)])],
            ),
            (
                'graceword off: the slash is text on the main note and grace notes get nothing',
                '', '{g}A B|\nw:O/All two\n',
                [('gG', []),
                 ('A', [('single', 'O/All', None)]),
                 ('B', [('single', 'two', None)])],
            ),
            (
                'graceword off: an extend reaches past a grace note and past a chord',
                '', 'A {g}B [CE] D|\nw:la _ lo _\n',
                [('A', [('single', 'la', 'start')]),
                 ('gG', []),
                 ('B', [(None, None, 'stop')]),
                 ('C', [('single', 'lo', 'start')]),
                 ('E', []),
                 ('D', [(None, None, 'stop')])],
            ),
        ]
        for description, header, body, expected in cases:
            with self.subTest(description):
                self.assertEqual(convert(body, header), expected)

    def test_grace_slots_match_abcm2ps(self):
        # Syllable placement abcm2ps 8.14.18 renders for this tune: a grace group before a
        # rest or a barline takes no syllable, one before a chord does.
        body = '{g}z A {f}[CE] D {e}|B C D E|\nw:a b c d e f g\n'
        self.assertEqual(convert(body), [
            ('gG', []),
            ('z', []),
            ('A', [('single', 'a', None)]),
            ('gF', [('single', 'b', 'start')]),
            ('C', [(None, None, 'stop')]),
            ('E', []),
            ('D', [('single', 'c', None)]),
            ('gE', []),
            ('B', [('single', 'd', None)]),
            ('C', [('single', 'e', None)]),
            ('D', [('single', 'f', None)]),
            ('E', [('single', 'g', None)]),
        ])

    def test_inline_graceword_switches_alignment_across_lyric_blocks(self):
        body = ('{g}A B|\nw:O/All two\n'
                '[I:graceword 0] {g}C D|\nw:three/x four\n'
                '{g}E F|\nw:five six\n')
        self.assertEqual(convert(body), [
            ('gG', [('single', 'O', None)]),
            ('A', [('single', 'All', None)]),
            ('B', [('single', 'two', None)]),
            ('gG', []),
            ('C', [('single', 'three/x', None)]),
            ('D', [('single', 'four', None)]),
            ('gG', []),
            ('E', [('single', 'five', None)]),
            ('F', [('single', 'six', None)]),
        ])


if __name__ == '__main__':
    unittest.main()
