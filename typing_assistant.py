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

import re
from fractions import Fraction

import wx
from wx import GetTranslation as _

from abc_transform import all_notes, note_to_index, get_notes_from_abc
from abc_tune import AbcTune
from aligner import bar_sep, get_bar_length, bar_and_voice_overlay_sep
from constants import tune_index_re
from midi2abc import duration2abc

doremi_prefixes = 'DRMFSLTdrmfslt' # 'd' corresponds to "do", 'r' to "re" and so on, DO vs. do is like C vs. c in ABC
doremi_suffixes = 'oeiaoaioOEIAOAIOlLhH'


def get_metre_and_default_length(abc):
    return AbcTune(abc).get_metre_and_default_length()


class TypingAssistant(object):
    """Keystroke handling in the editor: bracket completion, automatic bar lines and note durations, do-re-mi and keyboard input modes."""

    def __init__(self, frame):
        self.frame = frame
        self.keyboard_input_mode = False
        self.keyboard_input_base_note = None
        self.keyboard_input_base_key = None

    def OnDoReMiModeChange(self, evt=None):
        if self.frame.mni_TA_do_re_mi.IsChecked():
            self.frame.SetStatusText(_("&Do-re-mi mode").replace('&', ''))
        else:
            self.frame.SetStatusText('')

    def OnInsertSymbol(self, evt):
        item = self.frame.GetMenuBar().FindItemById(evt.Id)
        editor = self.frame.editor
        editor.SetSelectionEnd(editor.GetSelectionStart())
        self.AddTextWithUndo(item.GetHelp())
        self.frame.score_view.refresh_tunes()

    def AutoInsertXNum(self):
        xNum = 0
        editor = self.frame.editor
        get_line = editor.GetLine
        for line_no in range(editor.GetLineCount()):
            m = tune_index_re.match(get_line(line_no))
            if m:
                xNum = max(xNum, int(m.group(1)))

        editor.BeginUndoAction()
        p = editor.GetCurrentPos()
        editor.SetSelection(p, p)
        editor.ReplaceSelection(str(xNum+1))
        line = editor.GetCurrentLine()
        end_pos = editor.GetLineEndPosition(line)
        editor.SetSelection(end_pos, end_pos)
        editor.EndUndoAction()

    def DoReMiToNote(self, char):
        doremi_index = doremi_prefixes.find(char)
        if doremi_index >= 0:
            tune = self.frame.tune_list_controller.GetSelectedTune()
            if tune:
                editor = self.frame.editor
                matches = re.findall(r'(?<=[\r\n\[])K: *([A-Ga-g])', editor.GetTextRange(tune.offset_start, editor.GetCurrentPos()))
                if matches:
                    K = matches[-1]
                    base_note_index = note_to_index(K.upper())
                    note = all_notes[base_note_index + doremi_index]
                    if char == char.upper():
                        return note[0].upper()
                    else:
                        return note[0].lower()
        return char

    def OnCharEvent(self, evt):
        frame = self.frame
        # 1.3.7 [JWdJ] 2016-01-06
        current_svg_tune = frame.score_view.current_svg_tune
        if current_svg_tune and evt.KeyCode in [wx.WXK_PAGEDOWN, wx.WXK_PAGEUP, wx.WXK_HOME, wx.WXK_END]:
            # 1.3.7.0 [JWdJ] 2015-12 Added shortcuts to navigate through pages
            new_page = -1
            if evt.KeyCode == wx.WXK_HOME and evt.GetModifiers() == (wx.MOD_ALT + wx.MOD_CONTROL):
                new_page = 0
            elif evt.KeyCode == wx.WXK_END and evt.GetModifiers() == (wx.MOD_ALT + wx.MOD_CONTROL):
                new_page = current_svg_tune.page_count - 1
            elif evt.KeyCode == wx.WXK_PAGEDOWN and evt.GetModifiers() in [wx.MOD_ALT, wx.MOD_ALT + wx.MOD_CONTROL]:
                new_page = frame.current_page_index + 1
            elif evt.KeyCode == wx.WXK_PAGEUP and evt.GetModifiers() in [wx.MOD_ALT, wx.MOD_ALT + wx.MOD_CONTROL]:
                new_page = frame.current_page_index - 1

            if 0 <= new_page < current_svg_tune.page_count and new_page != frame.current_page_index:
                frame.score_view.select_page(new_page)
                evt.Skip()
                return

        editor = frame.editor
        cur_pos = editor.GetCurrentPos()
        in_music_code = self.position_is_music_code(cur_pos)

        c = chr(evt.GetUnicodeKey())
        p1, p2 = editor.GetSelection()
        no_selection = p1 == p2

        # 1.3.6.2 [JWdJ] 2015-02
        line, caret = editor.GetCurLine()
        is_inside_field = len(line)>=2 and line[1] == ':' and re.match(r'[A-Za-z\+]', line[0]) or line.startswith('%')
        if is_inside_field:
            evt.Skip()
            return
        is_inside_chord = self.position_is_in_chord(cur_pos)
        at_end_of_line = not line[caret:].strip(' \r\n|:][')
        use_typing_assist = frame.mni_TA_active.IsChecked()
        if use_typing_assist and in_music_code and not is_inside_chord:
            if c == '-' and no_selection:
                self.AddTextWithUndo('- ')
                return

            if c == ' ':
                try:
                    self.FixNoteDurations()
                    if no_selection and self.add_bar_if_needed():
                        return
                    else:
                        evt.Skip()
                except Exception:
                    evt.Skip()
                    raise
            elif frame.mni_TA_add_bar_auto.IsChecked() and no_selection and c not in "-/<,'1234567890\"!":
                if c in '|]&':
                    if c == ']':
                        bar_text = '|]'
                    else:
                        bar_text = c
                    if self.add_bar_if_needed(bar_text):
                        return
                elif c == ':':
                    if not (caret == 1 and line.rstrip() in [u'X', u'Z']) and self.add_bar_if_needed(':|'):
                        return
                else:
                    self.add_bar_if_needed()

        # when there is a selection and 's' is pressed it serves as a shortcut for slurring
        if p1 != p2 and c == 's':
            c = '('

        if c == ':':
            # fill in unique tune index after typing X:
            evt.Skip()
            if (line.rstrip(), caret) == (u'X', 1):
                wx.CallAfter(self.AutoInsertXNum)

        elif c == '3' and p1 == p2 and editor.GetTextRange(p1-1, p1+1) == '()' and in_music_code:
            # if the user writes ( which is auto-completed to () and then writes 3, he/she probably
            # wants to start a triplet so we delete the right parenthesis
            editor.BeginUndoAction()
            editor.SetSelection(p1, p1+1)
            editor.ReplaceSelection(c)
            editor.EndUndoAction()

        elif (c in ']}' and editor.GetTextRange(p1, p1+1) == c and in_music_code) or \
                (c == '"'  and editor.GetTextRange(p1, p1+1) == c and editor.GetTextRange(p1-1, p1) != '\\'):
            # unless this is not a field line
            if re.match('[a-zA-Z]:', line):
                evt.Skip()
            # if there is already a ] or }, just move one step to the right
            else:
                editor.SetSelection(p1+1, p1+1)

        elif c in '([{"':
            start, end = {'(': '()', '[': '[]', '{': '{}', '"': '""'}[c]

            # if this is a text or chord, then don't replace selection, but insert the new text/chord in front of the note(s) selected
            if c == '"':
                editor.SetSelection(p1, p1)
                p2 = p1

            first_char, last_char = editor.GetTextRange(p1-1, p1), editor.GetTextRange(p2, p2+1)
            orig_p1 = p1

            # if this is a triplet with a leading '(' then virtually move the selection start a bit to the left
            if p1 != p2 and last_char == ')' and editor.GetTextRange(p1-3, p1) == '((3':
                p1 -= 2
                first_char = '('
            if p1 != p2 and first_char == start and last_char == end and first_char != '"':
                editor.BeginUndoAction()
                editor.SetSelection(p2, p2+1)
                editor.ReplaceSelection('')
                editor.SetSelection(p1-1, p1)
                editor.ReplaceSelection('')
                editor.SetSelection(orig_p1-1, p2-1)
                editor.EndUndoAction()
            elif p1 != p2 and c != '[':
                editor.BeginUndoAction()
                # if this is a triplet, then start the slur just before '(3' instead of after.
                if c == '(' and last_char == ' ' and editor.GetTextRange(p1-2, p1) == '(3':
                    editor.InsertText(p1-2, start)
                else:
                    editor.InsertText(p1, start)
                editor.InsertText(p2+1, end)
                editor.SetSelection(p1+1, p2+1)
                editor.EndUndoAction()
            elif in_music_code and use_typing_assist and frame.mni_TA_add_right.IsChecked():
                if c == '"' and line.count('"') % 2 == 1 or \
                        c != '"' and line.count(end) > line.count(start):
                    evt.Skip()
                else:
                    editor.ReplaceSelection(start + end)
                    editor.SetSelection(p1+1, p1+1)
            else:
                evt.Skip()
        elif c in '<>' and (p2 - p1) > 1:
            try:
                editor.BeginUndoAction()
                base_pos = editor.GetSelectionStart()
                text = editor.GetSelectedText()
                notes = get_notes_from_abc(text, exclude_grace_notes=True)
                total_offset = 0
                for (start, end, abc_note_text) in notes[0::2]:
                    p = base_pos + end + total_offset
                    if re.match(r'[_=^]', abc_note_text):
                        p += 1
                    cur_char = editor.GetTextRange(p-1, p)
                    if cur_char == '<' and c == '>' or cur_char == '>' and c == '<':
                        editor.SetSelection(p-1, p)
                        editor.ReplaceSelection('')
                        total_offset -= 1
                    else:
                        editor.SetSelection(p, p)
                        editor.AddText(c)
                        total_offset += 1
                editor.SetSelection(p1, p2+total_offset)
            finally:
                editor.EndUndoAction()
        elif c == '.' and p1 != p2:
            # staccato selection
            try:
                editor.BeginUndoAction()
                base_pos = editor.GetSelectionStart()
                text = editor.GetSelectedText()
                notes = get_notes_from_abc(text, exclude_grace_notes=True)
                total_offset = 0
                for (start, end, abc_note_text) in notes:
                    p = base_pos + start + total_offset
                    #if re.match(r'[_=^]', abc_note_text):
                    #    p -= 1
                    cur_char = editor.GetTextRange(p-1, p)
                    if cur_char == '.':
                        editor.SetSelection(p-1, p)
                        editor.ReplaceSelection('')
                        total_offset -= 1
                    else:
                        editor.SetSelection(p, p)
                        editor.AddText(c)
                        total_offset += 1
                editor.SetSelection(p1, p2+total_offset)
            finally:
                editor.EndUndoAction()
        elif self.keyboard_input_mode and in_music_code:
            keys = u'asdfghjkl\xf6\xe4'
            sharp_keys = '' #u'\x00wertyuiop\xe5\x00'
            flat_keys = '' #u'<zxcvbnm,.-'

            i = -1
            if c in keys:
                i, accidental = keys.index(c), ''
            elif c in sharp_keys:
                i, accidental = sharp_keys.index(c), '^'
            elif c in flat_keys:
                i, accidental = flat_keys.index(c), '_'
            if i == -1:
                evt.Skip()
            else:
                if not self.keyboard_input_base_key:
                    self.keyboard_input_base_key = i
                else:
                    note = all_notes[i - self.keyboard_input_base_key + self.keyboard_input_base_note]
                    editor.ReplaceSelection(accidental + note)

        # automatically select uppercase/lowercase - choose the one that will make this note be closest to the previous note
        elif use_typing_assist and in_music_code and p1 == p2 and at_end_of_line and frame.mni_TA_auto_case.IsChecked() \
            and (not frame.mni_TA_do_re_mi.IsChecked() and c in 'abcdefgABCDEFG' or \
                  frame.mni_TA_do_re_mi.IsChecked() and c in doremi_prefixes):

            if frame.mni_TA_do_re_mi.IsChecked():
                c = self.DoReMiToNote(c)[0]

            # get the text of the previous and current line up to the position of the cursor
            prev_line = editor.GetLine(editor.GetCurrentLine()-1)
            text = prev_line + line[:caret]

            p = cur_pos

            last_note_number = None
            # go backwards (to the left from the cursor) and look for the first note
            for i in range(len(text)-1):
                if p-i >= 1 and self.position_is_music_code(p-i-1):
                    m = re.match(r"([A-Ga-g][,']?)", text[len(text)-1-i : len(text)-1-i+2])
                    if m:
                        last_note_number = note_to_index(m.group(0))
                        break

            if last_note_number is None:
                if frame.mni_TA_do_re_mi.IsChecked():
                    editor.AddText(c)
                else:
                    evt.Skip()
            else:
                # sort matching note by distance to the last note and give a slightly penalty to
                # note names that include ' or , since we prefer jumping to an alternative somewhere in the middle
                all_matches = [(abs(i - last_note_number) + int(',' in n)*0 + int("'" in n)*0, n)
                               for (i, n) in enumerate(all_notes)
                               if n[0].lower() == c.lower() and len(n) == 1]    # temporarily turned off my advanced logic
                all_matches.sort()
                if all_matches:
                    if evt.ShiftDown():
                        c = all_matches[1][1]  # second "best" choice
                    else:
                        c = all_matches[0][1]  # first choice
                    c = c[0]
                    editor.AddText(c)
                else:
                    evt.Skip()

        elif use_typing_assist and in_music_code and frame.mni_TA_do_re_mi.IsChecked():
            if c in doremi_prefixes:
                c = self.DoReMiToNote(c)
                editor.AddText(c)
            elif c not in doremi_suffixes:
                evt.Skip()

        else:
            evt.Skip()

    def FixNoteDurations(self):
        frame = self.frame
        # 1.3.6.2 [JWdJ] 2015-02
        use_add_note_durations = frame.mni_TA_active.IsChecked() and frame.mni_TA_add_note_durations.IsChecked()
        if not use_add_note_durations:
            return

        tune = frame.tune_list_controller.GetSelectedTune()
        if not tune:
            return

        editor = frame.editor
        line_start_offset = editor.PositionFromLine(editor.GetCurrentLine())
        text = editor.GetTextRange(line_start_offset, editor.GetCurrentPos())
        abc_up_to_selection = editor.GetTextRange(tune.offset_start, editor.GetCurrentPos())

        # find the position of the last bar symbol or space
        start_offset = max([0] + [m.start(0) for m in re.finditer('(%s)| ' % bar_sep.pattern, text)])
        text = text[start_offset:]
        notes = get_notes_from_abc(text, exclude_grace_notes=True)
        note_pattern = re.compile(r"(?P<note>([_=^]?[A-Ga-gxz]([,']+)?))(?P<len>\d{0,2}/\d{1,2}|/+|\d{0,2})(?P<dur_mod>[><]?)")

        # determine L: and M: fields
        metre, default_len = get_metre_and_default_length(abc_up_to_selection)

        # 1.3.6.3 [JWdJ] 2015-03
        if use_add_note_durations and not '[' in text:
            # does any of these notes have a duration specified?
            any_duration_specified = False
            for (start, end, abc_note_text) in notes:
                m = note_pattern.match(abc_note_text)
                if not m:
                    return
                if m.group('len'):
                    any_duration_specified = True
                    break
            if not any_duration_specified:
                total_duration = get_bar_length(text, default_len, metre)
                durations = []  # new durations to assign to notes
                if metre.denominator == 4 and total_duration != Fraction(1, 4):
                    if '(3' in text:
                        if len(notes) == 3:
                            durations = [Fraction(1,8), Fraction(1,8), Fraction(1,8)]
                    else:
                        if len(notes) == 1:
                            durations = [Fraction(1,4)]
                        elif len(notes) == 2:
                            durations = [Fraction(1,8)]*2
                        elif len(notes) == 3:
                            durations = [Fraction(1,8), Fraction(1,16), Fraction(1,16)]
                        elif len(notes) == 4:
                            durations = [Fraction(1,16)]*4
                elif str(metre) == str(Fraction(6, 8)):
                    if '(3' not in text:
                        if len(notes) == 1:
                            durations = [Fraction(3,8)]
                        if len(notes) == 2:
                            durations = [Fraction(1,4), Fraction(1,8)]
                        elif len(notes) == 3:
                            durations = [Fraction(1,8), Fraction(1,8), Fraction(1,8)]

                extra_offset = 0
                if durations:
                    sel_start = editor.GetSelectionStart()
                    editor.BeginUndoAction()
                    try:
                        for (d, (start, end, abc_note_text)) in zip(durations, notes):
                            abc_note_text_len = len(re.match(r"[_=^]?[A-Ga-gz](,+|'+)?", abc_note_text).group(0))
                            p = line_start_offset + start_offset + start + extra_offset + abc_note_text_len
                            dur_text = duration2abc(d / default_len)
                            extra_offset += len(dur_text)
                            editor.InsertText(p, dur_text)
                    finally:
                        editor.EndUndoAction()
                    sel_start += extra_offset
                    editor.SetSelection(sel_start, sel_start)

    def add_bar_if_needed(self, bar_text = '|'):
        frame = self.frame
        tune = frame.tune_list_controller.GetSelectedTune()
        if not tune:
            return

        # check if the bar is full and a new bar should start
        # 1.3.6.2 [JWdJ] 2015-02
        use_add_bar = frame.mni_TA_active.IsChecked() and (frame.mni_TA_add_bar.IsChecked() or frame.mni_TA_add_bar_auto.IsChecked())
        if use_add_bar:
            editor = frame.editor
            current_pos = editor.GetCurrentPos()
            line_start_offset = editor.PositionFromLine(editor.GetCurrentLine())
            text = editor.GetTextRange(line_start_offset, current_pos)
            abc_up_to_selection = editor.GetTextRange(tune.offset_start, current_pos)

            start_offset = max([0] + [m.end(0) for m in bar_and_voice_overlay_sep.finditer(text)])  # offset of last bar symbol
            text = text[start_offset:]  # the text from the last bar symbol up to the selection point
            metre, default_len = get_metre_and_default_length(abc_up_to_selection)

            # 1.3.6.1 [JWdJ] 2015-01-28 bar lines for multirest Zn
            end_of_line_offset = editor.GetLineEndPosition(editor.GetCurrentLine())
            rest_of_line = editor.GetTextRange(current_pos, end_of_line_offset).strip()
            if re.match(r"^[XZ]\d*$", text):
                duration = metre
            else:
                duration = get_bar_length(text, default_len, metre)

            if (duration == metre and not bar_sep.match(rest_of_line) and
                    not (text.rstrip() and text.rstrip()[-1] in '[]:|')):
                self.insert_bar(bar_text)
                return True

    def insert_bar(self, bar_text = '|'):
        editor = self.frame.editor
        # 1.3.6.3 [JWDJ] 2015-3 don't add space before or after bar if space already present
        current_pos = editor.GetCurrentPos()
        pre_space = ''
        post_space = ''
        if current_pos > 0 and editor.GetTextRange(current_pos-1, current_pos) not in ' \r\n:':
            pre_space = ' '
        if current_pos == editor.GetTextLength() or editor.GetTextRange(current_pos, current_pos+1) != ' ':
            post_space = ' '
        self.AddTextWithUndo(pre_space + bar_text + post_space)
        if not post_space:
            skip_space_pos = editor.GetCurrentPos() + 1
            editor.SetSelection(skip_space_pos, skip_space_pos)

    def AddTextWithUndo(self, text):
        editor = self.frame.editor
        editor.BeginUndoAction()
        editor.AddText(text)
        editor.EndUndoAction()

    def replace_selection(self, text):
        editor = self.frame.editor
        editor.BeginUndoAction()
        editor.ReplaceSelection(text)
        editor.EndUndoAction()

    def position_is_music_code(self, position):
        styler = self.frame.styler
        style_at = self.frame.editor.GetStyleAt
        return style_at(position) == styler.STYLE_DEFAULT \
            and style_at(position-1) not in (styler.STYLE_EMBEDDED_FIELD_VALUE, styler.STYLE_EMBEDDED_FIELD, styler.STYLE_COMMENT_NORMAL)

    def position_is_in_chord(self, position):
        style_at = self.frame.editor.GetStyleAt
        return style_at(position-1) == self.frame.styler.STYLE_CHORD

    def OnKeyDownEvent(self, evt):
        # temporary work-around for what seems to be a scintilla bug on Mac:
        if wx.Platform == "__WXMAC__" and evt.GetRawKeyCode() == 7683:
            wx.CallAfter(lambda: self.AddTextWithUndo('^'))
            evt.Skip()
            return

        frame = self.frame
        editor = frame.editor
        line, caret = editor.GetCurLine()
        in_music_code = self.position_is_music_code(editor.GetCurrentPos())

        use_typing_assist = frame.mni_TA_active.IsChecked()
        if evt.GetKeyCode() == wx.WXK_RETURN:
            # 1.3.7.2 [JWDJ] 2016-03-17
            if in_music_code and use_typing_assist and frame.mni_TA_add_bar_auto.IsChecked():
                self.add_bar_if_needed()

            # 1.3.6.3 [JWDJ] 2015-04-21 Added line continuation
            if use_typing_assist:
                line = editor.GetCurrentLine()
                for prefix in ['W:', 'w:', 'N:', 'H:', '%%', '%', '+:']:
                    prev_line = editor.GetLine(line-1)
                    if prev_line.startswith(prefix) and editor.GetLine(line).startswith(prefix):
                        if prev_line.startswith(prefix + ' '):  # whether to add a space after W:
                            prefix += ' '
                        wx.CallAfter(lambda: self.AddTextWithUndo(prefix))
                        break
            evt.Skip()
        elif evt.GetKeyCode() == wx.WXK_TAB:
            if in_music_code and editor.GetSelectionStart() == editor.GetSelectionEnd():
                wx.CallAfter(lambda: self.insert_bar())
            else:
                evt.Skip()
        elif evt.GetUnicodeKey() == ord('L') and evt.CmdDown():
            frame.score_view.ScrollMusicPaneToMatchEditor(select_closest_note=True, select_closest_page=frame.mni_auto_refresh.IsChecked())
        else:
            evt.Skip()

    def StartKeyboardInputMode(self):
        editor = self.frame.editor
        line_start_offset = editor.PositionFromLine(editor.GetCurrentLine())
        text = editor.GetTextRange(line_start_offset, editor.GetCurrentPos()) # line up to selection position
        notes = get_notes_from_abc(text)
        if notes:
            self.keyboard_input_mode = True
            m = re.match(r"([_=^]?)(?P<note>[A-Ga-gz][,']*)", notes[-1][-1])
            self.keyboard_input_base_note = note_to_index(m.group('note'))
            self.keyboard_input_base_key = None
            if self.keyboard_input_base_note == -1:
                self.keyboard_input_mode = False
