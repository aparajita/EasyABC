#!/usr/bin/env python3

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

import os
import re

import wx
from wx import GetTranslation as _

from abc_tools import get_output_from_process
from abc_transform import str2bool, change_abc_tempo, process_MCM
from abc_tune import voice_re, AbcTune
from app_state import app_state
from constants import default_midi_volume, default_midi_pan
from dialogs import MyInfoFrame, MyAbcFrame
from tune_model import text_to_lines, MidiTune

gchordpat = re.compile('\"[^\"]+\"')
keypat = re.compile('([A-G]|[a-g]|)(#|b?)')


def test_for_guitar_chords(abccode):
    ''' The function returns False if there are no guitar chords
        in the tune abccode; otherwise it returns True. It is
        not sufficient to just find a token with enclosed by
        double quotes. The token must begin with a letter between
        A-G or a-g. We try up to 5 times in case, the token is
        used to present other information above the staff.

        The function is used to create a cleaner processed file
        for MIDI by eliminating unnecessary %%MIDI commands.
    '''
    i = 0
    k = 0
    found = False
    while k < 5:
        m = gchordpat.search(abccode, i)
        if m:
            token = m.group(0)
            i = m.end() + 1
            if keypat.match(token[1:-1]):
                found = True
                break
        else:
            break
        k = k + 1
    return found


def list_voices_in(abccode):
    ''' The function scans the entire abccode searching for V:
        and extracts the voice identifier (assuming it is not
        too long). A list of all the unique identifiers are
        returned.
    '''
    voices = []
    [voices.append(v) for v in [m.group('voice_id') or m.group('inline_voice_id') for m in voice_re.finditer(abccode)] if v not in voices]
    return voices


def grab_time_signature(abccode):
    ''' The function detects the first time signature M: n/m in
        abccode and returns [n, m].
    '''
    fracpat = re.compile(r'(\d+)/(\d+)')
    loc = abccode.find('M:')
    meter = abccode[loc+2:loc+10]
    meter = meter.lstrip()
    if meter.find('C') >= 0:
        return [4, 4]
    m = fracpat.match(meter)
    if m:
        num = int(m.group(1))
        den = int(m.group(2))
    else:  #no M: in tune
        num = 4
        den = 4
    return [num, den]


def drum_intro(timesig):
    ''' Depending on the numerator of the time signature, the function
        returns a MIDI drum command which produces a sequence of clicks.
    '''
    n = timesig[0]
    if n == 2:
        d = '%%MIDI drum dd 77 76'
    elif n == 3:
        # 1.3.6.4 [SS] 2015-09-06
        d = '%%MIDI drum ddd 77 76 76'
    elif n == 4:
        d = '%%MIDI drum dddd 77 76 77 76 110 50 60 50'
    elif n == 6:
        d = '%%MIDI drum dddddd 77 76 76 77 76 76 110 50 50 60 50 50'
    elif n == 9:
        d = '%%MIDI drum ddddddddd 77 76 76 77 76 76 77 76 76 110 50 50 60 50 50 60 50 50'
    else:
        d = '%%MIDI drum d 77'
    return d


def need_left_repeat(abccode):
    ''' Determine whether a left repeat |: is missing. If there
        are no right repeats (either :| or ::) then we do not need
        a left repeat. If a right repeat is found then we need
        to find a left repeat that appears before the first right
        repeat. Otherwise it is missing.
     '''
    loc1 = abccode.find(r':|')
    loc2 = abccode.find(r'::')
    if loc1 != -1 and loc2 != -1:
        loc = min(loc1, loc2)
    elif loc1 != -1:
        loc = loc1
    elif loc2 != -1:
        loc = loc2
    else:
        # no right repeat found
        return False

    loc1 = abccode.find(r'|:')
    if loc1 == -1:
        # left repeat missing but right repeat found
        return True
    if loc1 < loc:
        return False
    # left repeat found after right repeat. (Left repeat
    # missing for first repeat block.)
    return True


