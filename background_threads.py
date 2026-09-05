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

import os
import sys
import threading
import time
from datetime import datetime
from queue import Empty, Queue

import wx

from abc_parser import parse_abc
from abc_tools import abc_to_svg, start_process
from abc_transform import process_abc_code, frac_mod
from abc_tune import AbcTune
from app_state import app_state
from constants import line_end_re, cwd
from exceptions import Abcm2psException
from midi2abc import Note
from tune_model import SvgTune
from wxhelper import wx_sound

pypm = None
try:
    old_stdout = sys.stdout
    sys.stdout = open(os.devnull, 'w')
    if wx.Platform == "__WXMAC__":
        import pygame.midi as pypm
        pypm.init()
    else:
        import pygame.pypm as pypm
        pypm.Initialize()
except ImportError:
    try:
        import pypm
    except ImportError:
        sys.stderr.write('Warning: pygame/pypm module not found. Recording midi will not work\n')
finally:
    sys.stdout = old_stdout

myRECORDSTOP = wx.NewEventType()
EVT_RECORDSTOP = wx.PyEventBinder(myRECORDSTOP, 1)

gmidi_in = []

myMUSICUPDATEDONE = wx.NewEventType()
EVT_MUSIC_UPDATE_DONE = wx.PyEventBinder(myMUSICUPDATEDONE, 1)


class RecordStopEvent(wx.PyCommandEvent):
    def __init__(self, eid, value=None):
        wx.PyCommandEvent.__init__(self, myRECORDSTOP, eid)
        self._value = value

    def GetValue(self):
        return self._value


class MusicUpdateDoneEvent(wx.PyCommandEvent):
    def __init__(self, eid, value=None):
        wx.PyCommandEvent.__init__(self, myMUSICUPDATEDONE, eid)
        self._value = value

    def GetValue(self):
        return self._value


class MusicUpdateThread(threading.Thread):
    def __init__(self, notify_window, settings, cache_dir):
        threading.Thread.__init__(self)
        self.daemon = True # 1.3.6.3 [JWdJ] to make sure the thread does not prevent EasyABC from exiting
        self.queue = Queue(maxsize=0) # 1.3.6.2 [JWdJ]
        self.notify_window = notify_window
        self.settings = settings
        self.cache_dir = cache_dir
        self.want_abort = False # 1.3.6.2 [JWdJ]

    # 1.3.6.2 [JWdJ] 2015-02 rewritten
    def run(self):
        while not self.want_abort:
            task = self.queue.get()
            self.queue.task_done()
            abc_tune = None
            diagnostics = []
            header_line_count = 0
            try:
                abc_code, abc_header = task
                if abc_code:
                    # a failure here is a parser bug, not a tune error; it propagates to the error pane
                    header_line_count = len(line_end_re.findall(abc_header))
                    diagnostics = parse_abc(abc_header + abc_code)
                if not abc_code:
                    svg_files, error = [], None
                elif not 'K:' in abc_code:
                    raise Exception('K: field is missing')
                else:
                    # 1.3.6.3 [JWDJ] splitted pre-processing abc and generating svg
                    abc_code = process_abc_code(self.settings, abc_code, abc_header, minimal_processing=not self.settings.get('reduced_margins', True))
                    abc_tune = AbcTune(abc_code)
                    file_name = os.path.abspath(os.path.join(self.cache_dir, 'temp-%s-.svg' % abc_tune.tune_id))
                    # file_name = generate_temp_file_name(self.cache_dir, '-.svg', replace_ending='-001.svg')
                    svg_files, error = abc_to_svg(abc_code, self.cache_dir, self.settings, target_file_name=file_name)
            except Abcm2psException as e:
                # if abcm2ps crashes, then wait at least 10 seconds until next invocation
                svg_files, error = [], str(e)
                # wx.PostEvent(self.notify_window, MusicUpdateDoneEvent(-1, (svg_files, error)))
                # time.sleep(10.0)
                # continue
                # error_msg = traceback.format_exc()
                # print(error_msg)
                pass
            except Exception as e:
                svg_files, error = [], str(e)
                # error_msg = traceback.format_exc()
                # print(error_msg)
                pass
            svg_tune = SvgTune(abc_tune, svg_files, error, diagnostics, header_line_count)
            if app_state.running:
                wx.PostEvent(self.notify_window, MusicUpdateDoneEvent(-1, svg_tune))

    # 1.3.6.2 [JWdJ] 2015-02 rewritten
    def ConvertAbcToSvg(self, abc_code, abc_header, clear_queue=True):
        task = (abc_code, abc_header)
        if clear_queue:
            while not self.queue.empty():
                try:
                    self.queue.get(False)
                except Empty:
                    continue
                self.queue.task_done()
        self.queue.put(task)

    def abort(self):
        self.want_abort = True


