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
import threading

import wx
import wx.lib.mixins.listctrl as listmix
from wx.lib.embeddedimage import PyEmbeddedImage
from wx import GetTranslation as _

from abc_tune import find_start_of_tune, get_tune_title_at_pos, find_end_of_tune
from constants import control_margin
from tune_model import read_abc_file
from utils import search_files
from wxhelper import create_menu, append_menu_item, wx_dirdialog, wx_show_message, wx_insert_dropdown_value

search_parts_re = re.compile(r'(?:^| )([A-Za-z]:|%%)')
clean_lyrics_re = re.compile(r'\s*(?:-|\\-|\*|\|)\s*')


def lyrics_to_text(lyrics):
    return clean_lyrics_re.sub('', lyrics)


class SearchFilesThread(threading.Thread):
    def __init__(self, root, searchstring, searchfields, on_after_search, sort_search_results):
        threading.Thread.__init__(self)
        self.daemon = True
        self._stop_event = threading.Event()
        self.root = root
        self.searchstring = searchstring
        self.searchfields = searchfields
        self.on_after_search = on_after_search
        self.sort_search_results = sort_search_results
        self.search_results = []
        self.start()

    def abort(self):
        self._stop_event.set()

    @property
    def abort_requested(self):
        return self._stop_event.is_set()

    def run(self):
        self.find_abc_files(self.root, self.searchstring, self.searchfields)
        if self.sort_search_results:
            self.search_results = sorted(self.search_results, key=lambda sr: sr[0])

        if self.on_after_search is not None:
            wx.CallAfter(self.on_after_search, self.abort_requested, self.search_results)

# 1.3.6 [SS] 2014-11-23
    def find_abc_files(self, root, searchstring, searchfields):
        abcmatches = []
        for pathname in search_files(root, ['.abc', '.ABC']):  # currently not abortable
            abcmatches.append(pathname)

        search_parts = self.extract_search_parts(searchstring, searchfields)
        for pathname in abcmatches:
            self.find_abc_string(pathname, search_parts)
            if self.abort_requested:
                break

    def extract_search_parts(self, searchtext, searchfields):
        abckey = searchfields  # default search in title
        if not abckey or not abckey[0]:
            abckey = 'T:'
        search_parts = []
        allow_empty_text = False
        pos = 0
        for m in search_parts_re.finditer(searchtext):
            text = searchtext[pos:m.start(1)]
            self.add_searchpart(search_parts, abckey, text, allow_empty_text)
            abckey = m.group(1)
            pos = m.end(1)
            allow_empty_text = True

        text = searchtext[pos:]
        self.add_searchpart(search_parts, abckey, text, allow_empty_text)

        if not search_parts:
            search_parts.append([('T:', None)])
        return search_parts

    @staticmethod
    def add_searchpart(search_parts, abckey, text, allow_empty_text=False):
        if text or allow_empty_text:
            words = text.strip().lower().split()
            if isinstance(abckey, str):
                search_parts.append([(abckey, words)])
            else:
                search_parts.append([(k, words) for k in abckey])

# 1.3.6 [SS] 2014-11-30
    def find_abc_string(self, path, search_parts):
        wholefile = read_abc_file(path)
        prev_found_tune_positions = None
        for search_part in search_parts:
            found_tune_positions = {}
            for abckey, words in search_part:
                convert_line = lambda s: s
                if abckey in ('w:', 'W:'):
                    convert_line = lyrics_to_text

                loc = 0
                while loc != -1:
                    loc = wholefile.find(abckey, loc)
                    if loc == -1:
                        break
                    line_end = wholefile.find('\n', loc)
                    if line_end == -1:
                        break
                    if wholefile[loc - 1] == '\n':
                        start_pos = loc + len(abckey)
                        line = wholefile[start_pos:line_end]

                        index = 0
                        if words:
                            lline = convert_line(line).lower()
                            for word in words:
                                if word:
                                    index = lline.find(word)
                                    if index == -1:
                                        break  # all words must match

                        if index != -1:
                            start_pos += index
                            tune_start = find_start_of_tune(wholefile, start_pos)
                            if prev_found_tune_positions is None or tune_start in prev_found_tune_positions:
                                found_tune_positions[tune_start] = start_pos
                    loc = line_end
            prev_found_tune_positions = found_tune_positions

        if prev_found_tune_positions:
            for tune_pos in prev_found_tune_positions:
                title = get_tune_title_at_pos(wholefile, tune_pos)
                index = found_tune_positions[tune_pos]
                self.search_results.append((title, path, index))

    def get_result_for_index(self, index):
        _, path, pos = self.search_results[index]
        return path, pos  # character position in file