def make_abc_introduction(abccode, voicelist):
    ''' Given the music in abc notation, the function creates a sequence
        of clicks which counts in the tune. The function needs to determine
        the time signature and a list of all the voice names in the tune.
        If there are no voices, the sequence is in inserted after the first K:;
        otherwise, the sequence is inserted into the first voice and the
        other voices are padded with silent measures. Frequently, the
        left repeat symbol is omitted. We need to put a left repeat after
        the clicking sequence so that clicking sequence is not repeated.
    '''
    intro = []
    meter = grab_time_signature(abccode)

    if voicelist:
        intro.append("V: {0}".format(voicelist[0]))
    intro.append(drum_intro(meter))
    intro.append("%%MIDI drumon")
    if need_left_repeat(abccode):
        intro.append("Z|Z|:\\")
    else:
        intro.append("Z|Z|\\")
    intro.append("%%MIDI drumoff")

    if voicelist:
        for v in voicelist[1:]:
            intro.append("V: {0}".format(v))
            if need_left_repeat(abccode):
                intro.append("Z|Z|:\\")
            else:
                intro.append("Z|Z|\\")
    return intro


def add_abc2midi_options(cmd, settings, add_follow_score_markers):
    #Force BF option flag to be at the last position according to jwdj/EasyABC#86 and sshlien/abcmidi#8
    #if str2bool(settings['barfly']):
    #    cmd.append('-BF')
    if str2bool(settings['nofermatas']):
        cmd.append('-NFER')
    if str2bool(settings['nograce']):
        cmd.append('-NGRA')
    if str2bool(settings['nodynamics']):
        cmd.append('-NFNP')
    # 1.3.6.3 [SS] 2015-03-20
    if settings['tuning'] != '440':
        cmd.append('-TT %s' % settings['tuning'])
    # 1.3.6.4 [JWDJ] 2016-06-22
    if add_follow_score_markers:
        cmd.append('-EA')
    if str2bool(settings['barfly']):
        cmd.append('-BF')
    return cmd


def abc_to_midi(abc_code, settings, midi_file_name, add_follow_score_markers):

    abc2midi_path = settings.get('abc2midi_path')
    cmd = [abc2midi_path, '-', '-o', midi_file_name]
    cmd = add_abc2midi_options(cmd, settings, add_follow_score_markers)
    app_state.messages += '\nAbcToMidi\n' + " ".join(cmd)
    input_abc = abc_code + os.linesep * 2
    stdout_value, stderr_value, returncode = get_output_from_process(cmd, input=input_abc)
    app_state.messages += '\n' + stdout_value + stderr_value
    if stdout_value:
        stdout_value = re.sub(r'(?m)(writing MIDI file .*\r?\n?)', '', stdout_value)
    if returncode != 0:
        # 1.3.7.0 [SS] 2016-01-06
        app_state.messages += '\n' + _('%(program)s exited abnormally (errorcode %(error)#8x)') % { 'program': 'AbcToMidi', 'error': returncode & 0xffffffff }
        return None

    return midi_file_name


