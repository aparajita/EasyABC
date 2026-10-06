"""Tests for the text annotations of abc2xml: with --songscribe, an annotation just before a bar is
right-aligned, so it ends at the bar.
"""
import unittest

import abc2xml

TUNE_HEADER = 'X:1\nM:4/4\nL:1/4\nK:C\n'


def annotation(body):
    """Converts a tune with --songscribe and returns (placement, justify, halign) of its one annotation."""
    abc2xml.mxm.songscribe = True
    direction = next(abc2xml.mxm.parse(TUNE_HEADER + body).iter('direction'))
    words = direction.find('direction-type/words')
    return direction.get('placement'), words.get('justify'), words.get('halign')


class AnnotationTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(setattr, abc2xml.mxm, 'songscribe', abc2xml.mxm.songscribe)

    def test_annotation_before_a_bar_is_right_aligned(self):
        for bar in ['|', ':|', '||', '|]']:
            with self.subTest(bar):
                self.assertEqual(annotation('C D E F "^Sing 3x"%s\n' % bar), ('above', 'right', 'right'))

    def test_annotation_below_the_staff_before_a_bar_is_right_aligned(self):
        self.assertEqual(annotation('C D E F "_Sing 3x"|]\n'), ('below', 'right', 'right'))


if __name__ == '__main__':
    unittest.main()
