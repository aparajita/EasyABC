"""Tests for the abc_midi_export contract that classify_abc2midi_output() promises:
every 'instruction !X! ignored' line is informational regardless of X, every other
line takes the severity abc2midi's own prefix names, a non-zero return code adds an
abnormal-exit error, and the function is pure — it reads nothing from the shared
app_state.messages log.
"""
import unittest

from abc_parser import Severity
from abc_midi_export import classify_abc2midi_output, abnormal_exit_message
from app_state import app_state


class ClassifyAbc2midiOutputTests(unittest.TestCase):
    def test_ignored_instruction_lines_are_informational_for_every_decoration(self):
        for decoration in ('port', 'fall', 'arpeggio'):
            with self.subTest(decoration=decoration):
                line = 'Warning in line-char 7-1 : instruction !%s! ignored' % decoration
                lines = classify_abc2midi_output(line, '', 0)
                self.assertEqual(len(lines), 1)
                self.assertEqual(lines[0].severity, Severity.INFO)

    def test_other_lines_take_the_severity_of_their_prefix(self):
        stdout_value = (
            'AbcToMidi Nov 2024 version\n'
            'Error in line-char 3-0 : bad note\n'
            'Warning in line-char 5-2 : unusual pitch\n'
        )
        lines = classify_abc2midi_output(stdout_value, 'writing MIDI file to x.midi\n', 0)
        severities = [line.severity for line in lines]
        self.assertEqual(severities, [Severity.INFO, Severity.ERROR, Severity.WARNING, Severity.INFO])

    def test_nonzero_returncode_adds_an_abnormal_exit_error(self):
        returncode = 1
        lines = classify_abc2midi_output('writing MIDI file to x.midi\n', '', returncode)
        self.assertEqual(lines[-1].severity, Severity.ERROR)
        self.assertEqual(lines[-1].text, abnormal_exit_message(returncode))

    def test_reads_nothing_from_app_state_messages(self):
        stdout_value = 'Error in line-char 3-0 : bad note\n'
        without_unrelated_messages = classify_abc2midi_output(stdout_value, '', 0)

        original_messages = app_state.messages
        app_state.messages = 'Error: an unrelated message left over from another run'
        try:
            with_unrelated_messages = classify_abc2midi_output(stdout_value, '', 0)
        finally:
            app_state.messages = original_messages

        self.assertEqual(without_unrelated_messages, with_unrelated_messages)


if __name__ == '__main__':
    unittest.main()
