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

import wx
import wx.stc as stc
from wx import GetTranslation as _

from abc_search import abc_matches_iter


class FindReplace(object):
    """Find and replace dialogs and the search operations they drive."""

    def __init__(self, frame):
        self.frame = frame
        self.find_data = wx.FindReplaceData()
        self.find_data.SetFlags(wx.FR_DOWN)
        self.find_dialog = None
        self.replace_dialog = None

    def OnFind(self, evt):
        self.close_existing_find_and_replace_dialogs()
        self.find_dialog = wx.FindReplaceDialog(self.frame, self.find_data, _("Find"))
        wx.CallLater(1, self.find_dialog.Show, True)

    def OnReplace(self, evt):
        self.close_existing_find_and_replace_dialogs()
        self.replace_dialog = wx.FindReplaceDialog(self.frame, self.find_data, _("Find & Replace"), wx.FR_REPLACEDIALOG)
        wx.CallLater(1, self.replace_dialog.Show, True)

    def close_existing_find_and_replace_dialogs(self):
        if self.find_dialog:
            self.find_dialog.Close()
            self.find_dialog.Destroy()
            self.find_dialog = None
        if self.replace_dialog:
            self.replace_dialog.Close()
            self.replace_dialog.Destroy()
            self.replace_dialog = None

    def OnFindClose(self, evt):
        evt.GetDialog().Destroy()

    def get_scintilla_find_flags(self):
        self.findFlags = self.find_data.GetFlags()
        flags = 0
        if wx.FR_WHOLEWORD & self.findFlags:
            flags |= stc.STC_FIND_WHOLEWORD
        if wx.FR_MATCHCASE & self.findFlags:
            flags |= stc.STC_FIND_MATCHCASE
        return flags

    def OnFindReplace(self, evt):
        editor = self.frame.editor
        editor.BeginUndoAction()
        editor.ReplaceSelection(self.find_data.GetReplaceString())
        editor.EndUndoAction()
        wx.CallAfter(self.OnFindNext, evt)

    def OnFindReplaceAll(self, evt):
        editor = self.frame.editor
        try:
            editor.BeginUndoAction()
            text = editor.GetText()
            pattern = re.escape(self.find_data.GetFindString())
            if self.find_data.GetFlags() & wx.FR_WHOLEWORD:
                pattern = r'\b' + pattern + r'\b'
            if not (self.find_data.GetFlags() & wx.FR_MATCHCASE):
                pattern = '(?i)' + pattern
            text, count = re.subn(pattern, self.find_data.GetReplaceString(), text)
            editor.SetText(text.replace(self.find_data.GetFindString(), self.find_data.GetReplaceString()))
            editor.SetSelection(0, 0)
            editor.GotoPos(0)
        finally:
            editor.EndUndoAction()
        if count:
            msg = _('%d occurrences successfully replaced.') % count
        else:
            msg = _('Cannot find "%s"') % self.find_data.GetFindString()
        dlg = wx.MessageDialog(self.frame, msg, _('Replace All'), wx.OK | wx.ICON_INFORMATION)
        dlg.ShowModal()
        dlg.Destroy()

    def OnFindNextABC(self):
        editor = self.frame.editor
        find_abc = self.find_data.GetFindString().replace(':', '', 1).strip()

        # change selection to be at the end of the current selection and extract the rest of the text from that point on
        p1, p2 = editor.GetSelection()
        editor.SetSelection(p2, p2)
        abc = editor.GetTextRange(p2, editor.GetLength())
        abc = abc.encode('utf-8')

        # find occurances of the ABC search string
        for (start_offset, end_offset) in abc_matches_iter(abc, find_abc):
            p1, p2 = start_offset+p2, end_offset+p2  # both offsets are relative to p2, since that's where the extracted text starts
            editor.SetSelection(p1, p2)
            editor.EnsureVisible(editor.LineFromPosition(p2))
            editor.EnsureVisible(editor.LineFromPosition(p1))
            break
        else:
            editor.SetSelection(p1, p2)
            dlg = wx.MessageDialog(self.frame, _('Cannot find "%s"') % self.find_data.GetFindString(), _('Find'), wx.OK | wx.ICON_INFORMATION)
            dlg.ShowModal()
            dlg.Destroy()
            (self.find_dialog or self.replace_dialog).Raise()

    def OnFindNext(self, evt):
        editor = self.frame.editor
        dialog = self.find_dialog or self.replace_dialog
        if dialog is None:
            return
        dialog.Raise()
        if self.find_data.GetFindString().startswith(':'):
            self.OnFindNextABC()
        else:
            p1, p2 = editor.GetSelection()
            if self.find_data.GetFlags() & wx.FR_DOWN:
                editor.SetSelection(p2, p2)
            else:
                editor.SetSelection(p1, p2)
            editor.SearchAnchor()
            if self.find_data.GetFlags() & wx.FR_DOWN:
                search_func = editor.SearchNext
            else:
                search_func = editor.SearchPrev
            pos = search_func(self.get_scintilla_find_flags(), self.find_data.GetFindString())
            if pos == -1:
                editor.SetSelection(p1, p2)
                dlg = wx.MessageDialog(self.frame, _('Cannot find "%s"') % self.find_data.GetFindString(), _('Find'), wx.OK | wx.ICON_INFORMATION)
                dlg.ShowModal()
                (self.find_dialog or self.replace_dialog).Raise()
            else:
                p1, p2 = pos, pos+len(self.find_data.GetFindString())
                editor.SetSelection(p1, p2)
                editor.EnsureVisible(editor.LineFromPosition(p2))
                editor.EnsureVisible(editor.LineFromPosition(p1))
                # 1.3.6.1 [JWdJ] 2014-01-30 Cursor not lost after find-next
                editor.EnsureCaretVisible()
