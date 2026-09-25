"""Tests for the I: directive records: which kind each directive text is, the values the page format
and MIDI directives carry, and that a handler hears each directive exactly once.
"""
import unittest

from abc_directives import (DirectiveHandler, DrumMapping, GracewordDirective, InvalidDirective, MalformedDirective,
                            MidiInstrument, MidiDirective, PageFormat, PageSetting, PercussionMapping,
                            ScoreDirective, SkippedDirective, StaffRedirection, dispatch_info_directive,
                            parse_info_directive)

MM_PER_CM = 10
MM_PER_INCH = 25.4
POINTS_PER_INCH = 72


class ClassificationTests(unittest.TestCase):
    def test_kind_of_directive(self):
        cases = [
            ('score', 'score (A B) C', ScoreDirective),
            ('staves', 'staves A B', ScoreDirective),
            ('staffwidth before staff', 'staffwidth 18cm', SkippedDirective),
            ('staff redirection', 'staff +1', StaffRedirection),
            ('staff without a number', 'staff x', InvalidDirective),
            ('page format', 'scale 0.8', PageFormat),
            ('upper case MIDI', 'MIDI program 1', MidiDirective),
            ('lower case midi', 'midi channel 2', MidiDirective),
            ('percmap', 'percmap D', PercussionMapping),
            ('percmap its grammar rejects', 'percmap Q', MalformedDirective),
            ('graceword', 'graceword 1', GracewordDirective),
            ('unknown keyword', 'linebreak $', SkippedDirective),
        ]
        for label, text, kind in cases:
            with self.subTest(label):
                self.assertIsInstance(parse_info_directive(text), kind)


class PageFormatTests(unittest.TestCase):
    def test_value_in_mm(self):
        cases = [
            ('cm', 'pagewidth 21cm', PageSetting.PAGE_WIDTH, 21 * MM_PER_CM),
            ('inch', 'leftmargin 1in', PageSetting.LEFT_MARGIN, MM_PER_INCH),
            ('point', 'topmargin %dpt' % POINTS_PER_INCH, PageSetting.TOP_MARGIN, MM_PER_INCH),
            ('no unit is mm', 'botmargin 12', PageSetting.BOTTOM_MARGIN, 12),
            ('scale is a plain number', 'scale 0.75', PageSetting.SCALE, 0.75),
        ]
        for label, text, setting, value in cases:
            with self.subTest(label):
                directive = parse_info_directive(text)
                self.assertEqual(directive.setting, setting)
                self.assertAlmostEqual(directive.value, value)

    def test_value_without_a_number_is_invalid(self):
        for text in ('pagewidth wide', 'pagewidth 1.2.3cm'):
            with self.subTest(text):
                self.assertIsInstance(parse_info_directive(text), InvalidDirective)


class MidiTests(unittest.TestCase):
    def test_instrument(self):
        cases = [
            ('program', 'MIDI program 5', MidiInstrument('', '5', '', '')),
            ('channel and program', 'MIDI program 2 5', MidiInstrument('2', '5', '', '')),
            ('channel', 'MIDI channel 3', MidiInstrument('3', '', '', '')),
            ('control 7 is the volume', 'MIDI control 7 100', MidiInstrument('', '', '100', '')),
            ('control 10 is the pan', 'MIDI control 10 64', MidiInstrument('', '', '', '64')),
            ('another controller sets nothing', 'MIDI control 1 64', MidiInstrument('', '', '', '')),
            ('no instrument', 'MIDI transpose -2', None),
        ]
        for label, text, instrument in cases:
            with self.subTest(label):
                self.assertEqual(parse_info_directive(text).instrument, instrument)

    def test_drummap(self):
        cases = [
            ('^ draws an x', 'MIDI drummap ^F 42', DrumMapping('^', 'F', 0, '42'), 'x'),
            ('_ draws a circled x', "MIDI drummap _c' 49", DrumMapping('_', 'c', 1, '49'), 'circle-x'),
            ('a plain note draws a normal head', 'MIDI drummap C, 36', DrumMapping('', 'C', -1, '36'), 'normal'),
        ]
        for label, text, drum, notehead in cases:
            with self.subTest(label):
                directive = parse_info_directive(text)
                self.assertEqual(directive.drum, drum)
                self.assertEqual(directive.drum.notehead, notehead)

    def test_transpose(self):
        self.assertEqual(parse_info_directive('MIDI transpose -2').transpose, '-2')
        self.assertIsNone(parse_info_directive('MIDI program 5').transpose)


class RecordingHandler(DirectiveHandler):
    def __init__(self):
        self.calls = []

    def on_score(self, d): self.calls.append(('on_score', d))
    def on_staff_redirection(self, d): self.calls.append(('on_staff_redirection', d))
    def on_page_format(self, d): self.calls.append(('on_page_format', d))
    def on_midi(self, d): self.calls.append(('on_midi', d))
    def on_percussion_mapping(self, d): self.calls.append(('on_percussion_mapping', d))
    def on_graceword(self, d): self.calls.append(('on_graceword', d))
    def on_skipped(self, d): self.calls.append(('on_skipped', d))
    def on_invalid(self, d): self.calls.append(('on_invalid', d))
    def on_malformed(self, d): self.calls.append(('on_malformed', d))


class DispatchTests(unittest.TestCase):
    def test_one_call_per_directive(self):
        cases = [
            ('score A B', 'on_score'),
            ('staff 2', 'on_staff_redirection'),
            ('pageheight 29.7cm', 'on_page_format'),
            ('MIDI program 1', 'on_midi'),
            ('percmap D', 'on_percussion_mapping'),
            ('graceword 0', 'on_graceword'),
            ('linebreak $', 'on_skipped'),
            ('staff x', 'on_invalid'),
            ('percmap Q', 'on_malformed'),
        ]
        for text, method in cases:
            with self.subTest(text):
                handler = RecordingHandler()
                dispatch_info_directive(text, handler)
                self.assertEqual([(name, d) for name, d in handler.calls], [(method, parse_info_directive(text))])

    def test_handler_lacking_a_method_cannot_exist(self):
        class Incomplete(DirectiveHandler):
            def on_score(self, d): pass
        with self.assertRaises(TypeError):
            Incomplete()


if __name__ == '__main__':
    unittest.main()