class FlexibleListCtrl(wx.ListCtrl, listmix.ColumnSorterMixin, listmix.ListCtrlAutoWidthMixin):
    def __init__(self, parent, ID, pos=wx.DefaultPosition, size=wx.DefaultSize, style=0):
        wx.ListCtrl.__init__(self, parent, ID, pos, size, style)
        listmix.ListCtrlAutoWidthMixin.__init__(self)
        listmix.ColumnSorterMixin.__init__(self, 3)
        self._resizeCol = 2
        self._resizeColStyle = "COL"
        self._resizeColMinWidth = 10
        self.il = wx.ImageList(1, 16)
        SmallUpArrow = PyEmbeddedImage(
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABHNCSVQICAgIfAhkiAAAADxJ"
        "REFUOI1jZGRiZqAEMFGke2gY8P/f3/9kGwDTjM8QnAaga8JlCG3CAJdt2MQxDCAUaOjyjKMp"
        "cRAYAABS2CPsss3BWQAAAABJRU5ErkJggg==")

        SmallDnArrow = PyEmbeddedImage(
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABHNCSVQICAgIfAhkiAAAAEhJ"
        "REFUOI1jZGRiZqAEMFGke9QABgYGBgYWdIH///7+J6SJkYmZEacLkCUJacZqAD5DsInTLhDR"
        "bcPlKrwugGnCFy6Mo3mBAQChDgRlP4RC7wAAAABJRU5ErkJggg==")
        self.sm_up = self.il.Add(SmallUpArrow.GetBitmap())
        self.sm_dn = self.il.Add(SmallDnArrow.GetBitmap())
    def GetListCtrl(self):
        return self
    def GetSortImages(self):
        return (self.sm_dn, self.sm_up)
    def getColumnText(self, index, col):
        item = self.GetItem(index, col)
        text = item.GetText()
        return text
    def GetSecondarySortValues(self, col, key1, key2):
        """Returns a tuple of 2 values to use for secondary sort values when the
           items in the selected column match equal.  The default just returns the
           item data values."""
        if col == 0:
            return (self.itemDataMap[key1][1], self.itemDataMap[key2][1])
        elif col >= 1:
            return (self.itemDataMap[key1][0], self.itemDataMap[key2][0])
        else:
            return (None, None)

    def SelectItem(self, index, select=True):
        self.Select(index, select)

    def DeselectAll(self):
        item = self.GetFirstSelected()
        while item != -1:
            nextItem = self.GetNextSelected(item)
            self.SelectItem(item, False)
            item = nextItem


