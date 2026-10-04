"""Tests for the navigation marks of abc2xml: each becomes a direction above the staff whose
sound element makes playback follow the jump.
"""
import unittest

import abc_decorations
from abc_decorations import DecorationKind
from tests.abc2xml_support import parse_score

TUNE_HEADER = 'X:1\nM:4/4\nL:1/4\nK:C\n'


def directions(body):
    """Converts a tune and returns (placement, symbol or words, words text, sound attributes) per direction."""
    result = []
    for direction in parse_score(TUNE_HEADER + body).iter('direction'):
        mark = direction.find('direction-type')[0]
        sound = direction.find('sound')
        result.append((direction.get('placement'), mark.tag, mark.text, dict(sound.attrib)))
    return result


class NavigationMarkTests(unittest.TestCase):
    def test_marks_convert_to_directions_above_the_staff(self):
        cases = [
            ('coda', 'coda', None, {'coda': 'coda'}),
            ('segno', 'segno', None, {'segno': 'segno'}),
            ('fine', 'words', 'Fine', {'fine': 'yes'}),
            ('D.S.', 'words', 'D.S.', {'dalsegno': 'segno'}),
            ('D.C.', 'words', 'D.C.', {'dacapo': 'yes'}),
            ('dacapo', 'words', 'D.C.', {'dacapo': 'yes'}),
            ('dacoda', 'words', 'To Coda', {'tocoda': 'coda'}),
            ('D.C.alfine', 'words', 'D.C. al Fine', {'dacapo': 'yes'}),
            ('alfinerepeat', 'words', 'D.C. al Fine with repeats', {'dacapo': 'yes'}),
            ('alfinenorepeat', 'words', 'D.C. al Fine no repeat', {'dacapo': 'yes'}),
            ('D.C.alcoda', 'words', 'D.C. al Coda', {'dacapo': 'yes'}),
            ('D.S.alfine', 'words', 'D.S. al Fine', {'dalsegno': 'segno'}),
            ('D.S.alcoda', 'words', 'D.S. al Coda', {'dalsegno': 'segno'}),
        ]
        for decoration, tag, text, sound in cases:
            with self.subTest(decoration):
                self.assertEqual(directions('!%s!C D E F|]\n' % decoration), [('above', tag, text, sound)])

    def test_navigation_words_are_right_aligned(self):
        for d in abc_decorations.CATALOG:
            if d.kind is not DecorationKind.NAVIGATION_WORDS:
                continue
            with self.subTest(d.name):
                words = parse_score(TUNE_HEADER + '!%s!C D E F|]\n' % d.name).find('.//words')
                self.assertEqual((words.get('justify'), words.get('halign')), ('right', 'right'))


if __name__ == '__main__':
    unittest.main()
