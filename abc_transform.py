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
import hashlib
import os
import re
from collections import namedtuple
from fractions import Fraction

from abc_tune import comment_pattern
from aligner import bar_sep_without_space
from constants import program_name
from tune_model import text_to_lines

all_notes = "C,, D,, E,, F,, G,, A,, B,, C, D, E, F, G, A, B, C D E F G A B c d e f g a b c' d' e' f' g' a' b' c'' d'' e'' f'' g'' a'' b''".split()


def str2fraction(s):
    parts = [int(x.strip()) for x in s.split('/')]
    return Fraction(parts[0], parts[1])


def frac_mod(fractional_number, modulo):
    return fractional_number - modulo * int(fractional_number / modulo)


def note_to_index(abc_note):
    try:
        return all_notes.index(abc_note)
    except ValueError:
        return None


def str2bool(v):
    ''' converts a string to a boolean if necessary'''
    if type(v) == str:
        return v.lower() in ('yes', 'true', 't', '1')
    else:
        return v


def get_hash_code(*args):
    hash = hashlib.md5()
    for arg in args:
        hash.update(arg.encode('utf-8', 'ignore'))
        hash.update(program_name.encode('utf-8', 'ignore'))
    return hash.hexdigest()[:10]


def remove_non_note_fragments(abc, exclude_grace_notes=False):
    ''' remove parts of the ABC which is not notes or bar symbols by replacing them by spaces (in order to preserve offsets) '''

    repl_by_spaces = lambda m: ' ' * len(m.group(0))
    # replace non-note fragments of the text by replacing them by spaces (thereby preserving offsets), but keep also bar and repeat symbols
    abc = abc.replace('\r', '\n')
    abc = re.sub(r'(?s)%%beginps.+?%%endps', repl_by_spaces, abc)  # remove embedded postscript
    abc = re.sub(r'(?s)%%begintext.+?%%endtext', repl_by_spaces, abc)  # remove text
    abc = re.sub(comment_pattern, repl_by_spaces, abc) # remove comments
    abc = re.sub(r'\[\w:.*?\]', repl_by_spaces, abc)   # remove embedded fields
    abc = re.sub(r'(?m)^\w:.*?$', repl_by_spaces, abc) # remove normal fields
    abc = re.sub(r'\\"', repl_by_spaces, abc)          # remove escaped quote characters
    abc = re.sub(r'".*?"', repl_by_spaces, abc)        # remove strings
    abc = re.sub(r'!.+?!', repl_by_spaces, abc)        # remove ornaments like eg. !pralltriller!
    abc = re.sub(r'\+.+?\+', repl_by_spaces, abc)      # remove ornaments like eg. +pralltriller+
    if exclude_grace_notes:
        abc = re.sub(r'\{.*?\}', repl_by_spaces, abc)  # remove grace notes
    return abc


def get_notes_from_abc(abc, exclude_grace_notes=False):
    ''' returns a list of (start-offset, end-offset, abc-note-text) tuples for ABC notes/rests '''
    abc = remove_non_note_fragments(abc, exclude_grace_notes)

    # find and return ABC notes (including the text ranges)
    # 1.3.6.3 [JWDJ] 2015-3 made regex case sensitive again, because after typing Z and <space> a bar did not appear
    return [(note.start(0), note.end(0), note.group(0)) for note in
            re.finditer(r"([_=^]?[A-Ga-gz](,+|'+)?\d{0,2}(/\d{1,2}|/+)?)[><-]?", abc)]


def copy_bar_symbols_from_first_voice(abc):
    # normalize line endings (necessary for ^ in regexp) and extract the header and the two voices
    abc = re.sub(r'\r\n|\r', '\n', abc)
    m = re.match(r'(?sm)(.*?K:[^\n]+\s+)^V: *1(.*?)^V: *2\s*(.*)', abc)
    header, V1, V2 = m.groups()

    # replace strings and other parts with spaces and locate all bar symbols
    V1_clean = remove_non_note_fragments(V1)
    V2_clean = remove_non_note_fragments(V2)
    bar_seps1 = bar_sep_without_space.findall(V1_clean)
    bar_seps2 = bar_sep_without_space.findall(V2_clean)

    # abort, if the number of par symbols in the first and second voice doesn't match.
    if len(bar_seps1) != len(bar_seps2):
        print('warning: number of bar separators does not match (cannot complete operation)')
        return abc

    offset = 0
    for m in bar_sep_without_space.finditer(V2_clean):
        bar_symbol = bar_seps1.pop(0)
        bar_symbol = ' %s ' % bar_symbol.strip()
        start, end = m.start(0)+offset, m.end(0)+offset
        if bar_symbol != V2[start:end]:
            V2 = V2[:start] + bar_symbol + V2[end:]
            offset += len(bar_symbol) - (end-start)

    abc = header + 'V:1' + V1 + 'V:2\nI:repbra 0\n' + V2.lstrip()
    abc = abc.replace('\n', os.linesep)
    return abc