class MidiThread(threading.Thread):
    ''' This is how python runs a separate thread'''
    def __init__(self, settings):
        threading.Thread.__init__(self)
        self.daemon = True
        self.queue = Queue(maxsize=0) # 1.3.6.3 [JWdJ]
        self.settings = settings
        self.__want_abort = False # 1.3.6.3 [JWdJ]
        self.start()
        self.__is_busy = False

    def run(self):
        while not self.__want_abort:
            self.__is_busy = False
            command, params = self.queue.get()
            self.__is_busy = True
            midiplayer_path = params[0]
            midi_file = params[1]
            midiplayer_parameters = params[2].split()
            # 1.3.6.2 [SS] sleep no longer needed. abcToMidi not run as a
            # separate thread anymore.
            #time.sleep(0.5) # give abc2midi a chance to complete 2014-10-26 [SS]
            # 1.3.6.3 [SS] 2015-04-29
            # 1.3.6.3 [SS] 2015-05-08
            c = [midiplayer_path, midi_file] + midiplayer_parameters
            #note this is not the same as
            #c = [midiplayer_path, midi_file, midiplayer_parameters]
            try:
                start_process(c)
            except Exception as e:
                pass
                # print(e)
            self.queue.task_done()

    #p09 new function for playing midi files as a last resort 2014-10-14 [SS]
    def play_midi(self, midi_file):
        # p09 an option in case you have trouble playing midi files.
        midiplayer_path = self.settings['midiplayer_path']
        # [SS] 2015-04-29
        midiplayer_params = self.settings['midiplayer_parameters']
        if midiplayer_path:
            app_state.messages += '\ncalling ' + midiplayer_path #1.3.6 [SS]
            self.queue_task('play', midiplayer_path, midi_file, midiplayer_params)

    def clear_queue(self):
        while not self.queue.empty():
            try:
                self.queue.get(False)
            except Empty:
                continue
            self.queue.task_done()

    def queue_task(self, command, *args):
        task = (command, args)
        self.queue.put(task)

    def abort(self):
        self.__want_abort = True

    @property
    def is_busy(self):
        return self.__is_busy