class AbcSearchPanel(wx.Panel):
    ''' For searching a directory of abc files for tunes containing a string. '''
    def __init__(self, parent, settings, statusbar):
        wx.Panel.__init__(self, parent)
        self.settings = settings
        self.statusbar = statusbar
        self.mainwindow = parent
        border = control_margin
        self.max_results = 5000

        find_what_label = wx.StaticText(self, wx.ID_ANY, _('Find what') + ':')

        default_choices = ['C:mozart', 'w:love', 'R:jig', 'M:6/8']
        self.find_what_ctrl = wx.ComboBox(self, wx.ID_ANY, choices=default_choices, style=wx.CB_DROPDOWN | wx.TE_PROCESS_ENTER)
        self.focus_find_what()
        self.show_search_options_button = wx.Button(self, wx.ID_ANY, '...', size=(26, -1))

        options = [(_('Title'), 'T:'), (_('Composer'), 'C:'), (_('Lyrics'), 'w: W:')]
        searchfields = self.get_searchfields()
        menu = create_menu([], parent=self)
        for label, field in options:
            menuitem = append_menu_item(menu, label + ' (' + field + ')', '', self.on_toggle_option, kind=wx.ITEM_CHECK)
            menuitem.Help = field
            menuitem.Check(field.split()[0] in searchfields)
        menu.AppendSeparator()
        menuitem = append_menu_item(menu, _('Sort by title'), '', self.on_toggle_sort_search_results, kind=wx.ITEM_CHECK)
        menuitem.Check(settings.get('sort_search_results', True))

        self.search_menu = menu

        searchfolder_label = wx.StaticText(self, wx.ID_ANY, _("Look in") + ':')
        self.searchfolder_ctrl = wx.TextCtrl(self, wx.ID_ANY, settings['searchfolder'], style=wx.TE_PROCESS_ENTER)
        self.choose_search_folder_button = wx.Button(self, wx.ID_ANY, '...', size=(26, -1))

        self.progress = wx.Gauge(self, wx.ID_ANY)
        self.progress.Hide()
        self.progress_timer = None
        if wx.Platform != "__WXMSW__":  # on Windows not needed, but Linux and macOS need an update timer
            self.progress_timer = wx.Timer(self)
            self.Bind(wx.EVT_TIMER, self.on_progress_timer, self.progress_timer)

        self.cancel_search_button = wx.Button(self, wx.ID_ANY, _('Cancel'))
        self.cancel_search_button.Hide()
        self.find_all_button = wx.Button(self, wx.ID_ANY, _('Find All'))
        self.list_ctrl = wx.ListBox(self, style=wx.LB_SINGLE)

        no_top_border = wx.BOTTOM | wx.LEFT | wx.RIGHT
        no_bottom_border = wx.TOP | wx.LEFT | wx.RIGHT
        mainsizer = wx.BoxSizer(wx.VERTICAL)
        mainsizer.Add(find_what_label, flag=no_bottom_border, border=border)

        whatSizer = wx.BoxSizer(wx.HORIZONTAL)
        whatSizer.Add(self.find_what_ctrl, 1, flag=wx.EXPAND | wx.BOTTOM | wx.LEFT, border=border)
        whatSizer.Add(self.show_search_options_button, 0, flag=no_top_border, border=border)
        mainsizer.Add(whatSizer, 0, flag=wx.EXPAND)

        mainsizer.Add(searchfolder_label, flag=no_bottom_border, border=border)
        folderSizer = wx.BoxSizer(wx.HORIZONTAL)
        folderSizer.Add(self.searchfolder_ctrl, 1, flag=wx.EXPAND | wx.BOTTOM | wx.LEFT, border=border)
        folderSizer.Add(self.choose_search_folder_button, 0, flag=no_top_border, border=border)

        progressSizer = wx.BoxSizer(wx.HORIZONTAL)
        progressSizer.Add(self.progress, 1, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL | wx.RESERVE_SPACE_EVEN_IF_HIDDEN, border=border)
        progressSizer.Add(self.cancel_search_button, 0, flag=wx.ALL | wx.RESERVE_SPACE_EVEN_IF_HIDDEN, border=border)
        progressSizer.Add(self.find_all_button, 0, flag=wx.ALL | wx.RESERVE_SPACE_EVEN_IF_HIDDEN, border=border)

        self.when_selecting = wx.RadioBox(self, wx.ID_ANY, _('When selecting'), choices=[_('Open file'), _('Copy tune to editor')], majorDimension=1)
        when_selecting_sizer = wx.BoxSizer(wx.HORIZONTAL)
        when_selecting_sizer.Add(self.when_selecting, 1, flag=wx.ALL | wx.RESERVE_SPACE_EVEN_IF_HIDDEN, border=border)

        mainsizer.Add(folderSizer, 0, flag=wx.EXPAND)
        mainsizer.Add(progressSizer, 0, flag=wx.EXPAND)
        mainsizer.Add(self.list_ctrl, 1, flag=wx.EXPAND)
        mainsizer.Add(when_selecting_sizer, 0, flag=wx.EXPAND)

        self.SetSizer(mainsizer)
        self.Show()

        self.Bind(wx.EVT_BUTTON, self.On_browse_abcsearch, self.choose_search_folder_button)
        self.Bind(wx.EVT_BUTTON, self.on_popup_search_menu, self.show_search_options_button)
        self.Bind(wx.EVT_BUTTON, self.On_start_search, self.find_all_button)
        self.Bind(wx.EVT_BUTTON, self.On_start_search, self.find_all_button)
        self.Bind(wx.EVT_BUTTON, self.on_cancel_search, self.cancel_search_button)
        self.Bind(wx.EVT_TEXT_ENTER, self.On_start_search, self.find_what_ctrl)
        self.Bind(wx.EVT_TEXT_ENTER, self.On_start_search, self.searchfolder_ctrl)
        self.list_ctrl.Bind(wx.EVT_LISTBOX, self.OnItemSelected, self.list_ctrl)

        self.search_thread = None
        self.last_results = None
        self.results_start_index = 0

    def get_searchfields(self):
        return self.settings.get('searchfields', 'T:').split(';')

    def set_searchfields(self, value):
        self.settings['searchfields'] = ';'.join(value)

    def on_progress_timer(self, event):
        self.progress.Pulse()

    def on_popup_search_menu(self, event):
        self.PopupMenu(self.search_menu, event.EventObject.Position)

    def on_toggle_sort_search_results(self, event):
        menu = event.EventObject
        menu_item = menu.FindItemById(event.Id)
        self.settings['sort_search_results'] = menu_item.IsChecked()

    def on_toggle_option(self, event):
        menu = event.EventObject
        menu_item = menu.FindItemById(event.Id)
        include = menu_item.IsChecked()
        fields = menu_item.Help.split()
        searchfields = self.get_searchfields()
        for field in fields:
            if include:
                if not field in searchfields:
                    searchfields.append(field)
            else:
                if field in searchfields:
                    searchfields.remove(field)
        self.set_searchfields([f for f in searchfields if f])

    def focus_find_what(self):
        self.find_what_ctrl.SetFocus()

    def On_browse_abcsearch(self, evt):
        ''' Selects the folder to open for searching'''
        old_path = self.searchfolder_ctrl.GetValue()
        path = wx_dirdialog(self, _("Open"), old_path)
        if path:
            self.settings['searchfolder'] = path
            self.searchfolder_ctrl.SetValue(path)

    def On_start_search(self, evt):
        ''' Initializes dictionaries and calls find_abc_files'''
        root = self.searchfolder_ctrl.GetValue()
        if not root or not os.path.exists(root):
            wx_show_message(_('Invalid path'), _('Please enter a valid path to start looking for ABC-files.'))
        else:
            searchstring = self.find_what_ctrl.GetValue().strip()
            if searchstring and not searchstring in self.find_what_ctrl.Items:
                wx_insert_dropdown_value(self.find_what_ctrl, searchstring, max=5)
            self.find_all_button.Disable()
            self.list_ctrl.Show(False)
            self.list_ctrl.Clear()
            self.cancel_search_button.Enable()
            self.cancel_search_button.Show()
            self.progress.Pulse()
            self.progress.Show()
            if self.progress_timer:
                self.progress_timer.Start(200, wx.TIMER_CONTINUOUS)

            sort_results = self.settings.get('sort_search_results', True)
            if self.search_thread:
                self.search_thread.abort()
            self.search_thread = SearchFilesThread(root, searchstring, self.get_searchfields(), self.on_after_search, sort_results)

    def on_after_search(self, aborted, items):
        self.last_results = items
        self.results_start_index = 0
        if not aborted:
            self.statusbar.SetStatusText(_('Found {0} results').format(len(items)))
            self.show_next_results(self.results_start_index)

        self.find_all_button.Enable()
        self.cancel_search_button.Hide()
        if self.progress_timer:
            self.progress_timer.Stop()
        self.progress.Hide()
        self.progress.SetValue(0)

    def on_cancel_search(self, event):
        self.abort_search()

    def abort_search(self):
        self.cancel_search_button.Disable()
        self.search_thread.abort()

    @property
    def is_searching(self):
        return self.search_thread and self.search_thread.is_alive()

    def clear_results(self):
        self.find_what_ctrl.SetValue('')
        if self.is_searching:
            self.search_thread.abort()
        else:
            self.list_ctrl.Clear()