def process_MCM(abc):
    """ Processes sticky rhythm feature of mcmusiceditor https://www.mcmusiceditor.com/download/sticky-rhythm.pdf
    :param abc: abc possibly containing sticky rhythm
    :return: abc-compliant
    """
    abc, n = re.subn(r'(?m)^(L:\s*mcm_default)', r'L:1/8', abc)
    if n:
        # erase non-note fragments of the text by replacing them by spaces (thereby preserving offsets)
        repl_by_spaces = lambda m: ' ' * len(m.group(0))
        s = abc.replace('\r', '\n')
        s = re.sub(r'(?s)%%begin(ps|text).+?%%end(ps|text)', repl_by_spaces, s) # remove embedded text/postscript
        s = re.sub(r'(?m)^\w:.*?$|%.*$', repl_by_spaces, s)                 # remove non-embedded fields and comments
        s = re.sub(r'".*?"|!.+?!|\+\w+?\+|\[\w:.*?\]', repl_by_spaces, s)   # remove strings, ornaments and embedded fields

        fragments = []
        last_fragment_end = 0
        for m in re.finditer(r"(?P<note>([_=^]?[A-Ga-gxz](,+|'+)?))(?P<len>\d{0,2})(?P<dot>\.?)", s):
            if m.group('len') == '':
                length = 0
            else:
                length = Fraction(8, int(m.group('len')))
                if m.group('dot'):
                    length = length * 3 / 2

            start, end = m.start(0), m.end(0)
            fragments.append((False, abc[last_fragment_end:start]))
            fragments.append((True, m.group('note') + str(length)))
            last_fragment_end = end
        fragments.append((False, abc[last_fragment_end:]))
        abc = ''.join((text for is_note, text in fragments))
    return abc


def change_abc_tempo(abc_code, tempo_multiplier):
    ''' multiples all Q: fields in the abc code by the given multiplier and returns the modified abc code '''

    def subfunc(m, multiplier):
        try:
            if '=' in m.group(0):
                parts = m.group(0).split('=')
                parts[1] = str(int(int(parts[1])*multiplier))
                return '='.join(parts)

            q = int(int(m.group(1))*multiplier)
            if '[' in m.group(0):
                return '[Q: %d]' % q
            else:
                return 'Q: %d' % q
        except:
            return m.group(0)

    abc_code, n1 = re.subn(r'(?m)^Q: *(.+)', lambda m, mul=tempo_multiplier: subfunc(m, mul), abc_code)
    abc_code, _ = re.subn(r'\[Q: *(.+)\]', lambda m, mul=tempo_multiplier: subfunc(m, mul), abc_code)
    # if no Q: field that is not inline add a new Q: field after the X: line
    # (it seems to be ignored by abcmidi if added earlier in the code)
    if n1 == 0:
        default_tempo = 120
        extra_line = 'Q:%d' % int(default_tempo * tempo_multiplier)
        lines = text_to_lines(abc_code)
        for i in range(len(lines)):
            if lines[i].startswith('X:'):
                lines.insert(i+1, extra_line)
                break
        abc_code = os.linesep.join(lines)
    return abc_code


def sort_abc_tunes(abc_code, sort_fields, keep_free_text=True):
    lines = text_to_lines(abc_code)
    tunes = []
    file_header = []
    preceeding_lines = []
    Tune = namedtuple('Tune', 'lines header preceeding_lines')
    cur_tune = None
    for line in lines:

        if line.startswith('X:'):
            tune = Tune([], {}, [])
            if tunes:
                tune.preceeding_lines.extend(preceeding_lines)
            else:
                file_header = preceeding_lines
            preceeding_lines = []
            cur_tune = tune
            tunes.append(cur_tune)

        if cur_tune:
            cur_tune.lines.append(line)
            if re.match('[a-zA-Z]:', line):
                field = line[0]
                text = line[2:].strip().lower()
                if field == 'X':
                    try:
                        text = int(text)
                    except:
                        pass
                if field in cur_tune.header:
                    cur_tune.header[field] += '\n' + text
                else:
                    cur_tune.header[field] = text
            elif not line.strip():
                cur_tune = None
                preceeding_lines = [line]
        else:
            preceeding_lines.append(line)

    def get_sort_key_for_tune(tune, sort_fields):
        return tuple([tune.header.get(f, '').lower() for f in sort_fields])

    tunes = [(get_sort_key_for_tune(t, sort_fields), t) for t in tunes]
    tunes.sort()

    result = file_header
    for _, tune in tunes:
        if result and result[-1].strip() != '':
            result.append('')
        if keep_free_text:
            result.extend([l for l in tune.preceeding_lines if l.strip()])
        L = tune.lines[:]
        while L and not L[-1].strip():
            del L[-1]
        result.extend(L)
    return os.linesep.join(result)