class RecordThread(threading.Thread):
    def __init__(self, notify_window, midi_in_device_ID, midi_out_device_ID=None, metre_1=3, metre_2=4, bpm=70):
        global gmidi_in
        threading.Thread.__init__(self)
        self._notify_window = notify_window
        self._want_abort = 0
        self.bpm = bpm
        self.metre_1 = metre_1
        self.metre_2 = metre_2
        self.midi_in = pypm.Input(midi_in_device_ID)
        if midi_out_device_ID is None:
            self.midi_out = None
        else:
            self.midi_out = pypm.Output(midi_out_device_ID, 0)
        gmidi_in.append(self.midi_in)
        gmidi_in.append(self.midi_out)
        self.notes = []
        self.is_running = False
        self.tick1 = wx_sound(os.path.join(cwd, 'sound', 'tick1.wav'))
        self.tick2 = wx_sound(os.path.join(cwd, 'sound', 'tick2.wav'))

    def timedelta_microseconds(self, td):
        return td.seconds*1000000 + td.microseconds

    @property
    def beat_duration(self):
        return 1000000 * 60 / self.bpm  # unit is microseconds

    @property
    def midi_in_poll(self):
        if wx.Platform == "__WXMAC__":
            return self.midi_in.poll()
        else:
            return self.midi_in.Poll()

    def number_to_note(self, number):
        notes = ['c', 'c#', 'd', 'd#', 'e', 'f', 'f#', 'g', 'g#', 'a', 'a#', 'b']
        return notes[number%12]


    def run(self):
        self.is_running = True
        NOTE_ON = 0x09
        NOTE_OFF = 0x08
        i = 0
        noteon_time = {}
        start_time = datetime.now()
        last_tick = datetime.now()
        wx.CallAfter(self.tick1.Play)
        time.sleep(0.002)
        try:
            while not self._want_abort:
                while not self.midi_in_poll and not self._want_abort:
                    time.sleep(0.00025)
                    if self.timedelta_microseconds(datetime.now() - start_time) / self.beat_duration > i:
                        last_tick = datetime.now()
                        if i % self.metre_1 == 0:
                            wx.CallAfter(self.tick1.Play)
                        else:
                            wx.CallAfter(self.tick2.Play)
                        i += 1 #FAU: 20210102: One tick was missing the first time so incrementing i after the tick

                time_offset = self.timedelta_microseconds(datetime.now() - start_time)
                if self.midi_in_poll:
                    if wx.Platform == "__WXMAC__":
                        data = self.midi_in.read(1)
                    else:
                        data = self.midi_in.Read(1) # read only 1 message at a time
                    if self.midi_out is not None:
                        if wx.Platform == "__WXMAC__":
                            self.midi_out.write(data)
                        else:
                            self.midi_out.Write(data)
                    cmd = data[0][0][0] >> 4
                    midi_note = data[0][0][1]
                    midi_note_velocity = data[0][0][2]
                    #print(self.number_to_note(midi_note), midi_note_velocity)
                    if cmd == NOTE_ON and midi_note_velocity > 0:
                        noteon_time[midi_note] = time_offset
                        #print('note-on', midi_note, float(time_offset)/self.beat_duration)
                    elif (cmd == NOTE_OFF or midi_note_velocity ==0) and midi_note in noteon_time:
                        start = float(noteon_time[midi_note]) / self.beat_duration
                        end = float(time_offset) / self.beat_duration
                        self.notes.append([midi_note, start, end])
                        #print('note-off', midi_note, float(time_offset)/self.beat_duration)


        finally:
            if wx.Platform == "__WXMAC__":
                self.midi_in.close()
            else:
                self.midi_in.Close()
            if self.midi_out is not None:
                if wx.Platform == "__WXMAC__":
                    self.midi_out.close()
                else:
                    self.midi_out.Close()
            self.is_running = False
        self.quantize()
        wx.PostEvent(self._notify_window, RecordStopEvent(-1, self.notes))

    def quantize_swinged_16th(self, start_time):
        quantize_time = 0.25  # 1/16th
        return round(start_time / quantize_time) * quantize_time

    def quantize_triplet(self, notes):
        if len(notes) < 4:
            return False

        tolerance = 0.07
        first_note_start = round(notes[0][1] / 0.25) * 0.25

        durations = [n2[1]-n1[1] for n1, n2 in zip(notes[:3], notes[1:4])]

        for total_len in [1.0, 0.5]:
            if abs(durations[0] - total_len/3) < tolerance and \
               abs(durations[1] - total_len/3) < tolerance and \
               abs(durations[2] - total_len/3) < tolerance and \
               frac_mod(first_note_start, total_len) < tolerance:  # make sure that the start is on beat (8th) triplets, or on an 8th for 16th triplets

                notes[0][1] = first_note_start             # start time
                notes[1][1] = notes[0][1] + total_len /3   # start time
                notes[2][1] = notes[1][1] + total_len /3   # start time

                notes[0][2] = notes[0][1] + total_len / 3  # end time
                notes[1][2] = notes[1][1] + total_len / 3  # end time
                notes[2][2] = notes[2][1] + total_len / 3  # end time

                return True
        return False

    def quantize(self):
        quantized_notes = []

        if self.notes:
            distance_from_beat = frac_mod(self.notes[0][1], 1.0)
            if distance_from_beat > 0.5:
                distance_from_beat = -(1.0 - distance_from_beat)
            for note in self.notes:
                note[1] -= distance_from_beat/2

        for n1, n2 in zip(self.notes[0:-1], self.notes[1:]):
            n1[2] = n2[1]  # end of first is set to start of next note

        while self.notes:
            if self.quantize_triplet(self.notes):
                quantized_notes.extend(self.notes[:3])
                self.notes = self.notes[3:]
            else:
                note, start, end = self.notes.pop(0)
                start = self.quantize_swinged_16th(start)
                quantized_notes.append((note, start, end))

        for n1, n2 in zip(self.notes[0:-1], self.notes[1:]):
            n1[2] = n2[1]  # end of first is set to start of next note

        # quantize the end of the last note so that it ends at an even bar
        if quantized_notes:
            if self.metre_2 == 4:
                bar_length = float(self.metre_1)
            elif self.metre_2 == 8:
                bar_length = float(self.metre_1) / 2
            else:
                raise Exception('unknown metre')
            (note, start, end) = quantized_notes.pop()
            end = (int(end / bar_length) + 1) * bar_length     # set the end to be at the end of the bar
            quantized_notes.append((note, start, end))

        self.notes = [Note(start, end, note) for (note, start, end) in quantized_notes]

    def abort(self):
        self._want_abort = True