# 1.3.6 [SS] 2014-12-02
    def OnItemSelected(self, evt):
        ''' Responds to a selected title in the search listbox results. The abc file
        containing the selected tune is opened and the table of contents is updated.'''
        index = evt.Selection  # line number in listbox
        if self.max_results > 0 and index >= self.max_results:
            self.show_next_results(self.max_results + self.results_start_index)
        else:
            index += self.results_start_index
            path, char_pos_in_file = self.search_thread.get_result_for_index(index)

            wait = wx.BusyCursor()
            if self.when_selecting.GetSelection() == 0:
                # open file and select tune
                if self.mainwindow.CanClose():
                    abc_text = read_abc_file(path)[0:char_pos_in_file]
                    byte_pos_in_file = len(abc_text.encode('utf-8'))
                    self.mainwindow.load_and_position(path, byte_pos_in_file)
            else:
                # open in current editor
                wholefile = read_abc_file(path)
                tune_start = find_start_of_tune(wholefile, char_pos_in_file)
                tune_end = find_end_of_tune(wholefile, char_pos_in_file)
                editor = self.mainwindow.editor
                editor.BeginUndoAction()

                last_pos = editor.GetLength()
                editor.GotoPos(last_pos)
                editor.SetSelection(last_pos, last_pos)

                empty_line = os.linesep
                if last_pos > 0 and editor.GetTextRange(last_pos - 1, last_pos) != '\n':
                    empty_line += os.linesep

                editor.ReplaceSelection(empty_line + wholefile[tune_start:tune_end])

                editor.EndUndoAction()
            del wait

    def show_next_results(self, start_index):
        results = self.last_results
        items = results
        end_index = len(results)
        if self.max_results > 0:
            end_index = start_index + self.max_results
            items = results[start_index:end_index]

        titles = [title for title, path, pos in items]
        if end_index < len(results):
            next_count = min(len(results) - end_index, self.max_results)
            titles.append(u'[ ' + _('Next {0} results').format(next_count) + u' ]')

        self.results_start_index = start_index
        wait = wx.BusyCursor()
        self.list_ctrl.Hide()
        self.list_ctrl.Clear()
        if titles:
            self.list_ctrl.InsertItems(titles, 0)
        self.list_ctrl.Show()
        del wait
