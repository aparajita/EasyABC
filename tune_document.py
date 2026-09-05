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
import traceback
from collections import namedtuple
from datetime import datetime

import wx
from wx import GetTranslation as _

from abc_character_encoding import get_encoding_abc, decode_abc
from abc_tools import NWCToXml, AbcToPDF, launch_file
from abc_transform import sort_abc_tunes, fix_boxmarks_texts, change_texts_into_chords
from abc_tune import strip_comments
from app_state import app_state
from constants import program_name, cwd, WX4, line_end_re, tune_index_re
from dialogs import IncipitsFrame, generate_incipits_abc
from exceptions import AbortException, NWCConversionException
import menu_builder
from tune_model import Tune, text_to_lines
from utils import read_entire_file
from xml2abc_interface import xml_to_abc


def abc_bytes_to_text(file_as_bytes):
    encoding = get_encoding_abc(file_as_bytes)
    if encoding and encoding != 'utf-8':
        try:
            return file_as_bytes.decode(encoding)
        except UnicodeError:
            try:
                text = file_as_bytes.decode('utf-8')
                modal_result = wx.MessageBox(_("This ABC file seems to be encoded using UTF-8 but contains no indication of this fact. "
                                               "It is strongly recommended that an I:abc-charset field is added in order for you to load the file and safely save changes to it. "
                                               "Do you want EasyABC to add this for you automatically?"), _("Add abc-charset field?"), wx.ICON_QUESTION | wx.YES | wx.NO)
                if modal_result == wx.YES:
                    text = os.linesep.join(('I:abc-charset utf-8', text))
                return text
            except UnicodeError:
                pass
    try:
        return file_as_bytes.decode('utf-8')
    except UnicodeError:
        return file_as_bytes.decode('latin-1')


def fix_end_of_line_sequence(text):
    if wx.Platform == "__WXMAC__":
        return text.replace('\r\n', '\n')
    else:
        # text = re.sub('\r+', '\r', text)
        if not '\n' in text:
            text = text.replace('\r', '\r\n')
        return text


