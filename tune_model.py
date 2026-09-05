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
from collections import deque, namedtuple

from abc_character_encoding import get_encoding_abc
from constants import line_end_re
from utils import read_entire_file

Tune = namedtuple('Tune', 'xnum title rythm offset_start offset_end abc header num_header_lines')
MidiNote = namedtuple('MidiNote', 'start stop indices page svg_row')


def text_to_lines(text):
    return line_end_re.split(text)


def read_abc_file(path):
    file_as_bytes = read_entire_file(path)
    encoding = get_encoding_abc(file_as_bytes)
    if encoding and encoding != 'utf-8':
        try:
            return file_as_bytes.decode(encoding)
        except UnicodeError:
            pass
    try:
        return file_as_bytes.decode('utf-8')
    except UnicodeError:
        return file_as_bytes.decode('latin-1')


class MidiTune(object):
    """ Container for abc2midi-generated .midi files """
    def __init__(self, abc_tune, midi_file=None, error=None):
        self.error = error
        self.midi_file = midi_file
        self.abc_tune = abc_tune

    def cleanup(self):
        if self.midi_file:
            if os.path.isfile(self.midi_file):
                os.remove(self.midi_file)
            self.midi_file = None


class SvgTune(object):
    """ Container for abcm2ps-generated .svg files """
    def __init__(self, abc_tune, svg_files, error, diagnostics, header_line_count):
        self.error = error
        self.svg_files = svg_files
        self.pages = {}
        self.abc_tune = abc_tune
        self.diagnostics = diagnostics
        self.header_line_count = header_line_count

    def render_page(self, page_index, renderer):
        if 0 <= page_index < self.page_count:
            page = self.pages.get(page_index, None)
            if page is None:
                page = renderer.svg_to_page(open(self.svg_files[page_index], 'rb').read())
                page.index = page_index
                self.pages[page_index] = page
        else:
            page = renderer.empty_page
        return page

    def cleanup(self):
        for f in self.svg_files:
            if os.path.isfile(f):
                os.remove(f)
        self.svg_files = ()

    def is_equal(self, svg_tune):
        if not isinstance(svg_tune, SvgTune):
            return False
        return self.abc_tune and self.abc_tune.is_equal(svg_tune.abc_tune)

    @property
    def page_count(self):
        return len(self.svg_files)

    @property
    def first_note_line_index(self):
        if self.abc_tune:
            return self.abc_tune.first_note_line_index
        return -1

    @property
    def tune_header_start_line_index(self):
        if self.abc_tune:
            return self.abc_tune.tune_header_start_line_index
        return -1

    @property
    def x_number(self):
        if self.abc_tune:
            return self.abc_tune.x_number
        return -1


class AbcTunes(object):
    """ A holder for created tunes. Takes care of proper cleanup. """
    def __init__(self, cache_size=1):
        self.__tunes = {}
        self.cache_size = cache_size
        self.cached_tune_ids = deque()

    def get(self, tune_id):
        tune = self.__tunes.get(tune_id, None)
        return tune

    def add(self, tune):
        if tune.abc_tune and self.cache_size > 0:
            tune_id = tune.abc_tune.tune_id
            #if tune_id in self.__tunes:
            #    print 'tune already cached'
            while len(self.cached_tune_ids) >= self.cache_size:
                old_tune_id = self.cached_tune_ids.pop()
                self.remove(old_tune_id)
            self.__tunes[tune_id] = tune
            self.cached_tune_ids.append(tune_id)

    def cleanup(self):
        for tune_id in list(self.__tunes):
            self.remove(tune_id)
        self.__tunes = {}

    def remove(self, tune_id):
        tune = self.__tunes[tune_id]
        if tune is not None:
            tune.cleanup()
        del self.__tunes[tune_id]
