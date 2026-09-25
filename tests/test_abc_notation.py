"""Tests for ClefField: the octave shift of the pitches that a K: or V: field's clef sets through
middle=, a +8/-8/^8/_15 suffix and octave=.
"""
import unittest

from abc_notation import ClefField, VoiceDefinition, drumSoundMidi


class ClefFieldTests(unittest.TestCase):
    def test_transposition(self):
        cases = [
            ('no clef', 'G', None),
            ('named clef', 'clef=bass', 0),
            ('middle= on the middle line of its clef', 'clef=bass middle=D,', 0),
            ('middle= an octave above the middle line', 'middle=D', -1),
            ('middle= two octaves above the middle line', 'middle=d', -2),
            ('lower case middle= note', 'middle=b', -1),
            ('+8 sounds an octave higher', 'clef=treble+8', 1),
            ('-8 sounds an octave lower', 'clef=treble-8', -1),
            ('^8 only prints', 'clef=treble^8', 0),
            ('_15 only prints', 'clef=treble_15', 0),
            ('octave= overrides the suffix', 'clef=treble-8 octave=1', 1),
            ('octave= without a clef', 'octave=-1', -1),
            ('the clef without a sign ignores octave=', 'clef=none octave=1', 0),
        ]
        for label, field, expected in cases:
            with self.subTest(label):
                self.assertEqual(ClefField.parse(field).transposition(), expected)

    def test_octave_change(self):
        cases = [
            ('+8', 'clef=treble+8', 1),
            ('_15', 'clef=treble_15', -2),
            ('no suffix', 'clef=treble', 0),
            ('digits are no suffix', 'clef=treble transpose=18', 0),
        ]
        for label, field, expected in cases:
            with self.subTest(label):
                self.assertEqual(ClefField.parse(field).octave_change, expected)


class VoiceDefinitionTests(unittest.TestCase):
    def test_parse(self):
        cases = [
            ('name and subname', 'clef=bass name="Left" subname="L"', ('Left', 'L', 'clef=bass name="" subname=""')),
            ('short forms', 'nm="Right" snm="R"', ('Right', 'R', 'nm="" snm=""')),
            ('sname', 'sname="R"', ('', 'R', 'sname=""')),
            ('subname before name', 'subname="R" name="Right"', ('Right', 'R', 'subname="" name=""')),
            ('snm before nm', 'snm="R" nm="Right"', ('Right', 'R', 'snm="" nm=""')),
            ('a name that is a clef keyword is blanked', 'name="bass"', ('bass', '', 'name=""')),
            ('no names', 'clef=treble', ('', '', 'clef=treble')),
        ]
        for label, text, expected in cases:
            with self.subTest(label):
                self.assertEqual(VoiceDefinition.parse(text), VoiceDefinition(*expected))


class DrumSoundTests(unittest.TestCase):
    def test_midi_of_abbreviated_name(self):
        cases = [
            ('parts match the parts of a GM name', 'closed-hi', '42'),
            ('a part matches inside a GM part', 'open-hi', '46'),
            ('the first GM name left wins', 'ride', '51'),
            ('parts match by place, not anywhere', 'hi-hat', None),
            ('no GM name matches', 'xyz', None),
        ]
        for label, name, expected in cases:
            with self.subTest(label):
                self.assertEqual(drumSoundMidi(name), expected)


if __name__ == '__main__':
    unittest.main()