class TuneDocument(object):
    """The file behind the editor: its path, its display name, and loading and saving it."""

    def __init__(self, frame):
        self.frame = frame
        self._current_file = None
        self.untitled_number = 1
        self.document_name = None
        self.updating_text = False

    @property
    def current_file(self):
        return self._current_file

    @current_file.setter
    def current_file(self, value):
        self._current_file = value
        if value:
            self.add_recent_file(value)

    def new_tune(self):
        self.document_name = _('Untitled') + ' %d' % self.untitled_number
        self.frame.SetTitle('%s - %s' % (program_name, self.document_name))
        self.frame.editor.ClearAll()
        self.frame.editor.SetSavePoint()

    def add_recent_file(self, value):
        recent_files = self.frame.settings.get('recentfiles', '').split('|')
        if recent_files[0] != value:
            if value in recent_files:
                recent_files.remove(value)
            recent_files.insert(0, value)
            if len(recent_files) > 10:
                recent_files = recent_files[:10]
            self.frame.settings['recentfiles'] = '|'.join(recent_files)
            menu_builder.update_recent_files_menu(self.frame)

    def CanClose(self, dont_ask = False):
        if self.frame.editor.GetModify():
            if dont_ask:
                result = wx.ID_YES
            else:
                result = self.ask_save()
            if result == wx.ID_YES:
                if self.current_file:
                    try:
                        self.save()
                    except IOError:
                        wx.MessageBox(_("Error: there was some trouble saving the file."), _("File could not be saved properly"), wx.OK)
                        return False
                else:
                    result = self.save_as()
            if result == wx.ID_CANCEL:
                return False

        if self.frame.playback.record_thread != None:
            self.frame.playback.record_thread.abort()
            self.frame.playback.record_thread = None
        return True

    def OnNew(self, evt=None):
        self.frame.save_settings()
        frame = wx.GetApp().NewMainFrame()
        frame.Show(True)
        # move new window slightly down to the right:
        width, height = tuple(wx.DisplaySize())
        x, y = self.frame.GetPosition()
        x, y = (x + 40) % (width - 200), (y + 40) % (height - 200)
        frame.Move((x, y))
        return frame

    def OnOpen(self, evt):
        wildcard = _("ABC file") + " (*.abc;*.txt;*.mcm)|*.abc;*.txt;*.mcm|" + \
                   _('Any file') + " (*.*)|*"
        dlg = wx.FileDialog(
            self.frame, message=_("Open ABC file"),
            defaultFile="", wildcard=wildcard, style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_CHANGE_DIR )
        try:
            if dlg.ShowModal() == wx.ID_OK:
                if not self.frame.editor.GetModify() and not self.current_file:     # if a new unmodified document
                    self.load(dlg.GetPath())
                else:
                    frame = self.OnNew()
                    frame.document.load(dlg.GetPath())
        finally:
            dlg.Destroy() # 1.3.6.3 [JWDJ] 2015-04-21 always clean up dialog window

    def OnImport(self, evt):
        wildcard = _('Any music file') + " (*.abc;*.txt,*.mcm;*.mid;*.midi;*.xml;*.mxl;*.nwc)|*.abc;*.txt;*.mcm;*.mid;*.midi;*.xml;*.mxl;*.nwc|" + \
                   _('ABC file') + " (*.abc;*.txt;*.mcm)|*.abc;*.txt;*.mcm|" + \
                   _('Midi file') + " (*.mid;*.midi)|*.mid;*.midi|" + \
                   _('MusicXML') + " (*.xml;*.mxl)|*.xml;*.mxl|" + \
                   _('Noteworthy Composer file') + " (*.nwc)|*.nwc|" + \
                   _('Any file') + " (*.*)|*"
        dlg = wx.FileDialog(
            self.frame, message=_('Import and add tune'), #defaultDir='',
            defaultFile="", wildcard=wildcard, style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_CHANGE_DIR )
        try:
            if dlg.ShowModal() == wx.ID_OK:
                self.OnDropFile(dlg.GetPath())
        finally:
            dlg.Destroy() # 1.3.6.3 [JWDJ] 2015-04-21 always clean up dialog window
        # self.UpdateTuneList() # 1.3.7.4 [JWDJ] No need to explicitly update tunelist, because adding lines triggers UpdateTuneList

    def load_or_import(self, filepath):
        if not self.frame.editor.GetModify() and not self.frame.editor.GetText().strip() and os.path.splitext(filepath)[1].lower() in ('.txt', '.abc', '.mcm', ''):
            self.load(filepath)
        else:
            self.OnDropFile(filepath)

    def load(self, filepath, editor_pos = None):
        try:
            file_as_bytes = read_entire_file(filepath)
        except IOError:
            wx.MessageBox(_("Could not find file.\nIt may have been moved or deleted. Choose File,Open to locate it."), _("File not found"), wx.OK)
            return

        text = abc_bytes_to_text(file_as_bytes)
        text = fix_end_of_line_sequence(text)

        self.current_file = filepath
        self.document_name = filepath
        self.frame.SetTitle('%s - %s' % (program_name, self.document_name))
        self.updating_text = True
        try:
            self.frame.editor.ClearAll()
            self.frame.editor.SetText(text)
            if editor_pos:
                self.frame.editor.SetCurrentPos(editor_pos)
            self.frame.editor.SetSavePoint()
            self.frame.editor.EmptyUndoBuffer()
        finally:
            self.updating_text = False

        self.frame.tune_list_controller.UpdateTuneList()
        if editor_pos:
            self.frame.tune_list_controller.select_tune_at_current_pos()
        else:
            self.frame.tune_list.Select(0)

    def load_and_position(self, filepath, editor_pos):
        # import cProfile
        # profiler = cProfile.Profile()
        # profiler.enable()

        # self.Freeze()
        # try:
        if self.current_file == filepath:
            self.frame.editor.SetCurrentPos(editor_pos)
            self.frame.tune_list_controller.select_tune_at_current_pos()
        else:
            self.load(filepath, editor_pos)
        # finally:
        #     self.Thaw()

        # import pstats
        # p = pstats.Stats(profiler)
        # p.strip_dirs().sort_stats('cumulative').reverse_order().print_stats()

    def ask_save(self):
        dlg = wx.MessageDialog(self.frame, _('Do you want to save your changes to %s?') % self.document_name,
                               _('Save changes?'), wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION)
        modal_result = dlg.ShowModal()
        dlg.Destroy()
        return modal_result

    def save(self):
        if self.current_file is None:
            self.save_as()
        else:
            f = open(self.current_file, 'wb')
            s = self.frame.editor.GetText()
            encoding = 'utf-8'
            try:
                s.encode(encoding, 'strict')
            except UnicodeEncodeError as e: # 1.3.6.2 [JWdJ] 2015-02
                sample_letters = s[e.start:e.end][:30]
                modal_result = wx.MessageBox(_("This document contains characters (eg. %(ABC)s) that cannot be represented using the current character encoding (%(encoding)s). "
                                               "Do you want to switch to using UTF-8 as your character encoding (recommended)? "
                                               "(choosing No may cause some of these characters to be replaced by '?' when they are saved)") %
                                               {'ABC': sample_letters, 'encoding': encoding},
                                             _('Switch to UTF-8 encoding?'), wx.ICON_QUESTION | wx.YES | wx.NO)
                if modal_result == wx.YES:
                    s = os.linesep.join(('I:abc-charset utf-8', s))
                    self.frame.editor.BeginUndoAction()
                    self.frame.editor.SetText(s)
                    self.frame.editor.EndUndoAction()

            f.write(s.encode(encoding, 'replace'))
            f.close()
            self.add_recent_file(self.current_file)
            self.frame.editor.SetSavePoint()

    def save_as(self, directory=None):
        wildcard = _('ABC file') + " (*.abc)|*.abc"
        defaultDir = ''
        if self.current_file:
            defaultDir = os.path.dirname(self.current_file) or directory or cwd
        dlg = wx.FileDialog(
                self.frame, message=_('Save ABC file %s') % self.document_name, defaultDir=defaultDir,
                defaultFile="", wildcard=wildcard, style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT | wx.FD_CHANGE_DIR
                )
        try:
            result = dlg.ShowModal()
            if result == wx.ID_OK:
                if os.path.exists(dlg.GetPath()):
                    if wx.MessageDialog(self.frame,
                                        _('The file already exists. Do you want to overwrite the existing file?'),
                                        _('Overwrite existing file?'), wx.YES_NO | wx.NO_DEFAULT | wx.CANCEL | wx.ICON_QUESTION).ShowModal() != wx.ID_YES:
                        return wx.ID_CANCEL
                self.current_file = dlg.GetPath()
                self.document_name = os.path.basename(self.current_file)
                self.frame.SetTitle('%s - %s' % (program_name, self.document_name))
                self.save()
        finally:
            dlg.Destroy() # 1.3.6.3 [JWDJ] 2015-04-21 always clean up dialog window
        return result

    def OnSave(self, evt):
        self.save()

    def OnSaveAs(self, evt):
        self.save_as()

    def OnCloseFile(self, evt):
        if self.CanClose():
            self.current_file = None
            self.untitled_number += 1
            self.new_tune()
            self.frame.tune_list_controller.OnTuneSelected(None)

    def OnDropFile(self, filename):
        info_messages = []
        # [SS] 2014-12-18
        options = namedtuple ('Options', 'u m c d n b v x p j t v1 ped s stm')                     # emulate the options object
        options.m = 0; options.j = 0; options.p = []; options.b = 0; options.d = 0  # unused options
        options.n = 0; options.v = 0; options.u = 0; options.c = 0; options.x = 0   # but all may be used if needed
        options.t = 0; options.v1 = False; options.ped = True; options.s = 0; options.stm = 0
        settings = self.frame.settings
        if settings['xmlunfold']:
            options.u = 1
        if settings['xmlmidi']:
            options.m = 1
        if settings['xml_v'] != 0:
            options.v = int(settings['xml_v'])
        if settings['xml_n'] != 0:
            options.n = int(settings['xml_n'])
        if settings['xml_b'] != 0:
            options.b = int(settings['xml_b'])
        if settings['xml_c'] != 0:
            options.c = int(settings['xml_c'])
        if settings['xml_d'] != 0:
            options.d = int(settings['xml_d'])
        # 1.3.6.1 [SS] 2015-01-08
        if settings['xml_p'] != '' and settings['xml_p'] != 0:
            p = settings['xml_p'].split(',')
            for elem in p:
                options.p.append(float(elem))

        editor = self.frame.editor
        try:
            extension = os.path.splitext(filename)[1].lower()
            p = editor.GetLength()
            editor.SetSelection(p, p)
            if extension in ('.xml', '.mxl', '.musicxml'):
                # 1.3.6 [SS] 2014-12-18
                self.frame.typing_assistant.AddTextWithUndo(u'\n%s\n' % xml_to_abc(filename,options,info_messages))
                app_state.messages = u'abc_to_xml '+ filename
                for infoline in info_messages:
                    app_state.messages += infoline
                return True
            if extension == '.nwc':
                try:
                    xml_file_path = NWCToXml(filename, self.frame.cache_dir, settings.get('nwc2xml_path', None))
                    # 1.3.6 [SS] 2014-12-18
                    abc_code = xml_to_abc(xml_file_path,options,info_messages)
                    abc_code = fix_boxmarks_texts(abc_code)
                    abc_code = change_texts_into_chords(abc_code)
                # 1.3.6.2 [JWdJ] 2015-02
                except NWCConversionException as e:
                    dlg = wx.MessageDialog(self.frame, str(e), _('nwc2xml error'), wx.OK | wx.CANCEL)
                    result = dlg.ShowModal()
                    dlg.Destroy()
                    if result == wx.ID_OK:
                        return True
                    else:
                        raise AbortException()
                self.frame.typing_assistant.AddTextWithUndo(u'\n%s\n' % abc_code)
                return True
            elif extension in ('.abc', '.txt', '.mcm', ''):
                editor.BeginUndoAction()
                editor.AddText('\n\n')
                editor.AddText(open(filename, 'r').read().strip())
                editor.AddText('\n\n')
                editor.EndUndoAction()
                return True
            elif extension in ('.mid', '.midi'):
                return self.frame.handle_midi_conversion(filename=filename)
        except AbortException:
            raise
        except:
            error_msg = traceback.format_exc()
            dlg = wx.MessageDialog(self.frame, error_msg, _('Error'), wx.OK | wx.CANCEL)
            dlg.ShowModal()
            dlg.Destroy()
            raise
        self.frame.execmessage_time = datetime.now() # 1.3.6 [SS] 2014-12-11