def process_abc_code(settings, abc_code, header, minimal_processing=False, tempo_multiplier=None, landscape=False):
    ''' adds file header and possibly some extra fields, and may also change the Q: field '''

    #print traceback.extract_stack(None, 3)
    extra_lines = \
    '%%leftmargin 0.5cm\n' \
    '%%rightmargin 0.5cm\n' \
    '%%botmargin 0cm\n'  \
    '%%topmargin 0cm\n'

    if minimal_processing or settings['abcm2ps_clean']:
        extra_lines = ''

    if settings['abcm2ps_number_bars']:
        extra_lines += '%%barnumbers 1\n'
    if settings['abcm2ps_no_lyrics']:
        extra_lines += '%%musiconly 1\n'
    if settings['abcm2ps_refnumbers']:
        extra_lines += '%%withxrefs 1\n'
    if settings['abcm2ps_ignore_ends']:
        extra_lines += '%%continueall 1\n'
    if settings['abcm2ps_clean'] == False and settings['abcm2ps_defaults'] == False:
        extra_lines += '%%leftmargin ' + settings['abcm2ps_leftmargin'] + 'cm \n'
        extra_lines += '%%rightmargin ' + settings['abcm2ps_rightmargin'] + 'cm \n'
        extra_lines += '%%topmargin ' + settings['abcm2ps_topmargin'] + 'cm \n'
        extra_lines += '%%botmargin ' + settings['abcm2ps_botmargin'] + 'cm \n'
        extra_lines += '%%pagewidth ' + settings['abcm2ps_pagewidth'] + 'cm \n'
        extra_lines += '%%pageheight ' + settings['abcm2ps_pageheight'] + 'cm \n'

        extra_lines += '%%scale ' + settings['abcm2ps_scale'] + ' \n'
    parts = []
    if landscape and not minimal_processing:
        parts.append('%%landscape 1\n')
    if header:
        parts.append(header.rstrip() + os.linesep)
    if extra_lines:
        parts.append(extra_lines)
    parts.append(abc_code)
    abc_code = ''.join(parts)

    abc_code = re.sub(r'\[\[(.*/)(.+?)\]\]', r'\2', abc_code)  # strip PmWiki links and just include the link text
    if tempo_multiplier:
        abc_code = change_abc_tempo(abc_code, tempo_multiplier)

    abc_code = process_MCM(abc_code)

    # 1.3.6.3 [JWdJ] 2015-04-22 fixing newlines to part of process_abc_code
    abc_code = re.sub(r'\r\n|\r', '\n', abc_code)  ## TEST

    return abc_code


def fix_boxmarks_texts(abc):
    ''' Some Noteworthy Composer files use a special font where some note decorations are input
        as a single letter. Substitute real ABC decorations. '''
    decorations = {   # this list is not complete (eg. gliss decorations are currently left out)
        'c': '!arpeggio!',
        'h': 'T',
        'i': 'P',
        'j': 'P',
        'r': '!turn!',
        's': '!invertedturn!',
        't': 'u',
        'u': 'v',
        'x': '!<(!!<)!',
        'y': '!>(!!>)!',
        'z': '!>!', }
    abc = re.sub(r'"[^_]([%s])"' % ''.join(list(decorations)), lambda m: decorations[m.group(1)], abc)
    abc = abc.replace('"^tr"', 'T')
    return abc


def change_texts_into_chords(abc):
    ''' Change ABC fragments like "^G7" into "G7" by trying to identify strings that look like chords '''
    chord_types = 'm 7 m7 maj7 M7 6 m6 aug + aug7 dim dim7 9 m9 maj9 min Maj9 MAJ9 M9 11 dim9 sus sus4 Sus Sus4 sus9 7sus4 7sus9 5'.split()
    optional_chord_type = '(%s)?' % '|'.join(re.escape(c) for c in chord_types)
    return re.sub(r'(?<!\\)"[^_]([A-G][#b]? ?%s)(?<!\\)"' % optional_chord_type, r'"\1"', abc)
