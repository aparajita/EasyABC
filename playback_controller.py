# Copyright (C) 2011-2014 Nils Liberg (mail: kotorinl at yahoo.co.uk)
# Copyright (C) 2015-2024 Seymour Shlien (mail: fy733@ncf.ca), Jan Wybren de Jong (jw_de_jong at yahoo dot com)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

import itertools
import os
import platform
import re
import sys
import traceback
from collections import defaultdict
from fractions import Fraction

import wx
from wx import GetTranslation as _

from abc_character_encoding import abc_text_to_unicode
from abc_midi_export import AbcToMidi
from abc_tools import get_output_from_process, get_midi_structure_as_text
from abc_transform import get_notes_from_abc, str2fraction
from app_state import app_state
from background_threads import EVT_RECORDSTOP, MidiThread, RecordThread
from constants import application_path, max_int
import menu_builder
from midi2abc import midi_to_abc
from settings_dialogs import MidiOptionsFrame
from tune_model import MidiNote, AbcTunes

try:
    from fluidsynthplayer import FluidSynthPlayer
    fluidsynth_available = True
except ImportError:
    sys.stderr.write('Warning: FluidSynth library not found. Playing using a SoundFont (.sf2) is disabled.\n')
    fluidsynth_available = False

#FAU:MIDIPLAY: On Mac, it is possible to interface directly to the Midi syntethiser of mac OS via mplay: https://github.com/jheinen/mplay
# An adaptation is done to integrate with EasyABC
if wx.Platform == "__WXMAC__":
    from mplaysmfplayer import MPlaySMFPlayer