class TuneList(object):
    """The tunes found in the editor text and the list control that shows them."""

    def __init__(self, frame):
        self.frame = frame
        self.tunes = []
        self.selected_tune = None
        self.multi_tunes_menu_items = []

    def GetTunes(self):
        editor = self.frame.editor
        pos_from_line = editor.PositionFromLine
        get_text_range = editor.GetTextRange
        get_line = editor.GetLine
        search_tune_index = tune_index_re.search
        cur_index = None
        cur_startline = None
        cur_title = u''
        titles_found = 0
        tunes = []
        tunes_append = tunes.append
        n = editor.GetLineCount()
        for i in range(n):
            p = pos_from_line(i)
            try:
                t = get_text_range(p, p+2)
            except:
                t = ''
            if t == 'X:':
                if cur_index is not None:
                    tunes_append((cur_index, cur_title, cur_startline))
                    cur_index = None
                m = search_tune_index(get_line(i))
                if m:
                    cur_index = int(m.group(1))
                    cur_startline = i
                cur_title = u''
                titles_found = 0
            elif t == 'T:' and titles_found < 2 and cur_index is not None:
                title = decode_abc(strip_comments(get_line(i)[2:]).strip())
                cur_title = ' - '.join(filter(None, (cur_title, title)))

        if cur_index is not None:
            tunes_append((cur_index, cur_title, cur_startline))
        return tunes

    def GetTune(self, listbox_index, add_file_header=True):
        tune_list = self.frame.tune_list
        index = tune_list.GetItemData(listbox_index)  # remap index in case items are sorted
        if index in tune_list.itemDataMap:
            (xnum, title, line_no) = tune_list.itemDataMap[index]
            offset_start = self.frame.editor.PositionFromLine(line_no)
            offset_start, offset_end = self.GetTextRangeOfTune(offset_start)
            if add_file_header:
                header, num_header_lines = self.GetFileHeaderBlock()
            else:
                header, num_header_lines = '', 0
            abc = self.frame.editor.GetTextRange(offset_start, offset_end)
            return Tune(xnum, title, '', offset_start, offset_end, abc, header, num_header_lines)
        else:
            return None

    def GetTuneAbc(self, startpos):
        editor = self.frame.editor
        get_line = editor.GetLine
        first_line_no = editor.LineFromPosition(startpos)
        lines = []
        for line_no in range(first_line_no, editor.GetLineCount()):
            line = get_line(line_no)
            if line.startswith('X:'):
                break
            lines.append(line)
        return ''.join(lines)

    def GetSelectedTune(self, add_file_header=True):
        tune_list = self.frame.tune_list
        selItem = tune_list.GetFirstSelected()
        if selItem >= 0:
            return self.GetTune(selItem, add_file_header)
        elif tune_list.ItemCount > 0:
            return self.GetTune(0, add_file_header)
        else:
            return None

    def GetSelectedTunes(self, add_file_header=True):
        return [self.GetTune(i, add_file_header) for i in self.selected_tune_iterator()]

    def selected_tune_iterator(self):
        tune_list = self.frame.tune_list
        i = tune_list.GetFirstSelected()
        if i >= 0:
            while i >= 0:
                yield i
                i = tune_list.GetNextSelected(i)
        elif tune_list.ItemCount > 0:
            yield 0

    def GetTextRangeOfTune(self, offset):
        position = offset
        editor = self.frame.editor
        start_line = editor.LineFromPosition(position)
        line_count = editor.GetLineCount()
        get_line = editor.GetLine
        end_line = start_line + 1
        while end_line < line_count and not get_line(end_line).startswith('X:'):
            end_line += 1
        end_position = editor.PositionFromLine(end_line)
        return (position, end_position)

    def GetTextPositionOfTune(self, tune_index):
        editor = self.frame.editor
        position = editor.FindText(0, editor.GetTextLength(), 'X:%s' % tune_index, 0)
        if position == -1:
            position = editor.FindText(0, editor.GetTextLength(), 'X: %s' % tune_index, 0)
        return position

    def GetFileHeaderBlock(self):
        if self.frame.settings.get('abc_include_file_header', True):
            # collect all header lines
            lines = []
            # 1.3.6.4 [SS] 2015-09-07
            getall = False
            editor = self.frame.editor
            get_line = editor.GetLine
            for i in range(editor.GetLineCount()):
                line = get_line(i)
                if line.startswith('X:') or line.startswith('T:'):
                    break
                elif re.match(r'%%beginps',line):
                    getall = True
                    lines.append(line)
                elif re.match(r'%%.*|[a-zA-Z_]:.*', line):
                    lines.append(line)
                elif getall:
                    lines.append(line)
                if re.match(r'%%endps',line):
                    getall = False
            abc = ''.join(lines)
            # remove certain fields that are probably only used for title fields
            abc = re.sub(r'(?ms)(^%%multicol start.*%%multicol end[ \t]*?[\r\n]+)', '', abc)
            abc = re.sub(r'(?ms)(^%%begintext.*%%endtext.*?[\r\n]+)', '', abc)
            abc = re.sub(r'(?m)(^%%(EPS|text|multicol|center|sep|vskip|newpage).*[\r\n]*)', '', abc)

            num_header_lines = len(line_end_re.findall(abc))

            return (abc, num_header_lines)
        else:
            return ('', 0)

    def UpdateTuneList(self, reselect_tune=False):
        tune_list = self.frame.tune_list
        selected_tune_index = None
        if reselect_tune:
            first_selected = tune_list.GetFirstSelected()
            if first_selected > 0:
                selected_tune_index = tune_list.GetItemData(tune_list.GetFirstSelected())
        tunes = self.GetTunes()
        tune_list.itemDataMap = dict(enumerate(tunes))

        different = (len(tunes) != len(self.tunes))
        if not different:
            for tune1, tune2 in zip(tunes, self.tunes):
                different = different or (tune1[:-1] != tune2[:-1])    # compare xnum, title but not line_no
        if different:
            top_item = tune_list.GetTopItem()
            tune_list.Freeze()
            tune_list.DeleteAllItems()
            set_item = tune_list.SetStringItem
            insert_item = tune_list.InsertStringItem
            set_item_data = tune_list.SetItemData
            get_item_count = tune_list.GetItemCount
            if WX4:
                insert_item = tune_list.InsertItem
                set_item = tune_list.SetItem
            for xnum, title, line_no in tunes:
                index = insert_item(get_item_count(), str(xnum))
                set_item(index, 1, title)
                set_item_data(index, index)

            last_index = get_item_count() - 1
            if selected_tune_index is not None and selected_tune_index <= last_index:
                tune_list.Select(selected_tune_index)

            # try to restore scroll state
            if tunes and top_item >= 0:
                last_visible_index = top_item + tune_list.GetCountPerPage() - 1
                if last_visible_index > last_index:
                    last_visible_index = last_index
                tune_list.EnsureVisible(last_visible_index)

            tune_list.Thaw()

        self.tunes = tunes

        self.SelectOnlyTuneIfTuneNotSelected()

    def UpdateTuneListAndReselectTune(self):
        self.UpdateTuneList(reselect_tune=True)

    def OnTuneSelected(self, evt):
        frame = self.frame

        # 1.3.6.4 [SS] 2015-06-11 -- to maintain consistency for different media players
        # self.reset_BpmSlider()

        dt = datetime.now() - frame.execmessage_time # 1.3.6 [SS] 2014-12-11
        dtime = dt.seconds*1000 + dt.microseconds // 1000
        if evt is not None and dtime > 20000:
            app_state.messages = u''
        self.selected_tune = None
        self.update_multi_tunes_menu_items()

        tune = self.GetSelectedTune()
        if tune:
            frame.score_view.music_update_thread.ConvertAbcToSvg(tune.abc, tune.header)
            if evt and (wx.Window.FindFocus() != frame.editor and not (frame.find_replace.find_dialog and frame.find_replace.find_dialog.IsActive() or frame.find_replace.replace_dialog and frame.find_replace.replace_dialog.IsActive())):
                # 1.3.6.2 [JWdJ] 2015-02
                frame.music_pane.current_page.clear_note_selection()
                frame.score_view.selected_note_descs = []

                # HideLines() does not work correctly on either Windows
                # or Linux. The goal was to display only the selected
                # tune in the edit window using documented options
                # in the wxpython StyledTextCtrl widget. [SS] 2014-9-18
                #lastline = self.editor.LineFromPosition(tune.offset_end)
                #firstline = self.editor.LineFromPosition(tune.offset_start)
                #print 'from ',firstline,' to ',lastline
                #self.editor.HideLines(1,firstline)

                frame.editor.SetSelection(tune.offset_start, tune.offset_start)
                frame.editor.ScrollToLine(frame.editor.LineFromPosition(tune.offset_start))
                frame.music_pane.Scroll(0, 0)

                frame.error_pane = frame.manager.GetPane('error message').Hide()
                frame.manager.Update()

    def OnTuneDeselected(self, evt):
        tune_list = self.frame.tune_list
        selected = tune_list.GetFirstSelected()
        if selected >= 0 and tune_list.GetNextSelected(selected) < 0:
            self.OnTuneSelected(evt)
        self.update_multi_tunes_menu_items()

    def OnTuneListClick(self, evt):
        self.frame.tune_list.SetFocus()
        evt.Skip()

    def OnTuneDoubleClicked(self, evt):
        self.frame.OnToolStop(evt)
        self.frame.OnToolPlay(evt)
        evt.Skip()

    def SelectOnlyTuneIfTuneNotSelected(self):
        if len(self.tunes) == 1 and self.frame.tune_list.GetFirstSelected() == -1:
            self.frame.tune_list.Select(0)
            self.OnTuneSelected(None)

    def MoveTune(self, from_index, to_index):
        tune_list = self.frame.tune_list
        editor = self.frame.editor
        tune_list.GetItemData(from_index)
        (_, _, line_no) = tune_list.itemDataMap[from_index]
        offset_start = editor.PositionFromLine(line_no)
        offset_start, offset_end = self.GetTextRangeOfTune(offset_start)

        (_, _, line_no) = tune_list.itemDataMap[to_index]
        insert_pos = editor.PositionFromLine(line_no)

        if insert_pos > offset_start:
            _, insert_pos = self.GetTextRangeOfTune(insert_pos)
            insert_pos -= offset_end - offset_start

        editor.BeginUndoAction()
        abc = editor.GetTextRange(offset_start, offset_end)
        editor.SetSelection(offset_start, offset_end)
        editor.ReplaceSelection('')
        editor.InsertText(insert_pos, abc)
        editor.SetSelection(insert_pos, insert_pos)
        editor.EndUndoAction()

    def OnMoveTuneUp(self, evt):
        tune_list = self.frame.tune_list
        selected_index = tune_list.GetFirstSelected()
        if selected_index > 0:
            tune_list.DeselectAll()
            self.MoveTune(selected_index, selected_index - 1)

    def OnMoveTuneDown(self, evt):
        tune_list = self.frame.tune_list
        selected_index = tune_list.GetFirstSelected()
        if selected_index < tune_list.ItemCount - 1:
            tune_list.DeselectAll()
            self.MoveTune(selected_index, selected_index + 1)

    def OnSortTunes(self, evt):
        editor = self.frame.editor
        dlg = wx.TextEntryDialog(
            self.frame, _('Which field(s) do you want to sort the tunes by? (eg. T for title)'), _('Sort tunes'), 'T')
        try:
            if dlg.ShowModal() == wx.ID_OK:
                sort_fields = re.findall('[A-Za-z]', dlg.GetValue())
                text = sort_abc_tunes(editor.GetText(), sort_fields)
                editor.BeginUndoAction()
                editor.SetText(text)
                editor.EndUndoAction()
        finally:
            dlg.Destroy() # 1.3.6.3 [JWDJ] 2015-04-21 always clean up dialog window

    def OnRenumberTunes(self, evt):
        editor = self.frame.editor
        dlg = wx.TextEntryDialog(
            self.frame, _('Please specify the index of the first tune: '), _('Renumber X: fields'), '1')
        try:
            if dlg.ShowModal() == wx.ID_OK:
                xnum = int(dlg.GetValue())
                lines = text_to_lines(editor.GetText())
                for i in range(len(lines)):
                    if re.match(r'X:\s*\d+\s*$', lines[i]):
                        if lines[i].startswith('X: '):
                            lines[i] = 'X: %d' % xnum
                        else:
                            lines[i] = 'X:%d' % xnum
                        xnum += 1
                editor.BeginUndoAction()
                editor.SetText(os.linesep.join(lines))
                editor.EndUndoAction()
        finally:
            dlg.Destroy() # 1.3.6.3 [JWDJ] 2015-04-21 always clean up dialog window

    def update_multi_tunes_menu_items(self):
        tune_list = self.frame.tune_list
        selected = tune_list.GetFirstSelected()
        multi_select = selected >= 0 and tune_list.GetNextSelected(selected) >= 0

        for menu_item in self.multi_tunes_menu_items:
            menu_item.Enable(multi_select)

    def select_tune_at_current_pos(self):
        frame = self.frame
        line_no = frame.editor.LineFromPosition(frame.editor.GetCurrentPos())
        total_tunes = frame.tune_list.GetItemCount()
        found_index = next((i for i, (index, title, startline) in enumerate(self.tunes) if startline > line_no), total_tunes) - 1

        tune_list = frame.tune_list
        get_item_data = tune_list.GetItemData
        if found_index == -1:
            tune_list.DeselectAll()
        else:
            index = next((i for i in range(tune_list.GetItemCount()) if get_item_data(i) == found_index), -1)  # list could be sorted
            if index != -1:
                if index == tune_list.GetFirstSelected():
                    frame.score_view.ScrollMusicPaneToMatchEditor(select_closest_page=frame.mni_auto_refresh.IsChecked())
                else:
                    tune_list.DeselectAll()
                    tune_list.SelectItem(index)
                    tune_list.EnsureVisible(index)
                    frame.music_pane.Scroll(0, 0)

        if frame.abc_assist_panel.IsShown():
            frame.abc_assist_panel.update_assist()

    def OnMovedToDifferentLine(self, queue_number_movement):
        if self.frame.score_view.queue_number_movement != queue_number_movement:
            return

    def OnGenerateIncipits(self, evt):
        main_frame = self.frame
        dlg = IncipitsFrame(main_frame, main_frame.settings)
        try:
            modal_result = dlg.ShowModal()
        finally:
            dlg.Destroy() # 1.3.6.3 [JWDJ] 2015-04-21 always clean up dialog window
        if modal_result != wx.ID_OK:
            return

        main_frame.SetCursor(wx.HOURGLASS_CURSOR)
        abc = generate_incipits_abc(main_frame.settings, self, main_frame.tune_list.GetItemCount(), main_frame.editor)
        main_frame.SetCursor(wx.STANDARD_CURSOR)

        frame = main_frame.document.OnNew()
        frame.editor.SetText(abc)
        frame.editor.SetSavePoint()
        frame.editor.EmptyUndoBuffer()
        frame.document.document_name = main_frame.document.document_name + ' ' + _('incipits')
        frame.SetTitle('%s - %s' % (program_name, frame.document.document_name))
        frame.tune_list_controller.UpdateTuneList()
        frame.tune_list.Select(0)

    def OnViewIncipits(self, evt):
        main_frame = self.frame
        dlg = IncipitsFrame(main_frame, main_frame.settings)
        try:
            modal_result = dlg.ShowModal()
        finally:
            dlg.Destroy() # 1.3.6.3 [JWDJ] 2015-04-21 always clean up dialog window
        if modal_result != wx.ID_OK:
            return
        try:
            main_frame.SetCursor(wx.HOURGLASS_CURSOR)
            abc = generate_incipits_abc(main_frame.settings, self, main_frame.tune_list.GetItemCount(), main_frame.editor)
            pdf_file = AbcToPDF(main_frame.settings, abc, '', main_frame.cache_dir, main_frame.settings.get('abcm2ps_extra_params', ''),
                                main_frame.settings.get('abcm2ps_path', ''),
                                main_frame.settings.get('gs_path',''),
                                #main_frame.settings.get('ps2pdf_path',''),
                                main_frame.settings.get('abcm2ps_format_path', ''))
            if pdf_file:
                launch_file(pdf_file)
            else:
                wx.MessageBox(_("Error: there was some trouble saving the file."), _("File could not be saved properly"), wx.OK)
        finally:
            main_frame.SetCursor(wx.STANDARD_CURSOR)
        self.select_tune_at_current_pos()