def process_abc_for_midi(abc_code, header, cache_dir, settings, tempo_multiplier):
    ''' This function inserts extra lines in the abc tune controlling the assignment of musical instruments to the different voices
        per the instructions in the ABC Settings/abc2midi and voices. If the tune already contains these instructions, eg. %%MIDI program,
        %%MIDI chordprog, etc. then the function avoids changing these assignments by suppressing the output of the additional commands.
        Note that these assignments can also be embedded in the body of the tune using the instruction [I: MIDI = program 10] for
        examples see https://abcmidi.sourceforge.io/ and click link [I:MIDI=...].
    '''
    ####   set all the control flags which determine which %%MIDI commands are written

    play_chords = settings.get('play_chords')
    default_midi_program = settings.get('midi_program')
    default_midi_chordprog = settings.get('midi_chord_program')
    default_midi_bassprog = settings.get('midi_bass_program')
    # 1.3.6.4 [SS] 2015-06-07
    default_midi_melodyvol = settings.get('melodyvol')
    default_midi_chordvol = settings.get('chordvol')
    default_midi_bassvol = settings.get('bassvol')
    # 1.3.6.3 [SS] 2015-05-04
    default_tempo = settings.get('bpmtempo')
    # build the list of midi program to be used for each voice
    midi_program_ch_list = ['midi_program_ch%d' % ch for ch in range(1, 16 + 1)]

    # this flag is added just in case none would have been set but shouldn't be the case.
    if not default_midi_bassprog:
        default_midi_bassprog = default_midi_chordprog

    # verify if MIDI instructions are already present if yes, no extra command should be added

    add_midi_program_extra_line = True
    add_midi_volume_extra_line = True # 1.3.6.3 [JWDJ] 2015-04-21 added so that when abc contains instrument selection, the volume from the settings can still be used
    add_midi_gchord_extra_line = True
    add_midi_chordprog_extra_line = True
    add_midi_introduction = settings.get('midi_intro')  # 1.3.6.4 [SS] 2015-07-05

    if not test_for_guitar_chords(abc_code):
        add_midi_chordprog_extra_line = False
        add_midi_gchord_extra_line = False

    # 1.3.6.3 [JWDJ] 2015-04-17 header was forgotten when checking for MIDI directives
    abclines = text_to_lines(header + abc_code)
    for line in abclines:
        if line.startswith('%%MIDI program'):
            add_midi_program_extra_line = False
        elif line.startswith('%%MIDI control 7 '):
            add_midi_volume_extra_line = False
        elif line.startswith('%%MIDI gchord'):
            add_midi_gchord_extra_line = False
        elif line.startswith('%%MIDI chordprog') or line.startswith('%%MIDI bassprog'):
            add_midi_chordprog_extra_line = False
        if not (add_midi_program_extra_line or add_midi_volume_extra_line or add_midi_gchord_extra_line or add_midi_chordprog_extra_line):
            break

    #### create the abc_header which will be placed in front of the processed abc file
    # extra_lines is a list of all the MIDI commands to be put in abcheader

    #FAU: enforce at least one extra_lines to avoid to introduce a blank line
    extra_lines = ['%']

    # build default list of midi_program
    # this is needed in case no instrument per voices where defined or in case option "separate defaults per voice" is not checked

    midi_program_ch = []
    for channel in range(16):
        midi_program_ch.append([default_midi_program, default_midi_volume, default_midi_pan])

    separate_defaults_per_voice = settings.get('separate_defaults_per_voice', False)
    if separate_defaults_per_voice:
        for channel in range(16):
            program_vol_pan = settings.get(midi_program_ch_list[channel])
            if program_vol_pan:
                midi_program_ch[channel] = program_vol_pan

    # Though these instructions shouldn't be needed (they are added for each voice afterwards),
    # there is a problem with QuickTime on the Mac and these lines ensure that the MIDI file is
    # played correctly.
    if wx.Platform == "__WXMAC__":
        for channel in range(16):
            extra_lines.append('%%MIDI program {0} {1}'.format(channel+1, midi_program_ch[channel][0]))
        extra_lines.append('%%MIDI program {0}'.format(default_midi_program)) # 1.3.6 [SS] 2014-11-16
    if add_midi_volume_extra_line:
        extra_lines.append('%%MIDI control 7 {0}'.format(midi_program_ch[0][1]))
        extra_lines.append('%%MIDI control 10 {0}'.format(midi_program_ch[0][2]))

    # add extra instruction to play guitar chords
    if add_midi_gchord_extra_line:
        if play_chords:
            extra_lines.append('%%MIDI gchordon')
            # 1.3.6 [SS] 2014-11-26
            gchord = settings.get('gchord')
            if gchord and gchord != 'default':
                extra_lines.append('%%MIDI gchord '+ gchord)

        else:
            extra_lines.append('%%MIDI gchordoff')
    # add extra instruction to define instrument for guitar chords and bass
    # These lines should be added to only the voices that have guitar chords. However,
    # unless we scan the voice in advance, we do not know whether it does have guitar
    # chords. There is nothing wrong in including these commands in every voice since
    # they will be ignored if nonapplicable; but it makes a rather messy processed for
    # midi file which is harder to interpret.

    # The extra_lines are added after X:1 in case the tune is not multivoice but
    # has guitar chords embedded. If it is a multivoice tune or the tune does not
    # have guitar chords, these lines are not necessary but do not do any harm.
    #
    # 1.3.6.4 [SS] 2015-06-29
    if add_midi_program_extra_line:
        extra_lines.append('%%MIDI program {0}'.format(default_midi_program))

    if add_midi_chordprog_extra_line:
        extra_lines.append('%%MIDI chordprog {0}'.format(default_midi_chordprog))
        extra_lines.append('%%MIDI bassprog {0}'.format(default_midi_bassprog))
        # 1.3.6.4 [SS] 2015-06-07
        extra_lines.append('%%MIDI chordvol {0}'.format(default_midi_chordvol))
        extra_lines.append('%%MIDI bassvol {0}'.format(default_midi_bassvol))

    # 1.3.6.3 [SS] 2015-03-19
    if int(settings.get('transposition', 0)) != 0:
        extra_lines.append('%%MIDI transpose {0}'.format(settings['transposition']))

    # 1.3.6.3 [SS] 2015-05-04
    if default_tempo != 120:
        extra_lines.append('Q:1/4 = %s' % default_tempo)

    abcheader = os.linesep.join(extra_lines + [header.strip()])

    # 1.3.6.4 [SS] 2015-07-07
    voicelist = list_voices_in(abc_code)
    # 1.3.6.4 [SS] 2015-07-03
    if add_midi_introduction:
        midi_introduction = make_abc_introduction(abc_code, voicelist)

    ####  modify abc_code to add MIDI instruction just after voice definition
    # (because using channel only in header doesn't seem to allow association with voice

    abclines = text_to_lines(abc_code) # 1.3.6.3 [JWDJ] 2015-04-17 split abc_code without header

    # 1.3.7.0 [SS] 2016-01-05
    # always add %%MIDI control 7 so user can control volume of melody
    #if add_midi_program_extra_line or add_midi_gchord_extra_line or add_midi_introduction:
    if True:  # 1.3.7.0 [SS] 2016-01-05
        list_voice = [] # keeps track of the voices we have already seen
        new_abc_lines = [] # contains the new processed abc tune
        voice = 0
        header_finished = False
        for line in abclines:
            new_abc_lines.append(line)
            # do not take into account the definition present in the header (maybe it would be better... to be further analysed)
            if line.startswith('K:'):
                if not header_finished:
                    # 1.3.6.4 [SS] 2015-07-09
                    if len(voicelist) == 0:
                        new_abc_lines.append('%%MIDI control 7 {0}'.format(int(default_midi_melodyvol)))
                    # 1.3.6.4 [SS] 2015-07-03
                    if add_midi_introduction:
                        new_abc_lines.extend(midi_introduction)
                header_finished = True
            if header_finished:
                match = voice_re.match(line)
                if match:
                    inline_voice_id = match.group('inline_voice_id')
                    voice_ID = inline_voice_id or match.group('voice_id')
                    if voice_ID not in list_voice:
                        # 1.3.6.4 [SS] 2015-07-08
                        # if it is an inline voice, we are not want to include the following notes before
                        # specifying the %%MIDI parameters
                        if inline_voice_id:
                            # remove last line in new_abc and put it back afterwards
                            removedline = new_abc_lines.pop()
                            new_abc_lines.append('V: {0}'.format(voice_ID))

                        # 1.3.6.4 [SS] 2015-06-19
                        # ideally you should determine whether gchords are present in this voice
                        voice_has_gchords = True

                        #as it's a new voice, add MIDI program instruction
                        list_voice.append(voice_ID)
                        if add_midi_program_extra_line:
                            new_abc_lines.append('%%MIDI program {0}'.format(midi_program_ch[voice][0]))
                        if add_midi_volume_extra_line:
                            new_abc_lines.append('%%MIDI control 7 {0}'.format(midi_program_ch[voice][1]))
                            new_abc_lines.append('%%MIDI control 10 {0}'.format(midi_program_ch[voice][2]))

                        if voice_has_gchords:
                            if add_midi_gchord_extra_line:
                                if play_chords:
                                    new_abc_lines.append('%%MIDI gchordon')
                                else:
                                    new_abc_lines.append('%%MIDI gchordoff')
                            if add_midi_chordprog_extra_line:
                                new_abc_lines.append('%%MIDI chordprog {0}'.format(default_midi_chordprog))
                                new_abc_lines.append('%%MIDI bassprog {0}'.format(default_midi_bassprog))
                                # 1.3.6.4 [SS] 2015-06-19
                                new_abc_lines.append('%%MIDI chordvol {0}'.format(default_midi_chordvol))
                                new_abc_lines.append('%%MIDI bassvol {0}'.format(default_midi_bassvol))
                        if inline_voice_id:
                            new_abc_lines.append(removedline)
                        voice += 1
                        if voice == 16:
                            voice = 0

        abc_code = os.linesep.join(new_abc_lines)

    #### assemble everything together

    # 1.3.6.4 [SS] 2014-07-07 replacement for process_abc_code
    # we do not want any abcm2ps options added
    sections = [abcheader.rstrip() + os.linesep, abc_code]
    abc_code = ''.join(sections) # put it together
    abc_code = re.sub(r'\[\[(.*/)(.+?)\]\]', r'\2', abc_code)  # strip PmWiki links and just include the link text
    if tempo_multiplier:
        abc_code = change_abc_tempo(abc_code, tempo_multiplier)
    abc_code = process_MCM(abc_code)
    # 1.3.6.3 [JWdJ] 2015-04-22 fixing newlines to part of process_abc_code
    abc_code = re.sub(r'\r\n|\r', '\n', abc_code)  ## TEST
    # 1.3.6 [SS] 2014-12-17
    #abc_code = process_abc_code(settings,abc_code, abcheader, tempo_multiplier=tempo_multiplier, minimal_processing=True)

    abc_code = abc_code.replace(r'\"', ' ')  # replace escaped " characters with space since abc2midi doesn't understand them

    # make sure that X field is on the first line since abc2midi doesn't seem to support
    # fields and instructions that come before the X field
    if not abc_code.startswith('X:'):
        abclines = text_to_lines(abc_code) # take it apart again
        for i in range(len(abclines)):
            if abclines[i].startswith('X:'):
                line = abclines[i]
                del abclines[i]
                abclines.insert(0, line)
                break
        abc_code = os.linesep.join(abclines) # put it back together

    #### for debugging
    #Write temporary abc_file (for debug purpose)
    #temp_abc_file =  os.path.abspath(os.path.join(cache_dir, 'temp_%s.abc' % hash)) 1.3.6 [SS] 2014-11-13
    temp_abc_file = os.path.abspath(os.path.join(cache_dir, 'temp.abc')) # 1.3.6 [SS] 2014-11-13
    with open(temp_abc_file, 'w', encoding='utf-8', newline='') as f:
        f.write(abc_code)

    return abc_code