def extract_note_timings(midi_tune, svg_tune, settings, renderer, unit_is_midi_tick):
    midi2abc_path = settings['midi2abc_path']
    if not svg_tune or not midi2abc_path or svg_tune.abc_tune.x_number != midi_tune.abc_tune.x_number:
        return []

    page_count = svg_tune.page_count
    if page_count == 0:
        return []

    lines = get_midi_structure_as_text(midi2abc_path, midi_tune.midi_file).splitlines()
    if not lines:
        return []

    pages = [svg_tune.render_page(p, renderer) for p in range(page_count)]
    page_index = 0
    page = pages[page_index]

    svg_rows = svg_tune.abc_tune.note_line_indices
    midi_rows = midi_tune.abc_tune.note_line_indices

    midi_lines = midi_tune.abc_tune.abc_lines
    svg_lines = svg_tune.abc_tune.abc_lines

    midi_col_to_svg_col = midi_tune.abc_tune.midi_col_to_svg_col

    if len(midi_rows) > len(svg_rows):
        # compensate for added lines for count-in
        svg_rows = list(svg_rows)
        for i in range(len(midi_rows)):
            if midi_lines[midi_rows[i]].strip() != svg_lines[svg_rows[i]].strip():
                svg_rows.insert(i, -1)
            if len(svg_rows) > len(midi_rows):
                return []  # out of sync

    if len(midi_rows) != len(svg_rows):
        return []  # out of sync

    svg_rows = [i + 1 for i in svg_rows]
    midi_rows = [i + 1 for i in midi_rows]

    errors = defaultdict(lambda: defaultdict(int))
    #FAU: jwdj/EasyABC#99 Starting from commit sshlien/abcmidi@705d9e1f737a2db9fdc615b622bc75204b1bcbee of midi2abc, Follow_score not working
    #FAU: This commit of midi2abc changed the format of CntlParm.
    #FAU: it used to be printf("CntlParm %2d %s = %d\n",chan+1, ctype[control],value);
    #FAU: it is now printf("CntlParm %2d %s = %d %d\n",chan+1, ctype[control],control,value);
    #FAU: Following regex is expecting only one decimal however an extra one is now present
    #FAU: To have a regex working for both version, \s*\d* is added
    #FAU: might need some further check
    #pos_re = re.compile(r'^\s*(\d+\.\d+)\s+CntlParm\s+1\s+unknown\s+=\s+(\d+)')
    pos_re = re.compile(r'^\s*(\d+\.\d+)\s+CntlParm\s+1\s+unknown\s+=\s*\d*\s+(\d+)')
    note_re = re.compile(r'^\s*(\d+\.\d+)\s+Note (on|off)\s+(\d+)\s+(\d+)')
    tempo_re = re.compile(r'^\s*(\d+\.\d+)\s+Metatext\s+tempo\s+=\s+(\d+\.\d+)\s+bpm')
    new_track_re = re.compile(r'^Track \d+ contains')

    def timediff_in_seconds(first, last, bpm):
        return (last - first) * 60 / bpm

    def time_value_to_milliseconds(value, tempos):
        tempos = [t for t in tempos if t[0] <= value]
        time_start, bpm, sec_until_time_start = tempos[-1]
        sec = sec_until_time_start + timediff_in_seconds(time_start, value, bpm)
        return int(sec * 1000)

    def append_tempo(tempos, time_start, tempo):
        sec_until_time_start = 0.0
        if tempos:
            later_start = [t for t in tempos if t[0] > time_start]
            if later_start:
                raise Exception('Cannot insert tempo at {0}'.format(time_start))
            prev_start, prev_bpm, prev_sec_until_time_start = tempos[-1]
            sec_until_time_start = prev_sec_until_time_start + timediff_in_seconds(prev_start, time_start, prev_bpm)
        tempos.append((time_start, tempo, sec_until_time_start))

    ticks_per_quarter = 480
    tempos = []
    notes = []
    svg_row = None
    row_col_midi_notes = defaultdict(lambda: defaultdict(int))
    last_line_was_pos = False
    for line in lines:
        m = new_track_re.match(line)
        if m is not None:
            page_index = 0
            page = pages[page_index]
            active_notes = {}
            indices = set()
            continue

        m = pos_re.match(line)
        if m is not None:
            value = int(m.group(2))
            if not last_line_was_pos:
                note_info = [value]
                indices = set()
                last_line_was_pos = True
            else:
                note_info.append(value)
                if len(note_info) == 5:
                    row = (note_info[0] << 14) + (note_info[1] << 7) + note_info[2]
                    col = (note_info[3] << 7) + note_info[4]

                    row_col_midi_notes[row][col] += 1
                    svg_row = svg_rows[midi_rows.index(row)]
                    svg_col = midi_col_to_svg_col(row, col)
                    if svg_col is not None:
                        for i in range(page_count):
                            indices = page.get_indices_for_row_col(svg_row, svg_col)
                            if indices:
                                break
                            # wrong page perhaps
                            page_index += 1
                            page_index %= page_count
                            page = pages[page_index]

                        if not indices:
                            errors[row][col] += 1
        else:
            last_line_was_pos = False
            m = note_re.match(line)
            if m is not None:
                time_value = float(m.group(1))
                if unit_is_midi_tick:
                    converted_time = time_value * ticks_per_quarter
                else:
                    converted_time = time_value_to_milliseconds(time_value, tempos)

                on_off = m.group(2)
                channel = int(m.group(3))
                note_num = int(m.group(4))
                if on_off == 'on':
                    note_start = converted_time
                    active_notes[(channel, note_num)] = MidiNote(note_start, None, indices, page_index, svg_row or 0)
                elif on_off == 'off':
                    note_stop = converted_time
                    note_on = active_notes.pop((channel, note_num), None)
                    if note_on is not None:
                        if page_index == note_on.page:
                            notes.append(MidiNote(note_on.start, note_stop, indices.union(note_on.indices), page_index, svg_row or 0))
                        else:
                            notes.append(MidiNote(note_on.start, note_stop, note_on.indices, note_on.page, note_on.svg_row))
            elif not unit_is_midi_tick:
                m = tempo_re.match(line)
                if m is not None:
                    tempo_start = float(m.group(1))
                    tempo = float(m.group(2))
                    append_tempo(tempos, tempo_start, tempo)

    row_col_svg_notes = defaultdict(lambda: defaultdict(int))
    for page in pages:
        for row, col in page.notes_row_col:
            row_col_svg_notes[row][col+1] += 1  # svg column is zero based so add one to make it 1-based

    lines = []

    rows = list(errors)
    rows.sort()
    for row in rows:
        svg_row = svg_rows[midi_rows.index(row)]
        svg_cols = list(row_col_svg_notes[svg_row])
        if errors[row]:
            if svg_cols:
                lines.append('Synchronization error in row {0} (SVG row {1}):'.format(row, svg_row))
                cols = list(errors[row])
                cols.sort()
                prev_col = 0
                line_parts = []
                for col in cols:
                    line_parts.append(' ' * (col - prev_col - 1))
                    n = errors[row][col]
                    if n > 0:
                        line_parts.append('!')
                    prev_col = col
                if svg_row > 1:
                    # output previous abc line from svg
                    lines.append(u'SVG{0:03d}:{1}'.format(svg_row-1, svg_lines[svg_row-2]))

                lines.append(u'Errors:{0}'.format(''.join(line_parts)))
            else:
                lines.append('Synchronization error in row {0} (SVG row {1} does not contain displayed notes)'.format(row, svg_row))

        if svg_cols:
            # output abc line from svg
            svg_line = svg_lines[svg_row-1]
            lines.append(u'SVG{0:03d}:{1}'.format(svg_row, svg_line))
            decoded_svg_line = abc_text_to_unicode(svg_line).encode('utf-8').decode('ascii', 'replace').replace('�', '?')
            if decoded_svg_line != svg_line:
                lines.append(u'SVG{0:03d}:{1}'.format(svg_row, decoded_svg_line))

            # mark the svg-notes
            svg_cols.sort()
            prev_col = 0
            line_parts = []
            for col in svg_cols:
                line_parts.append(' ' * (col - prev_col - 1))
                n = row_col_svg_notes[svg_row][col]
                if n == 1:
                    line_parts.append('^')
                elif 0 <= n <= 9:
                    line_parts.append('%d' % n)
                else:
                    line_parts.append('*')
                prev_col = col
            lines.append(u'SVG{0:03d}:{1}'.format(svg_row, ''.join(line_parts)))

            # output abc line from midi
            line = midi_lines[row-1]
            lines.append(u'MID{0:03d}:{1}'.format(row, line))

            # mark the midi-notes
            cols = list(row_col_midi_notes[row])
            cols.sort()
            prev_col = 0
            line_parts = []
            for col in cols:
                line_parts.append(' ' * (col - prev_col - 1))
                n = row_col_midi_notes[row][col]
                if n == 1:
                    line_parts.append('^')
                elif 0 <= n <= 9:
                    line_parts.append('%d' % n)
                else:
                    line_parts.append('*')
                prev_col = col
            lines.append(u'MID{0:03d}:{1}'.format(row, ''.join(line_parts)))
            lines.append('')

    if lines:
        app_state.messages += '\n\n=== follow score ===\n\n'
        app_state.messages += os.linesep.join(lines)

    return group_notes_by_time(notes)


