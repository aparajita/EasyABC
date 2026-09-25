"""Tests for the navigation marks of abc2xml: each becomes a direction above the staff whose
sound element makes playback follow the jump.
"""
import unittest

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
            ('D.C.alcoda', 'words', 'D.C. al Coda', {'dacapo': 'yes'}),
            ('D.S.alfine', 'words', 'D.S. al Fine', {'dalsegno': 'segno'}),
            ('D.S.alcoda', 'words', 'D.S. al Coda', {'dalsegno': 'segno'}),
        ]
        for decoration, tag, text, sound in cases:
            with self.subTest(decoration):
                self.assertEqual(directions('!%s!C D E F|]\n' % decoration), [('above', tag, text, sound)])


if __name__ == '__main__':
    unittest.main()