def AbcToMidi(abc_code, header, cache_dir, settings, statusbar, tempo_multiplier, midi_file_name=None, add_follow_score_markers=False):

    abc_code = process_abc_for_midi(abc_code, header, cache_dir, settings, tempo_multiplier)
    app_state.visible_abc_code = abc_code #p09 2014-10-22 [SS]

    abc_tune = AbcTune(abc_code)
    if midi_file_name is None:
        midi_file_name = os.path.abspath(os.path.join(cache_dir, 'temp%s.midi' % abc_tune.tune_id))
        # midi_file_name = generate_temp_file_name(cache_dir, '.midi')
    midi_file = abc_to_midi(abc_code, settings, midi_file_name, add_follow_score_markers)
    # P09 2014-10-26 [SS]
    MyInfoFrame.update_text()

    # 1.3.6 2014-12-16 [SS]
    MyAbcFrame.update_text()

    # 1.3.6 [SS] 2014-12-08
    if app_state.messages.find('Error') != -1:
        statusbar.SetStatusText(_('{0} reported some errors').format('Abc2midi'))
    elif app_state.messages.find('Warning') != -1:
        statusbar.SetStatusText(_('{0} reported some warnings').format('Abc2midi'))
    else:
        statusbar.SetStatusText('')

    if midi_file:
        return MidiTune(abc_tune, midi_file)
    else:
        return None