def fill_time_gaps(time_slices):
    gaps = []
    last_stop = 0
    for time_slice in time_slices:
        if time_slice.start > last_stop:
            gaps.append(MidiNote(last_stop, time_slice.start, set(), time_slice.page, time_slice.svg_row))
        last_stop = time_slice.stop

    if gaps:
        time_slices += gaps
        time_slices.sort(key=lambda n: n.start)

    time_slices.insert(0, MidiNote(-max_int, 0, set(), 0, 0))
    last_page = time_slices[-1].page
    svg_row = time_slices[-1].svg_row
    time_slices.append(MidiNote(last_stop, max_int, set(), last_page, svg_row))
    return time_slices


def group_notes_by_time(notes):
    takewhile = itertools.takewhile
    notes.sort(key=lambda n: n.start)
    time_slices = []
    active_notes = []
    time_stop = max_int
    page = 0
    while notes or active_notes:
        time_start = notes[0].start if notes else max_int
        if time_start <= time_stop:
            same_note_start = list(takewhile(lambda n: n.start == time_start, notes))
            notes = notes[len(same_note_start):]
            active_notes += same_note_start
            active_notes.sort(key=lambda n: n.stop)
            time_stop = min(active_notes[0].stop if active_notes else max_int, notes[0].start if notes else max_int)
        else:
            # a note stops before the next note starts
            time_start, time_stop = time_stop, time_start
            time_stop = min(time_stop, active_notes[0].stop if active_notes else max_int)

        # adding a new slice
        if active_notes:
            page = max([n.page for n in active_notes])
            active_notes = [n for n in active_notes if n.page == page] # prevent mingling of indices from different pages

        all_indices_for_time_slice = set().union(*[n.indices for n in active_notes])
        svg_row = min([n.svg_row for n in active_notes]) if active_notes else 0
        time_slices.append(MidiNote(time_start, time_stop, all_indices_for_time_slice, page, svg_row))

        # removing stopped notes
        stopped_notes = list(takewhile(lambda n: n.stop <= time_stop, active_notes))
        active_notes = active_notes[len(stopped_notes):]

    return fill_time_gaps(time_slices)


