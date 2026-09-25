"""Tests for StaffLayout.redirect: where an I:staff directive moves a voice within its grand staff.
"""
import unittest

from abc_directives import parse_info_directive
from abc_staff_layout import StaffLayout
from abc_syntax import abc_scoredef

# a grand staff of three staves (exactly one voice named, so it is accepted) and a voice outside it
SCORE = 'score {A B C} D'
VOICE_NAMES = {'A': ('Piano', ''), 'B': ('', ''), 'C': ('', ''), 'D': ('', '')}


def layout():
    return StaffLayout(VOICE_NAMES, abc_scoredef.parse_string(SCORE)[0])


class RedirectTests(unittest.TestCase):
    def test_redirect(self):
        cases = [
            ('relative down', 'B', 'staff +1', 3, []),
            ('relative up to the first staff', 'B', 'staff -1', 1, []),
            ('relative above the first staff', 'A', 'staff -1', 1, ['could not relocate to staff: staff -1']),
            ('absolute', 'A', 'staff 3', 3, []),
            ('staff 0 does not exist', 'A', 'staff 0', 1,
             ['abc staff 0 does not exist', 'could not relocate to staff: staff 0']),
            ('beyond the last staff', 'A', 'staff 5', 1,
             ['abc staff 5 does not exist', 'could not relocate to staff: staff 5']),
            ('a voice outside a grand staff stays', 'D', 'staff 1', 0, ['could not relocate to staff: staff 1']),
        ]
        for label, vid, text, staff, problems in cases:
            with self.subTest(label):
                staves = layout()
                self.assertEqual(staves.redirect(vid, parse_info_directive(text)), problems)
                self.assertEqual(staves.staff_of(vid), staff)

    def test_absolute_counts_the_staves_of_the_score(self):
        staves = layout()
        staves.redirect('B', parse_info_directive('staff 3'))
        staves.redirect('A', parse_info_directive('staff 2'))
        self.assertEqual(staves.staff_of('A'), 2)


if __name__ == '__main__':
    unittest.main()