class PlaybackController(object):
    """Playing, recording and following the score: the media player, the midi tunes it plays and the timers and threads around it."""

    def __init__(self, frame):
        self.frame = frame
        self.current_midi_tune = None # 1.3.6.3 [JWdJ] 2015-03
        self.midi_tunes = AbcTunes()
        self.applied_tempo_multiplier = 1.0 # 1.3.6.4 [JWdJ] 2015-05
        self.record_thread = None
        self.played_notes_timeline = None
        self.played_notes_iter = None
        self.future_notes_iter = None
        self.last_played_svg_row = None
        self.current_time_slice = None
        self.future_time_slice = None
        self.queue_number_follow_score = 0
        self.index = 1
        self.play_music_thread = None
        self.started_playing = False
        self.mc = None
        self.uses_fluidsynth = False
        self.create_media_player()
        self.mc.OnAfterLoad += self.OnMediaLoaded
        self.mc.OnAfterStop += self.OnAfterStop

        frame.Bind(EVT_RECORDSTOP, self.OnRecordStop)

        self.play_timer = wx.Timer(frame)
        frame.Bind(wx.EVT_TIMER, self.OnPlayTimer, self.play_timer)
        self.play_timer.Start(50)

    def create_media_player(self):
        frame = self.frame
        settings = frame.settings
        if platform.system() == 'Windows':
            default_soundfont_path = os.environ.get('HOMEPATH', 'C:') + "\\SoundFonts\\FluidR3_GM.sf2"
        else:
            default_soundfont_path = '/usr/share/sounds/sf2/FluidR3_GM.sf2'

        soundfont_path = settings.get('soundfont_path', default_soundfont_path)
        if fluidsynth_available and soundfont_path and os.path.exists(soundfont_path):
            try:
                init_soundfont_path = os.path.join(application_path, 'sound', 'example.sf2')
                if not os.path.exists(init_soundfont_path):
                    init_soundfont_path = soundfont_path
                self.mc = FluidSynthPlayer(init_soundfont_path)
                self.uses_fluidsynth = True
                self.mc.set_soundfont(soundfont_path, load_on_play=True)
            except Exception as e:
                error_msg = traceback.format_exc()
                self.mc = None

        #FAU:MIDIPLAY: on Mac add the ability to interface to System Midi Synth via mplay in case fluidsynth not available or not configured with soundfont
        if wx.Platform == "__WXMAC__" and self.mc is None:
            try:
                self.mc = MPlaySMFPlayer(frame)
            except:
                error_msg = "Error on loading SMF Midi Player"
                self.mc = None

        if self.mc is None:
            try:
                backend = None
                from wxmediaplayer import WxMediaPlayer
                #FAU:MIDIPLAY:The Quicktime interface do not manage MIDI File on latest version of Mac so keep only possibility on Windows
                #if wx.Platform == "__WXMAC__":
                #    backend = wx.media.MEDIABACKEND_QUICKTIME
                #elif wx.Platform == "__WXMSW__":
                if wx.Platform == "__WXMSW__":
                    if platform.release() == 'XP':
                        backend = wx.media.MEDIABACKEND_DIRECTSHOW
                    else:
                        backend = wx.media.MEDIABACKEND_WMP10
                self.mc = WxMediaPlayer(frame, backend)
            except NotImplementedError:
                from midiplayer import DummyMidiPlayer
                self.mc = DummyMidiPlayer()  # if media player not supported on this platform

    def shutdown(self):
        '''Stops the timer and the threads so none of them calls back into a destroyed frame.'''
        self.play_timer.Stop()
        if self.play_music_thread != None:
            self.play_music_thread.abort()
            self.play_music_thread = None
        if self.record_thread != None:
            self.record_thread.abort()
            self.record_thread = None

    def GetAbcToPlay(self):
        frame = self.frame
        tune = frame.tune_list_controller.GetSelectedTune()
        if tune:
            position, end_position = tune.offset_start, tune.offset_end
            if end_position > position and len(frame.score_view.selected_note_descs) > 2: ## and False:
                text = frame.editor.GetTextRange(position, end_position)
                notes = get_notes_from_abc(text)
                num_header_lines, first_note_line_index = frame.score_view.get_num_extra_header_lines(tune)

                #FAU: Seems not needed and issue when selecting not on a second page as it is considering all lines from first page as header. jwdj/EasyABC#100
                #FAU: To be noted it was already removed from OnNoteSelectionChangedDesc
                # workaround for the fact the abcm2ps returns incorrect row numbers
                # check the row number of the first note and if it doesn't agree with the actual value
                # then pretend that we have more or less extra header lines
                #if self.music_pane.current_page.notes: # 1.3.6.2 [JWdJ] 2015-02
                #    actual_first_row = self.music_pane.current_page.notes[0][2]-1
                #    correction = (actual_first_row - first_note_line_index)
                #    num_header_lines += correction

                temp = text.replace('\r\n', ' \n').replace('\r', '\n')  # re.sub(r'\r\n|\r', '\n', text)
                line_start_offset = [m.start(0) for m in re.finditer(r'(?m)^', temp)]

                selected_note_offsets = []
                offset_chord = 0
                for (_, _, abc_row, abc_col, desc) in frame.score_view.selected_note_descs:
                    abc_row -= num_header_lines
                    note_offset = line_start_offset[abc_row-1]+abc_col
                    if text[note_offset] == '[':
                        offset_chord += 1
                    if text[note_offset+offset_chord+1] == ']':
                        offset_chord = 0
                    selected_note_offsets.append(note_offset+offset_chord)

                unselected_note_offsets = [(start_offset, end_offset) for (start_offset, end_offset, _) in notes if not any(p for p in selected_note_offsets if start_offset <= p < end_offset)]
                unselected_note_offsets.sort()
                pieces = []
                pos = 0
                for start_offset, end_offset in unselected_note_offsets:
                    if start_offset > pos:
                        pieces.append(text[pos:start_offset])
                    pieces.append(' ' * (end_offset - start_offset))
                    pos = end_offset
                pieces.append(text[pos:])
                text = ''.join(pieces)

                # for some strange reason the MIDI sequence seems to be cut-off in the end if the last note is short
                # adding a silent extra note seems to fix this
                #text = text + os.linesep + '%%MIDI control 7 0' + os.linesep + 'A2'
                #FAU: the introduction of the previous line leads to have no sound at all on
                #     selection. using embedded instruction doesn' work either Thus remove it
                text = text.rstrip()# + '[I:MIDI control 7 0]' + os.linesep + 'A2'

                return (tune, text)
            return (tune, frame.editor.GetTextRange(position, end_position))
        return (tune, '')

    def play(self):
        frame = self.frame
        self.play_timer.Start(50)
        if frame.settings.get('follow_score', False) and frame.current_page_index != 0:
            frame.score_view.select_page(0)
        wx.CallAfter(self.mc.Play)

    def stop_playing(self):
        frame = self.frame
        self.mc.Stop()
        #FAU:remove highlighted notes
        frame.music_pane.draw_notes_highlighted(None)
        #FAU:MIDIPLAY: play timer can be stopped no need to update progress slider
        self.play_timer.Stop()
        frame.play_button.SetBitmap(frame.play_bitmap)
        frame.play_button.Refresh()
        frame.progress_slider.SetValue(0)

    def update_playback_rate(self):
        if self.mc.supports_tempo_change_while_playing:
            tempo_multiplier = self.get_tempo_multiplier() / self.applied_tempo_multiplier
            self.mc.PlaybackRate = tempo_multiplier

    def OnBpmSlider(self, evt):
        self.update_playback_rate()

    def OnBpmSliderClick(self, evt):
        if evt.ControlDown() or evt.ShiftDown():
            self.frame.bpm_slider.SetValue(0)
            self.OnBpmSlider(None)
        else:
            evt.Skip()

    # 1.3.6.3 [SS] 2015-05-05
    def reset_BpmSlider(self):
        self.frame.bpm_slider.SetValue(0)
        self.frame.bpm_slider.Enabled = True
        self.update_playback_rate() # 1.3.6.4 [JWDJ]

    def OnChangeLoopPlayback(self, event):
        loop = event.Selection != 0
        self.set_loop_midi_playback(loop)

    def OnChangeFollowScore(self, event):
        frame = self.frame
        enabled = event.Selection != 0
        frame.settings['follow_score'] = enabled
        self.UpdateTimingSliderVisibility()
        if enabled:
            if self.played_notes_timeline is None and self.current_midi_tune and frame.score_view.current_svg_tune:
                self.played_notes_timeline = self.note_timings(self.current_midi_tune, frame.score_view.current_svg_tune)
        else:
            frame.music_pane.draw_notes_highlighted(None)

    def UpdateTimingSliderVisibility(self):
        frame = self.frame
        visible = frame.follow_score_check.IsShown() and frame.follow_score_check.GetValue()
        if visible ^ frame.timing_slider.IsShown():
            frame.timing_slider.Show(visible)

    def OnChangeTiming(self, event):
        self.frame.settings['follow_score_timing_offset'] = event.Selection

    def OnTimingSliderClick(self, evt):
        if evt.ControlDown() or evt.ShiftDown():
            self.frame.timing_slider.SetValue(0)
            self.frame.settings['follow_score_timing_offset'] = 0
        else:
            evt.Skip()

    def start_midi_out(self, midifile):
        ''' Starts the Midi Player which runs as a separate thread in order not to
        hang up this program
        '''
        settings = self.frame.settings
        if self.play_music_thread is None:
            self.play_music_thread = MidiThread(settings)
        elif self.play_music_thread.is_busy:
            self.play_music_thread.abort()
            self.play_music_thread = MidiThread(settings)

        self.play_music_thread.play_midi(midifile)

    def do_load_media_file(self, path):
        if self.mc.Load(path):
            if wx.Platform == "__WXMSW__" and platform.release() != 'XP':
                # 1.3.6.3 [JWDJ] 2015-3 It seems mc.Play() triggers the OnMediaLoaded event
                self.mc.Play() # does not start playing but triggers OnMediaLoaded event
            #FAU:MIDIPLAY: added support for playback for Mac with SMF player For now kept apart from Windows
            #FAU:MIDIPLAY: %%TODO%% verify if can be merged with preceeding if
            #FAU:MIDIPLAY: 20250125 Not needed as correctly started based on OnMediaLoaded
            #elif wx.Platform == "__WXMAC__":
            #    self.mc.Play()
                #FAU:MIDIPLAY: Start timer to be able to have progress bar updated
            #    self.play_timer.Start(20)
            #    self.play_button.SetBitmap(self.pause_bitmap)
        else:
            wx.MessageBox(_("Unable to load %s: Unsupported format?") % path,
                          _("Error"), wx.ICON_ERROR | wx.OK)

    def OnMediaLoaded(self):
        frame = self.frame
        def play():
            # if wx.Platform == "__WXMAC__":
            #    time.sleep(0.3) # 1.3.6.4 [JWDJ] on Mac the first note is skipped the first time. hope this helps
            # self.mc.Seek(self.play_start_offset, wx.FromStart)
            frame.play_button.SetBitmap(frame.pause_bitmap)
            frame.progress_slider.SetRange(0, int(self.mc.Length())) #FAU:MIDIPLAY: mplay might return a float. thus forcing an int
            frame.progress_slider.SetValue(0)
            self.OnBpmSlider(None)
            self.update_playback_rate()
            #FAU:MIDIPLAY: The next 'if' was when using MediaCtrl which is not used anymore. Todo: remove the corresponding code if confirmed
            #if wx.Platform == "__WXMAC__":
            #    self.mc.Seek(0)  # When using wx.media.MEDIABACKEND_QUICKTIME the music starts playing too early (when loading a file)
            #    time.sleep(0.5)  # hopefully this fixes the first notes not being played
            self.play()
        wx.CallAfter(play)

    def OnAfterStop(self):
        frame = self.frame
        self.set_loop_midi_playback(False)
        # 1.3.6.3 [SS] 2015-05-04
        self.stop_playing()
        #FAU preserve latest bpm choice
        #self.reset_BpmSlider()
        #FAU20250125: Do not hide it if supported
        if frame.settings['midiplayer_path']:
            self.flip_tempobox(False)
        if wx.Platform != "__WXMSW__":
            frame.toolbar.Realize() # 1.3.6.4 [JWDJ] fixes toolbar repaint bug for Windows

    def OnToolRecord(self, evt):
        frame = self.frame
        settings = frame.settings
        if self.record_thread and self.record_thread.is_running:
            self.record_thread.abort()
            self.record_thread = None		#EPO prevent segmentation error (undefined variable)
        else:
            midi_in_device_ID = settings.get('midi_device_in', None)
            if midi_in_device_ID is None:
                frame.OnMidiSettings(None)
                midi_in_device_ID = settings.get('midi_device_in', None)
            midi_out_device_ID = settings.get('midi_device_out', None)
            if midi_in_device_ID is not None:
                metre_1, metre_2 = list(map(int, settings['record_metre'].split('/')))
                self.record_thread = RecordThread(frame, midi_in_device_ID, midi_out_device_ID, metre_1, metre_2, bpm = settings['record_bpm'])
                self.record_thread.daemon = True
                self.record_thread.start()

    def OnToolStop(self, evt):
        #FAU 20250125: Cleaning, trying to centralised what is common to Stop avoiding of mon to Stop instead of multiple call
        self.OnAfterStop()
        #self.set_loop_midi_playback(False)
        #self.stop_playing()
        # 1.3.6.3 [SS] 2015-04-03
        #self.play_panel.Show(False)
        #self.flip_tempobox(False)
        #self.progress_slider.SetValue(0)
        # self.reset_BpmSlider()     #[EPO] 2018-11-20 make sticky - this is new functionality
        #if wx.Platform != "__WXMSW__":
        #    self.toolbar.Realize() # 1.3.6.4 [JWDJ] fixes toolbar repaint bug for Windows
        if self.record_thread and self.record_thread.is_running:
            self.OnToolRecord(None)
        #if self.uses_fluidsynth:
        #    self.OnAfterStop()
        self.frame.editor.SetFocus()

    def OnSeek(self, evt):
        self.mc.Seek(self.frame.progress_slider.GetValue())

    def OnPlayTimer(self, evt):
        frame = self.frame
        if not frame.is_closed:
            if self.mc.is_playing:
                self.started_playing = True

                if wx.Platform == "__WXMAC__": #FAU:MIDIPLAY: Used to give the hand to MIDI player
                    delta = self.mc.IdlePlay()
                    #print(self.mc.get_songinfo)
                    if delta == 0:
                        if self.loop_midi_playback:
                            self.mc.Seek(0)
                        else:
                            self.mc.is_play_started = False

                offset = self.mc.Tell()
                if offset >= frame.progress_slider.Max:
                    length = self.mc.Length()
                    frame.progress_slider.SetRange(0, int(length)) #FAU:MIDIPLAY: mplay might return a float. thus forcing an int

                if frame.settings.get('follow_score', False):
                    self.queue_number_follow_score += 1
                    queue_number = self.queue_number_follow_score
                    #wx.CallLater(1, self.FollowScore, offset, queue_number) #[EPO] 2018-11-20  first arg 0 causes exception
                    self.FollowScore(offset, queue_number)

                frame.progress_slider.SetValue(offset)
            elif self.started_playing and not self.mc.is_paused: #and self.uses_fluidsynth
                self.started_playing = False
                wx.CallLater(500, self.OnAfterStop)

    def FollowScore(self, offset, queue_number):
        frame = self.frame
        if self.queue_number_follow_score != queue_number:
            return

        if not self.played_notes_timeline:
            return

        page = frame.music_pane.current_page
        if not page:
            return

        offset += frame.settings.get('follow_score_timing_offset', 0)

        current_time_slice = self.current_time_slice
        if current_time_slice and current_time_slice.start <= offset < current_time_slice.stop:
            return

        if current_time_slice is None or offset < current_time_slice.start:  # first time or after rewind
            self.played_notes_iter = iter(self.played_notes_timeline)

        for time_slice in self.played_notes_iter:
            if time_slice.start <= offset < time_slice.stop:
                current_time_slice = time_slice
                break

        self.current_time_slice = current_time_slice
        if current_time_slice.page == frame.current_page_index:
            try:
                frame.music_pane.draw_notes_highlighted(current_time_slice.indices, highlight_follow=True)
            except:
                pass
                # self.music_and_score_out_of_sync()

        # turning pages and going to next line has to be done slighty earlier
        if self.mc.unit_is_midi_tick:
            future_offset = offset + 480  # one quarter note should do
        else:
            future_offset = offset + 300  # 0.3 seconds should do
        future_time_slice = self.future_time_slice

        if future_time_slice is None or not (future_time_slice.start <= future_offset < future_time_slice.stop):
            if future_time_slice is None or future_offset < future_time_slice.start:
                self.future_notes_iter = iter(self.played_notes_timeline)

            future_time_slice = None
            for time_slice in self.future_notes_iter:
                if time_slice.start <= future_offset < time_slice.stop:
                    future_time_slice = time_slice
                    break

            self.future_time_slice = future_time_slice

        if future_time_slice is not None:
            try:
                if future_time_slice.page != frame.current_page_index:
                    frame.score_view.select_page(future_time_slice.page)
                    frame.score_view.scroll_to_notes(frame.music_pane.current_page, future_time_slice.indices)
                elif future_time_slice.svg_row != self.last_played_svg_row and future_time_slice.indices:
                    self.last_played_svg_row = future_time_slice.svg_row
                    frame.score_view.scroll_to_notes(frame.music_pane.current_page, future_time_slice.indices)
            except:
                pass
                # self.music_and_score_out_of_sync()

    def music_and_score_out_of_sync(self):
        self.played_notes_timeline = None
        self.current_time_slice = None
        self.future_time_slice = None

    def OnRecordBpmSelected(self, evt):
        settings = self.frame.settings
        menu = evt.EventObject
        item = menu.FindItemById(evt.GetId())
        settings['record_bpm'] = int(item.GetItemLabelText())
        if self.record_thread:
            self.record_thread.bpm = settings['record_bpm']

    def OnRecordMetreSelected(self, evt):
        menu = evt.EventObject
        item = menu.FindItemById(evt.GetId())
        self.frame.settings['record_metre'] = item.GetItemLabelText()

    def OnRecordStop(self, evt):
        notes = evt.GetValue()
        if notes:
            return self.handle_midi_conversion(notes=notes)

    # 1.3.6.3 [SS] 2015-05-03
    def flip_tempobox(self, state):
        ''' rearranges the toolbar depending on whether a midi file is played using the
            mc media player'''
        frame = self.frame
        menu_builder.show_toolbar_panel(frame, frame.progress_slider.Parent, state)
        frame.loop_check.Show(state)
        frame.follow_score_check.Show(state)
        self.UpdateTimingSliderVisibility()
        frame.toolbar.Realize()
        frame.manager.Update()

    def ReportFluidSynthIsMissing(self):
            wx.MessageBox(_("Both the FluidSynth library and a valid SoundFont (see menu Settings -> ABC Settings -> File settings) are required for exporting to a wave file."),
                          _("Unable to export"), wx.ICON_INFORMATION | wx.OK)

    def update_play_button(self):
        frame = self.frame
        if self.mc is not None or frame.settings['midiplayer_path']:
            frame.play_button.Enable()
        else:
            frame.play_button.Disable()

    def OnToolPlay(self, evt):
        frame = self.frame
        if self.mc.is_playing:
            self.mc.Pause()
            frame.play_button.SetBitmap(frame.play_bitmap)
        elif self.mc.is_paused:
            self.mc.Play()
            frame.play_button.SetBitmap(frame.pause_bitmap)
        else:
            remove_repeats = evt.ControlDown() or evt.CmdDown()
            # 1.3.6.3 [SS] 2015-05-04
            if not frame.settings['midiplayer_path']:
                self.flip_tempobox(True)
            frame.bpm_slider.Enabled = self.mc.supports_tempo_change_while_playing
            #self.play_panel.Show(not self.settings['midiplayer_path']) # 1.3.6.2 [JWdJ] 2015-02
            # self.toolbar.Realize() # 1.3.6.3 [JWDJ] fixes toolbar repaint bug

            self.current_time_slice = None
            self.future_time_slice = None
            self.last_played_svg_row = None
            wx.CallAfter(self.PlayMidi, remove_repeats)
        frame.editor.SetFocus()

    @property
    def loop_midi_playback(self):
        return self.mc.loop_midi_playback

    def set_loop_midi_playback(self, value):
        self.frame.loop_check.SetValue(value)
        self.mc.set_loop_midi_playback(value)

    def OnToolPlayLoop(self, evt):
        if self.frame.settings['midiplayer_path']:
            wx.MessageBox(_('Looping is not possible when using an external midi player. Empty the midiplayer path in Settings -> ABC Settings -> File Settings to regain the looping ability when you double click the play button'), _('Looping unavailable'), wx.OK | wx.ICON_INFORMATION)
        else:
            self.set_loop_midi_playback(True)
        if not self.mc.is_playing:
            self.OnToolPlay(evt)
        self.frame.editor.SetFocus()

    def PlayMidi(self, remove_repeats=False):
        frame = self.frame
        settings = frame.settings
        tune, abc = self.GetAbcToPlay()
        if not tune:
            return

        app_state.messages = u''
        if remove_repeats or (len(frame.score_view.selected_note_indices) > 2):
            abc = abc.replace('|:', '').replace(':|', '').replace('::', '')
            app_state.messages += '\n*removing repeats*'

        tempo_multiplier = self.get_tempo_multiplier()

        follow_score = not settings['midiplayer_path']
        # 1.3.6 [SS] 2014-11-15 2014-12-08
        self.current_midi_tune = AbcToMidi(abc, tune.header, frame.cache_dir, settings, frame.statusbar, tempo_multiplier, \
                                           add_follow_score_markers=follow_score)
        self.applied_tempo_multiplier = tempo_multiplier
        # 1.3.7 [SS] 2016-01-05 in case abc2midi crashes
        midi_file = None
        if self.current_midi_tune:
            self.midi_tunes.add(self.current_midi_tune)
            midi_file = self.current_midi_tune.midi_file

        if midi_file:
            # p09 an option in case you have trouble playing midi files.
            if settings['midiplayer_path']:
                app_state.messages += '\ncalling ' + settings['midiplayer_path'] #1.3.6 [SS]
                self.start_midi_out(midi_file)
            else:
                self.played_notes_timeline = None
                self.started_playing = False
                if settings.get('follow_score', False):
                    try:
                        self.played_notes_timeline = self.note_timings(self.current_midi_tune, frame.score_view.current_svg_tune)
                    except Exception as e:
                        error_msg = traceback.format_exc()
                        app_state.messages += error_msg
                self.do_load_media_file(midi_file)

    def note_timings(self, midi_tune, svg_tune):
        frame = self.frame
        return extract_note_timings(midi_tune, svg_tune, frame.settings, frame.renderer, self.mc.unit_is_midi_tick)

    def handle_midi_conversion(self, filename=None, notes=None):
        frame = self.frame
        midi2abc_path = frame.settings.get('midi2abc_path')
        if midi2abc_path and os.path.exists(midi2abc_path):
            cmd = [midi2abc_path, '-f', filename]
            app_state.messages += '\nMidiToAbc\n' + " ".join(cmd)
            stdout_value, stderr_value, returncode = get_output_from_process(cmd)
            app_state.messages += '\n' + stdout_value + stderr_value
            if returncode != 0:
                app_state.messages += '\n' + _('%(program)s exited abnormally (errorcode %(error)#8x)') % { 'program': 'MidiToAbc', 'error': returncode & 0xffffffff }
                return None
            if stdout_value:
                frame.typing_assistant.AddTextWithUndo('\n' + stdout_value + '\n')
        else:
            self.internal_midi_conversion(filename, notes)

    def internal_midi_conversion(self, filename=None, notes=None):
        frame = self.frame
        metre1, metre2 = [int(x) for x in frame.settings['record_metre'].split('/')]
        metre = Fraction(metre1, metre2)
        abcs = [midi_to_abc(filename=filename, notes=notes, metre=metre, default_len=df) for df in [Fraction(1,16), Fraction(1,8)]]
        abc = sorted(abcs, key=lambda x: len(x))[0]

        # default field values
        key = ''
        metre = ''
        default_len = ''
        title = _('Name of tune')

        # try to extract field values from abc code
        m = re.search('K: *(.*)', abc)
        if m:
            key = m.group(1)
        m = re.search('M: *(.*)', abc)
        if m:
            metre = m.group(1)
        m = re.search('L: *(.*)', abc)
        if m:
            default_len = m.group(1)
        if filename:
            title = os.path.splitext(os.path.basename(filename))[0].capitalize().replace('_', ' ')

        dlg = MidiOptionsFrame(frame, key=key, metre=metre, default_len=str(default_len), title=title)
        try:
            result = dlg.ShowModal() == wx.ID_OK
            if result:
                abc = midi_to_abc(filename=filename, notes=notes,
                                  key=dlg.key.GetValue(),
                                  metre=str2fraction(dlg.metre.GetValue()),
                                  title=dlg.title.GetValue(),
                                  default_len=str2fraction(dlg.default_len.GetValue()),
                                  bars_per_line=int(dlg.bpl.GetValue()),
                                  anacrusis_notes=int(dlg.num_notes_in_anacrusis.GetValue()),
                                  no_triplets=not dlg.triplet_detection.GetValue(),
                                  no_broken_rythms=not dlg.broken_rythm_detection.GetValue(),
                                  slur_8th_pairs=dlg.slur_8ths.GetValue(),
                                  slur_16th_pairs=dlg.slur_16ths.GetValue(),
                                  slur_triplets=dlg.slur_triplets.GetValue(),
                                  index=self.index)
                frame.typing_assistant.AddTextWithUndo('\n' + abc + '\n')
                self.index += 1
        finally:
            dlg.Destroy() # 1.3.6.3 [JWDJ] 2015-04-21 always clean up dialog window
        return result

    def get_tempo_multiplier(self):
        return 2.0 ** (float(self.frame.bpm_slider.GetValue()) / 100)
