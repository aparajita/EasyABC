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

# # for finding memory leaks uncomment following two lines
# import gc
# gc.set_debug(gc.DEBUG_LEAK)
#
# # for finding segmentation fault or bus error (pip install faulthandler)
# try:
#     import faulthandler  # pip install faulthandler
#     faulthandler.enable()
# except ImportError:
#     sys.stderr.write('faulthandler not installed. Try: pip install faulthandler\n')
#     pass

import sys

import os, os.path
import wx

from utils import *

import subprocess
import hashlib

import pickle

import shutil
import webbrowser
import time
import traceback
# import xml.etree.cElementTree as ET  # 1.3.7.4 [JWdJ] 2016-06-30
from datetime import datetime
from collections import deque
from wx.lib.scrolledpanel import ScrolledPanel
import wx.html
import wx.stc as stc
import wx.lib.agw.aui as aui
# import wx.lib.filebrowsebutton as filebrowse # 1.3.6.3 [JWdJ] 2015-04-22
import wx.lib.platebtn as platebtn
from wx.lib.embeddedimage import PyEmbeddedImage
# from wx.lib.expando import ExpandoTextCtrl, EVT_ETC_LAYOUT_NEEDED # 1.3.7.3 [JWdJ] 2016-04-09
from wx import GetTranslation as _
from wxhelper import *

from abc_styler import ABCStyler
from error_marks import ErrorMarks
from music_score_panel import MusicScorePanel
from svgrenderer import SvgRenderer
from tune_document import TuneDocument, TuneList
from score_view import ScoreView, DEFAULT_ZOOM
from playback_controller import PlaybackController
from typing_assistant import TypingAssistant
from find_replace import FindReplace
import printing
from settings_dialogs import MyNoteBook, MidiSettingsFrame
from search_panel import FlexibleListCtrl, AbcSearchPanel
from background_threads import EVT_MUSIC_UPDATE_DONE
from abc_tools import show_in_browser, get_default_path_for_executable, find_ps_to_pdf_converter, MidiToMftext
from dialogs import FieldReferenceTree, MyInfoFrame, \
    MyAbcFrame, MyTunesListFrame, AboutFrame, MyFileDropTarget
from app_state import app_state
from constants import program_version, program_name, WX4, application_path, cwd, default_midi_volume, default_midi_pan, default_midi_instrument
from exporter import Exporter
import menu_builder
if sys.version_info >= (3,0,0):
    from queue import Queue # 1.3.6.2 [JWdJ] 2015-02
else:
    from Queue import Queue # 1.3.6.2 [JWdJ] 2015-02

if wx.Platform == "__WXMSW__":
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w')
    if sys.stderr is None:
        sys.stderr = open(os.devnull, 'w')
    import win32api
    import win32process

from appearance import current_appearance, rebuild_appearance
from appearance import DEFAULT_NOTE_HIGHLIGHT as default_note_highlight_color
from appearance import DEFAULT_NOTE_HIGHLIGHT_FOLLOW as default_note_highlight_follow_color


# 1.3.6.3 [JWdJ] 2015-04-22

# 1.3.6.2 [JWdJ]


# 1.3.6.3 [JWdJ] 2015-04-22




# 1.3.6.3 [JWDJ] one function to determine font size


# p09 2014-10-14 [SS]


# 1.3.6 [SS] 2014-12-17

# 1.3.6 [SS] 2014-12-02 2014-12-07

# 1.3.6.3 [JWDJ] 2015-04-21 splitted AbcToSvg up into 2 functions (abc_to_svg does not do preprocessing)


# 1.3.6.4 [SS] 2015-06-22

# p09 2014-10-14 2014-12-17 2015-01-28 [SS]

# 1.3.6.4 [SS] 2015-07-10


# 1.3.6.4 [SS] 2015-07-03


# 1.3.6.4 [SS] 2015-07-03


# 1.3.6.4 [SS] 2015-07-03


#1.3.6.4 [SS] 2015-07-05


# 1.3.6.4 [SS] 2015-07-03


# 1.3.6  [SS] simplified the calling sequence 2014-11-15

# 1.3.6.3 [JWDJ] 2015-04-21 split up AbcToMidi into 2 functions: preprocessing (process_abc_for_midi) and actual midi generation (abc_to_midi)


# 1.3.6.3 [JWDJ] 2015-04-21 split up AbcToMidi into 2 functions: preprocessing (process_abc_for_midi) and actual midi generation (abc_to_midi)

# 1.3.6 [SS] 2014-11-24


# 1.3.6 [SS] 2014-11-24


# 1.3.6 [SS] 2014-12-07 statusbar added
# 1.3.6.2 [SS] 2015-03-02 statusbar removed


# p09 new class for playing midi files if self.mc is not working 2014-10-14
# 1.3.6.3 [JWdJ] midithread extended so it works the same as the svg-thread


#p09 Abcm2psSettingsFrame dialog box has been replaced with a
#tabbed notebook so we have lots of room for adding more options.
#2014-10-14


# p09 this was derived from the Abcm2psSettingsFrame. Now it is a separate page in the
# wx.notebook. 2014-10-14 [SS]


# New panel to be able to set MIDI settings for the different voices


# 1.3.6 [SS] 2014-12-04 2014-12-16
# For controlling the way abcm2ps runs


# 1.3.6 [SS] 2014-12-01
# For controlling the way xml2abc and abc2xml operate


class PaneManager(aui.AuiManager):
    """An AUI manager that lets the system colour event reach the managed frame.

    The manager sits in the frame's event handler chain ahead of the frame, and
    the library handler swallows the event, so the frame's own handler would
    otherwise never run on an appearance switch.
    """

    def OnSysColourChanged(self, event):
        super().OnSysColourChanged(event)
        event.Skip()


class MainFrame(wx.Frame):
    def __init__(self, parent, ID, app_dir, settings, options):
        wx.Frame.__init__(self, parent, ID, '%s - %s %s' % (program_name, _('Untitled'), 1),
                         wx.DefaultPosition, wx.Size(900, 850))
        #_icon = wx.EmptyIcon()
        #_icon.CopyFromBitmap(wx.Bitmap(os.path.join('img', 'logo.ico'), wx.BITMAP_TYPE_ICO))
        #self.SetIcon(_icon)
        if wx.Platform == "__WXMSW__":
            exeName = win32api.GetModuleFileName(win32api.GetModuleHandle(None))
            # 1.3.8.1 [mist13] Icon for Python version in Windows
            if "easy_abc" in exeName:
                icon = wx.Icon(exeName + ";0", wx.BITMAP_TYPE_ICO)
            else:
                icon = wx.Icon(os.path.join(application_path, 'img', 'logo.ico'))
            self.SetIcon(icon)
        self.settings = settings
        self.exporter = Exporter(self)
        self.document = TuneDocument(self)
        self.tune_list_controller = TuneList(self)
        self.score_view = ScoreView(self)
        self.typing_assistant = TypingAssistant(self)
        self.find_replace = FindReplace(self)
        self.__current_page_index = 0 # 1.3.6.2 [JWdJ] 2015-02
        self.is_closed = False
        self.app_dir = app_dir
        self.cache_dir = os.path.join(self.app_dir, 'cache')
        self.settings_file = os.path.join(self.app_dir, 'settings1.3.dat')
        self.exclusive_file_mode = options.get('exclusive', False)
        self.last_refresh_time = datetime.now()
        self.field_reference_frame = None
        self.settingsbook = None
        self.execmessage_time = datetime.now() # 1.3.6 [SS] 2014-12-11
        self.is_fullscreen = False

        self.load_settings()
        settings = self.settings
        # the media player is chosen by the loaded 'soundfont_path', so playback is constructed once the settings file is read
        self.playback = PlaybackController(self)

        # 1.3.6 [SS] 2014-12-07
        self.statusbar = self.CreateStatusBar()
        self.SetMinSize((100, 100))
        if settings.get('live_resize', False):
            self.manager = PaneManager(self, agwFlags=aui.AUI_MGR_DEFAULT | aui.AUI_MGR_LIVE_RESIZE)
        else:
            self.manager = PaneManager(self)

        menu_builder.setup_menus(self)
        menu_builder.setup_toolbar(self)

        # 1.3.7.3 [JWDJ] Removed wx.LC_SINGLE_SEL to enable multiselect tunes
        self.tune_list = FlexibleListCtrl(self, wx.ID_ANY, style=wx.LC_REPORT) #wx.LC_NO_HEADER)

        self.tune_list.InsertColumn(0, _('No.'), wx.LIST_FORMAT_RIGHT)
        self.tune_list.InsertColumn(1, _('Title'))

        self.tune_list.SetAutoLayout(True)
        self.editor = stc.StyledTextCtrl(self, -1)
        self.error_marks = ErrorMarks(self.editor)
        self.editor.SetCodePage(stc.STC_CP_UTF8)

        self.document.new_tune()

        # p09 include line numbering in the edit window. 2014-10-14 [SS]
        self.editor.SetMarginLeft(15)
        self.editor.SetMarginWidth(1,50)
        self.editor.SetMarginType(1,stc.STC_MARGIN_NUMBER)

        # 1.3.6.2 [JWdJ] 2015-02
        self.renderer = SvgRenderer(self.settings['can_draw_sharps_and_flats'], self.settings.get('note_highlight_color', default_note_highlight_color), self.settings.get('note_highlight_follow_color', default_note_highlight_follow_color), self.score_paper_color())
        self.music_pane = MusicScorePanel(self, self.renderer)
        self.music_pane.SetBackgroundColour(wx.Colour(self.renderer.paper_color))
        self.music_pane.OnNoteSelectionChangedDesc = self.score_view.OnNoteSelectionChangedDesc

        error_font_size = get_normal_fontsize() # 1.3.6.3 [JWDJ] one function to set font size
        self.error_msg = wx.TextCtrl(self, wx.ID_ANY, '', size=(200, 100), style=wx.TE_MULTILINE | wx.TE_PROCESS_ENTER | wx.TE_READONLY | wx.TE_DONTWRAP)
        self.error_msg.SetFont(wx.Font(error_font_size, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, "Courier New"))
        self.error_pane = aui.AuiPaneInfo().Name("error message").Caption(_("ABC errors")).CloseButton(True).BestSize((160, 80)).Bottom()
        self.error_pane.Hide()
        self.error_msg.Hide() # 1.3.7 [JWdJ] 2016-01-06

        # 1.3.6.3 [JWdJ] 2015-04-21 ABC Assist added
        from abc_assist_panel import AbcAssistPanel  # 1.3.7.1 [JWDJ] 2016-1 because of translation this import has to be done as late as possible
        self.abc_assist_panel = AbcAssistPanel(self, self.editor, cwd, self.settings)
        self.assist_pane = aui.AuiPaneInfo().Name("abcassist").CaptionVisible(True).Caption(_("ABC assist")).\
            CloseButton(True).MinimizeButton(False).MaximizeButton(False).\
            Left().Layer(1).Position(1).BestSize(300, 600) # .PaneBorder(False) # Fixed()

        tune_list_pane = aui.AuiPaneInfo().Name("tune list").Caption(_("Tune list")).MinimizeButton(True).CloseButton(False).BestSize((265, 80)).Left().Row(0).Layer(1)
        editor_pane = aui.AuiPaneInfo().Name("abc editor").Caption(_("ABC code")).CloseButton(False).MinSize(40, 40).MaximizeButton(True).CaptionVisible(True).Center()
        music_pane_info = aui.AuiPaneInfo().Name("tune preview").Caption(_("Musical score")).MaximizeButton(True).MinimizeButton(True).CloseButton(False).BestSize((200, 280)).Right().Top()
        for pane_info in [tune_list_pane, editor_pane, music_pane_info, self.error_pane, self.assist_pane]:
            pane_info.Floatable(False).Dockable(False).Snappable(False).NotebookDockable(False)

        # do layout
        self.manager.AddPane(self.music_pane, music_pane_info)
        self.manager.AddPane(self.tune_list, tune_list_pane)
        self.manager.AddPane(self.editor, editor_pane)
        #self.manager.AddPane(self.error_msg, self.error_pane)
        self.manager.AddPane(self.abc_assist_panel, self.assist_pane)
        self.manager.Bind(aui.EVT_AUI_PANE_CLOSE, self.__onPaneClose)
        self.manager.Bind(aui.EVT_AUI_PANE_MAXIMIZE, self.__onPaneMaximize)
        self.manager.Bind(aui.EVT_AUI_PANE_RESTORE, self.__onPaneRestore)

        self.manager.Update()

        self.search_files_panel = None
        self.default_perspective = self.manager.SavePerspective()

        self.styler = ABCStyler(self.editor)
        self.InitEditorFromSettings()

        self.editor.SetDropTarget(MyFileDropTarget(self))
        self.tune_list.SetDropTarget(MyFileDropTarget(self))
        self.music_pane.SetDropTarget(MyFileDropTarget(self))
        self.abc_assist_panel.SetDropTarget(MyFileDropTarget(self))
        if wx.Platform == "__WXMSW__":
            self.GetMenuBar().SetDropTarget(MyFileDropTarget(self))

        self.tune_list_last_width = self.tune_list.GetSize().width

        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.OnTimer, self.timer)
        self.timer.Start(2000, wx.TIMER_CONTINUOUS)

        self.tune_list.Bind(wx.EVT_LIST_ITEM_SELECTED, self.tune_list_controller.OnTuneSelected)
        self.tune_list.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.tune_list_controller.OnTuneDeselected)
        self.tune_list.Bind(wx.EVT_LEFT_DCLICK, self.tune_list_controller.OnTuneDoubleClicked)
        self.tune_list.Bind(wx.EVT_LEFT_DOWN, self.tune_list_controller.OnTuneListClick)
        self.editor.Bind(stc.EVT_STC_STYLENEEDED, self.styler.OnStyleNeeded)
        self.editor.Bind(stc.EVT_STC_CHANGE, self.OnChangeText)
        self.editor.Bind(stc.EVT_STC_MODIFIED, self.OnModified)
        self.editor.Bind(stc.EVT_STC_UPDATEUI, self.score_view.OnPosChanged)
        self.editor.Bind(wx.EVT_LEFT_UP, self.score_view.OnEditorMouseRelease)
        self.editor.Bind(wx.EVT_KEY_DOWN, self.typing_assistant.OnKeyDownEvent)
        self.editor.Bind(wx.EVT_CHAR, self.typing_assistant.OnCharEvent)
        self.editor.CmdKeyAssign(ord('+'), stc.STC_SCMOD_CTRL, stc.STC_CMD_ZOOMIN)
        self.editor.CmdKeyAssign(ord('-'), stc.STC_SCMOD_CTRL, stc.STC_CMD_ZOOMOUT)
        self.music_pane.Bind(wx.EVT_LEFT_DCLICK, self.score_view.OnMusicPaneDoubleClick)
        self.music_pane.Bind(wx.EVT_LEFT_DOWN, self.score_view.OnMusicPaneClick)
        self.music_pane.Bind(wx.EVT_RIGHT_DOWN, self.score_view.OnRightClickMusicPane)
        # self.music_pane.Bind(wx.EVT_KEY_DOWN, self.score_view.OnMusicPaneKeyDown)

        self.load_and_apply_settings(load_window_size_pos=True)
        self.restore_settings()

        self.update_controls_using_settings()

        self.score_view.start_music_update_thread()

        self.tune_list.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, self.OnRightClickList, self.tune_list)

        self.Bind(wx.EVT_CLOSE, self.OnClose)
        self.Bind(wx.EVT_SYS_COLOUR_CHANGED, self.OnSysColourChanged)
        self.Bind(EVT_MUSIC_UPDATE_DONE, self.score_view.OnMusicUpdateDone)
        self.editor.Bind(wx.EVT_KEY_DOWN, self.OnUpdate)
        self.music_pane.Bind(wx.EVT_KEY_DOWN, self.OnUpdate)
        self.tune_list.Bind(wx.EVT_KEY_DOWN, self.OnUpdate)
        self.music_pane.Bind(wx.EVT_MOUSEWHEEL, self.score_view.OnMusicPaneMouseWheel)
        if self.music_pane.EnableTouchEvents(wx.TOUCH_ZOOM_GESTURE):
            self.music_pane.Bind(wx.EVT_GESTURE_ZOOM, self.score_view.OnMusicPaneZoomGesture)

        self.tune_list_controller.UpdateTuneList()
        self.tune_list_controller.update_multi_tunes_menu_items()

        self.editor.SetFocus()
        wx.CallLater(100, self.editor.SetFocus)
        menu_builder.GrayUngray(self)

        self.OnClearCache(None) # P09 2014-10-26

        self.manager.GetPane(self.music_pane).Dockable(True) # 1.3.7.6 score pane movable
        # 1.3.7 [JWdJ] 2016-01-06
        self.ShowAbcAssist(self.settings.get('show_abc_assist', True))

        # 1.3.6.3 [SS] 2015-05-04
        self.statusbar.SetStatusText(_('This is the status bar. Check it occasionally.'))
        app_state.messages = _('You are running {0} on {1}').format(program_name, wx.Platform)
        app_state.messages += '\n' + _('You can get the latest version on') + ' https://sourceforge.net/projects/easyabc/'

    def update_controls_using_settings(self):
        # p09 Enable the play button if midiplayer_path is defined. 2014-10-14 [SS]
        self.playback.update_play_button() # 1.3.6.3 [JWdJ] 2015-04-21 centralized playbutton enabling

        self.follow_score_check.SetValue(self.settings.get('follow_score', False))
        self.timing_slider.SetValue(self.settings.get('follow_score_timing_offset', 0))
        self.playback.UpdateTimingSliderVisibility()

    def Destroy(self):
        self.renderer.destroy()
        self.renderer = None
        super(MainFrame, self).Destroy()

    # 1.3.6.2 [JWdJ] 2015-02
    @property
    def current_page_index(self):
        return self.__current_page_index

    # 1.3.6.2 [JWdJ] 2015-02
    @current_page_index.setter
    def current_page_index(self, value):
        if self.__current_page_index != value:
            self.score_view.selected_note_indices = [] # 1.3.6.4 [JWDJ] 2015-07-11 having notes selected and switching to a different page resulted in (almost) nothing being played
            self.score_view.selected_note_descs = []

        self.__current_page_index = value
        if self.cur_page_combo.GetSelection() != value:
            if self.cur_page_combo.GetCount() > 0:  #[EPO] 2018-11-27 crashes in next statement if list empty
                self.cur_page_combo.Select(value)

    def OnResetView(self, evt):
        self.manager.LoadPerspective(self.default_perspective)
        self.manager.Update()
        if 'tune_col_widths' in self.settings:
            del self.settings['tune_col_widths']
        self.OnSettingsChanged()

    def OnSettingsChanged(self):
        self.save_settings()
        for frame in wx.GetApp().GetAllFrames():
            frame.load_and_apply_settings()

    def OnSysColourChanged(self, evt):
        evt.Skip()
        rebuild_appearance()
        self.ApplyAppearance()

    def ApplyAppearance(self):
        """Repaint everything that draws with appearance colours.

        Runs on a live appearance switch, after the appearance has been rebuilt,
        so the editor palette and score pane can follow the system.
        """
        self.InitEditorFromSettings()
        self.ApplyScorePaper()
        tune_frame = wx.FindWindowByName('abctuneframe')
        if tune_frame is not None:
            tune_frame.ApplyAppearance()

    def score_paper_color(self):
        return current_appearance().style_color(self.settings, 'score_paper')

    def ApplyScorePaper(self):
        """Repaint the score pane on the paper colour of the current appearance."""
        self.renderer.paper_color = self.score_paper_color()
        self.music_pane.SetBackgroundColour(wx.Colour(self.renderer.paper_color))
        self.music_pane.redraw()
        self.Refresh()

    # 1.3.6 [SS] 2014-11-21
    def OnSearchDirectories(self, evt):
        self.show_search_in_files(True)

    def show_search_in_files(self, show):
        panel = self.search_files_panel
        if not panel:
            panel = AbcSearchPanel(self, self.settings, self.statusbar)
            self.search_files_panel = panel

        pane = self.manager.GetPane(self.search_files_panel)
        if not pane.IsOk():
            pane = aui.AuiPaneInfo().Name("search files").Caption(_("Find in Files")).MaximizeButton(False).MinimizeButton(False).CloseButton(True).BestSize((300, 600)).Right().Layer(1)
            self.manager.AddPane(self.search_files_panel, pane)
            self.manager.Update()

        if show:
            self.manager.RestorePane(pane)
            self.manager.Update()
        else:
            if self.abc_assist_panel.IsShown():
                self.abc_assist_panel.Hide()
            if pane.IsOk():
                self.manager.DetachPane(self.abc_assist_panel)
        self.manager.Update()


    def toggle_fullscreen(self, evt):
        self.is_fullscreen = not self.is_fullscreen
        self.ShowFullScreen(self.is_fullscreen, style=wx.FULLSCREEN_ALL)

    def OnRightClickList(self, evt):
        self.tune_list_controller.selected_tune = self.tune_list_controller.tunes[evt.Index]
        self.tune_list.PopupMenu(self.popup_upload, evt.GetPoint())

    # 1.3.6.3 [JWDJ] 2015-3 centralized enabling of play button
    def OnToolAbcAssist(self, evt):
        # 1.3.7 [JWdJ] 2016-01-06
        pane = self.manager.GetPane(self.abc_assist_panel)
        shown = self.abc_assist_panel.IsShown() and pane.IsOk()
        if shown:
            if pane.IsFloating():
                pane.Dock()
            else:
                pane.Float()

            self.manager.Update()
            pane.Floatable(False) # JWDJ: moving a docked abc-assist must not let it float
            pane.Dockable(not pane.IsFloating()) # JWDJ: moving a floating abc-assist must not try to dock it again
        else:
            self.ShowAbcAssist(not shown)
        self.editor.SetFocus()

    # 1.3.7 [JWdJ] 2016-01-06
    def ShowAbcAssist(self, show):
        pane = self.manager.GetPane(self.abc_assist_panel)
        if show:
            if not pane.IsOk():
                self.manager.AddPane(self.abc_assist_panel, self.assist_pane)
                self.manager.Update()
                pane = self.manager.GetPane(self.abc_assist_panel)

            if pane.IsOk():
                self.manager.RestorePane(pane)
                self.manager.Update()

            if not self.abc_assist_panel.IsShown():
                self.abc_assist_panel.Show()
            self.manager.Update()

            self.abc_assist_panel.update_assist()
            if pane.IsFloating():
                # 1.3.6.2 [JWDJ] move abc assist alongside abc editor
                w, h = self.abc_assist_panel.GetClientSize()
                w += 2 # include border pixels
                editor_x, editor_y = self.editor.ClientToScreen((0, 0))
                new_size = self.tune_list.GetSize()[0], self.editor.GetSize()[1]
                pane.FloatingSize(new_size)
                pane.FloatingPosition((editor_x, editor_y))
                pane.Show()
                self.manager.Update()
                assist_x, assist_y = self.abc_assist_panel.ClientToScreen((0, 0))
                offset = editor_x - assist_x, editor_y - assist_y
                pane.FloatingPosition((editor_x + offset[0] - w, editor_y + offset[1]))
                self.manager.Update()
            # 1.3.7 [JWdJ] 2016-01-06
            pane.Dockable(not pane.IsFloating()) # JWDJ: moving a floating abc-assist must not try to dock it again
        else:
            if self.abc_assist_panel.IsShown():
                self.abc_assist_panel.Hide()
            if pane.IsOk():
                self.manager.DetachPane(self.abc_assist_panel)

        self.manager.Update()
        self.UpdateAbcAssistSetting()

    def UpdateAbcAssistSetting(self):
        pane = self.manager.GetPane(self.abc_assist_panel)
        show_abc_assist = pane.IsOk() and pane.IsShown() and self.abc_assist_panel.IsShown()
        self.settings['show_abc_assist'] = show_abc_assist

    def __onPaneClose(self, evt):
        if evt.pane.window == self.abc_assist_panel:
            self.settings['show_abc_assist'] = False
        if evt.pane.window == self.search_files_panel:
            self.search_files_panel.focus_find_what()
            self.search_files_panel.clear_results()

    def __onPaneMaximize(self, evt):
        if evt.pane.window == self.music_pane:
            self.score_view.score_is_maximized = True

    def __onPaneRestore(self, evt):
        if evt.pane.window == self.music_pane:
            self.score_view.score_is_maximized = False

    def OnToolDynamics(self, evt):
       try: self.toolbar.PopupMenu(self.popup_dynamics)
       except wx._core.PyAssertionError: pass

    def OnToolOrnamentation(self, evt):
       try: self.toolbar.PopupMenu(self.popup_ornaments)
       except wx._core.PyAssertionError: pass

    def OnToolDirections(self, evt):
       try: self.toolbar.PopupMenu(self.popup_directions)
       except wx._core.PyAssertionError: pass

    @staticmethod
    def get_image_path():
        return os.path.join(application_path, 'img')

    def ShowMessages(self):
        win = wx.FindWindowByName('infoframe')
        if win is None:
            self.msg = MyInfoFrame()
            self.msg.ShowText(app_state.messages)
            self.msg.Show()
        else:
            win.ShowText(app_state.messages)
            # 1.3.6.1 [JWdJ] 2015-01-30 When messages window is lost it will be focused again
            win.Iconize(False)
            win.Raise()

    def OnShowMessages(self, evt):
        self.ShowMessages()

    def OnShowAbcTune(self, evt):
        win = wx.FindWindowByName('abctuneframe')
        if win is None:
            # 1.3.6.3 [JWDJ] 2015-04-27 instance of MyInfoFrame was overwritten by mistake
            self.tune_frame = MyAbcFrame()
            self.tune_frame.ShowText(app_state.visible_abc_code)
            self.tune_frame.Show()
        else:
            win.ShowText(app_state.visible_abc_code)
            # 1.3.6.1 [SS] 2015-02-01
            win.Iconize(False)
            win.Raise()

    def OnShowTunesList(self, evt):
        win = wx.FindWindowByName('tuneslistframe')
        tunes_list = 'index|title|startline\n'
        for i, (index, title, startline) in enumerate(self.tune_list_controller.tunes):
            tunes_list = tunes_list + str(index) + '|' + str(title) + '|' + str(startline) +'\n'
        if win is None:
            self.tuneslist_frame = MyTunesListFrame()
            self.tuneslist_frame.ShowText(tunes_list)
            self.tuneslist_frame.Show()
        else:
            win.ShowText(tunes_list)
            win.Iconize(False)
            win.Raise()

    # 1.3.6 [SS] 2014-12-10
    def OnShowSettings(self, evt):
        app_state.messages = u''
        for key in sorted(self.settings):
            line = key +' => '+ str(self.settings[key]) + '\n'
            app_state.messages += line
        # 1.3.6.1 [JWdJ] 2015-01-30 When messages window is lost it will be focused again
        self.ShowMessages()

    #1.3.6.4 [SS] 2015-06-22
    def OnShowMidiFile(self, evt):
        midi2abc_path = self.settings['midi2abc_path']
        current_midi_tune = self.playback.current_midi_tune
        if hasattr(current_midi_tune, 'midi_file'):
            MidiToMftext(midi2abc_path, current_midi_tune.midi_file)
        else:
            wx.MessageBox(_("You need to create the midi file by playing the tune"), _("Error") , wx.ICON_ERROR | wx.OK)

    def OnQuit(self, evt):
        for frame in wx.GetApp().GetAllFrames():
            if not frame.Close():
                break

    def do_command(self, cmd):
        self.editor.CmdKeyExecute(cmd)

    def OnUndo(self, evt):      #self.do_command(stc.STC_CMD_UNDO)
        if self.tune_list.HasFocus():
            return
        widget = self.FindFocus()
        widget.Undo()
    def OnRedo(self, evt):      #self.do_command(stc.STC_CMD_REDO)
        if self.tune_list.HasFocus():
            return
        widget = self.FindFocus()
        widget.Redo()
    def OnCut(self, evt):       #self.do_command(stc.STC_CMD_CUT)
        if self.tune_list.HasFocus():
            return
        widget = self.FindFocus()
        widget.Cut()
    def OnCopy(self, evt):      #self.do_command(stc.STC_CMD_COPY)
        if self.tune_list.HasFocus():
            self.exporter.OnExportToClipboard(evt)
        else:
            widget = self.FindFocus()
            widget.Copy()
    def OnPaste(self, evt):    #self.do_command(stc.STC_CMD_PASTE)
        if self.tune_list.HasFocus():
            return
        widget = self.FindFocus()
        widget.Paste()
    def OnDelete(self, evt):    #self.do_command(stc.STC_CMD_CLEAR)
        if self.tune_list.HasFocus():
            return
        widget = self.FindFocus()
        widget.Clear()
    def OnSelectAll(self, evt): #self.do_command(stc.STC_CMD_SELECTALL)
        if self.tune_list.HasFocus():
            for i in range(self.tune_list.GetItemCount()):
                self.tune_list.Select(i,1)
        else:
            widget = self.FindFocus()
            widget.SelectAll()

    def OnAbout(self, evt):
        dlg = AboutFrame(self)
        dlg.ShowModal()
        dlg.Destroy()

    def OnCheckLastestVersion(self, evt):
        show_in_browser('https://sourceforge.net/projects/easyabc/files/EasyABC/')

    def OnEasyABCHelp(self, evt):
        #FAU:HELP:the original page of EasyABC from Nils Libeg is not available anymore, so point to sourceforge guide
        #show_in_browser('https://www.nilsliberg.se/ksp/easyabc/')
        show_in_browser('https://easyabc.sourceforge.net')

    def OnABCStandard(self, evt):
        show_in_browser('https://abcnotation.com/wiki/abc:standard:v2.1')

    def OnABCLearn(self, evt):
        show_in_browser('https://abcnotation.com/learn')

    # 1.3.6.1 [SS] 2015-01-28
    def OnAbcm2psHelp(self, evt):
        show_in_browser('http://moinejf.free.fr/abcm2ps-doc/')

    # 1.3.6.1 [SS] 2015-01-28
    def OnAbc2midiHelp(self, evt):
        show_in_browser('https://abcmidi.sourceforge.io/')

    def OnAbcCheatSheet(self, evt):
        #FAU:HELP:The original ABC Quick Ref is not available changing to a github repository
        #show_in_browser('http://www.stephenmerrony.co.uk/uploads/ABCquickRefv0_6.pdf')
        show_in_browser('https://sourceforge.net/projects/easyabc/files/Documentation/ABCquickRefv0_6.pdf/download')

    def OnClearCache(self, evt):
        # make sure that any currently played/loaded midi file is released by the media control
        #patch from Seymour: ensure that the media player exists with the statement
        self.playback.stop_playing()

        dir_name = os.path.join(self.app_dir, 'cache')
        # 1.3.6 [SS] 2014-11-16
        files = [os.path.join(dir_name, f) for f in os.listdir(dir_name) if f.startswith('temp') and f[-3:] in ('png', 'svg', 'abc', 'mid', 'idi', 'pdf')]

        if evt is None: #PO9 2014-10-26
            result = wx.OK # remove cache silently
        else:
            total_size = sum(os.path.getsize(f) for f in files)
            mb = float(total_size) / (1024**2)
            result = wx.MessageBox(_("This will remove %(count)s temporary files stored in the directory %(dir)s that in total use %(size).2f MB of your disk space. Proceed?") % {'count': len(files), 'dir': dir_name, 'size': mb},
                               _("Clear cache?"), wx.ICON_QUESTION | wx.OK | wx.CANCEL)
        if result == wx.OK:
            for f in files:
                try:
                    os.remove(f)
                except:
                    pass
            self.score_view.svg_tunes.cleanup()
            self.playback.midi_tunes.cleanup()

    # 1.3.6.1 [SS] 2014-12-28 2015-01-22
    def OnColdRestart(self, evt):
        result = wx.MessageBox(_("This will close EasyAbc and put it in a state so that it starts with default settings."
        "i.e. the file settings1.3 will be deleted."),
                               _("Proceed?"), wx.ICON_QUESTION | wx.OK | wx.CANCEL)
        if result == wx.OK:
            f = os.path.join(self.app_dir, 'settings1.3.dat')
            os.remove(f)
            self.score_view.music_update_thread.abort()
            self.is_closed = True
            self.manager.UnInit()
            self.Destroy()

    def OnMidiSettings(self, evt):
        dlg = MidiSettingsFrame(self, self.settings)
        try:
            modal_result = dlg.ShowModal()
        finally:
            dlg.Destroy() # 1.3.6.3 [JWDJ] 2015-04-21 always clean up dialog window

    #p09 revised to use MyNoteBook
    def OnAbcSettings(self, evt):
        # 1.3.6.4 [SS] 2015-07-07
        win = wx.FindWindowByName('settingsbook')
        if win is None or not self.settingsbook:
            self.settingsbook = MyNoteBook(self, self.settings, self.statusbar)
            self.settingsbook.Show()
        else:
            win.Iconize(False)
            win.Raise()

    def OnChangeFont(self, evt):
        font = wx.GetFontFromUser(self, self.editor.GetFont(), _('Select a font for the ABC editor'))
        if font and font.IsOk():
            f = font
            self.settings['font'] = (f.GetPointSize(), f.GetFamily(), f.GetStyle(), f.GetWeight(), f.GetUnderlined(), f.GetFaceName())
            self.InitEditor(f.GetFaceName(), f.GetPointSize())

    def OnViewFieldReference(self, evt):
        if not self.field_reference_frame:
            self.field_reference_frame = frame = wx.Frame(self, wx.ID_ANY, _('ABC fields and commands reference'), wx.DefaultPosition, (700, 500),
                                                          style=wx.RESIZE_BORDER | wx.CLOSE_BOX | wx.FRAME_TOOL_WINDOW | wx.CAPTION | wx.FRAME_FLOAT_ON_PARENT | wx.SYSTEM_MENU  )
            tree = FieldReferenceTree(frame, -1)
            sizer = wx.GridSizer(1, 1, 0, 0)
            sizer.Add(tree, flag=wx.EXPAND)
            #frame.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
            #tree.SetFont(frame.GetFont())
            frame.CreateStatusBar()
            frame.SetSizer(sizer)
            frame.SetAutoLayout(True)
            frame.Centre()
            frame.tree = tree
            frame.tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.OnFieldReferenceItemDClick)
        self.field_reference_frame.Show(True)

    def OnFieldReferenceItemDClick(self, event):
        item = event.GetItem()
        if item and item.GetChildrenCount() == 0:
            cmd, desc = self.field_reference_frame.tree.GetItemText(item, 0), self.field_reference_frame.tree.GetItemText(item, 1)
            # 1.3.6.3 [JWdJ] 2015-02 bugfix: always insert at beginning of next line if current line is not empty
            current_line = self.editor.GetCurrentLine()
            text = cmd.ljust(30) + '% ' + desc
            line_start = self.editor.PositionFromLine(current_line)
            line_end = self.editor.GetLineEndPosition(current_line)
            if line_start != line_end:
                text = os.linesep + text
            self.editor.SetSelection(line_end, line_end)
            self.typing_assistant.replace_selection(text)
        else:
            event.Skip()

    def OnUseDefaultFont(self, evt):
        if 'font' in self.settings:
            del self.settings['font']
            self.save_settings()
            for frame in wx.GetApp().GetAllFrames():
                frame.load_and_apply_settings()
                frame.InitEditor()

    def OnActualFontSize(self, evt):
        self.editor.SetZoom(0)

    def OnModified(self, evt):
        if self.document.updating_text:
            return
        if evt.GetLinesAdded() != 0:
            wx.CallAfter(self.tune_list_controller.UpdateTuneListAndReselectTune)

    def AutomaticUpdate(self, update_number):
        if self.score_view.queue_number_refresh_music == update_number:
            self.score_view.refresh_tunes()

    def OnChangeText(self, event):
        event.Skip()
        if self.document.updating_text:
            return
        menu_builder.GrayUngray(self)
        # if auto-refresh is on
        if self.mni_auto_refresh.IsChecked():
            self.score_view.queue_number_refresh_music += 1
            wx.CallLater(250, self.AutomaticUpdate, self.score_view.queue_number_refresh_music)

    def OnUpdate(self, evt):
        c = evt.GetKeyCode()
        if c == wx.WXK_ESCAPE and self.is_fullscreen:
            self.toggle_fullscreen(evt)
        elif c == 344: #F5
            self.score_view.refresh_tunes()
        elif c == 345: #F6
            self.playback.OnToolPlay(evt)
            self.play_button.Refresh()
        elif c == 346: #F7
            self.playback.OnToolStop(evt)
        else:
            evt.Skip()

    def OnClose(self, evt):
        if self.is_closed:
            return
        if not self.document.CanClose():
            evt.Veto()
            return

        wx.GetApp().UnRegisterFrame(self)
        '''FAU 20201229: Need to stop the timer otherwise they could call back a routine that was destroyed and cause a segmentation fault on Mac'''
        self.playback.shutdown()
        self.timer.Stop()
        '''FAU 20201228: TODO: is it really what we want to do when multiple window?'''
        if wx.TheClipboard.Open():
            wx.TheClipboard.Flush()  # the text on the clipboard should be available after the app has closed
            wx.TheClipboard.Close()

        self.score_view.music_update_thread.abort()

        self.score_view.svg_tunes.cleanup()
        self.playback.midi_tunes.cleanup()
        self.settings['is_maximized'] = self.IsMaximized()
        self.Hide()
        self.Iconize(False)  # the x,y pos of the window is not properly saved if it's minimized
        self.save_settings()
        self.is_closed = True
        self.manager.UnInit()
        self.Destroy()

    def SetErrorMessage(self, error_msg):
        old_err = self.error_msg.GetValue()
        self.error_msg.SetValue(error_msg)
        pane = self.manager.GetPane('error message')

        if old_err and not error_msg:
            # 1.3.7 [JWdJ] 2016-01-06
            self.error_msg.Hide()
            if pane.IsOk():
                self.manager.DetachPane(pane)
                pane.Hide()
            self.manager.Update()
        elif not old_err and error_msg:
            # 1.3.7 [JWdJ] 2016-01-06
            if not self.error_pane.IsOk():
                self.manager.AddPane(self.error_msg, self.error_pane)
                pane = self.manager.GetPane('error message')
            pane.Show()
            self.error_msg.Show()
            self.manager.Update()
            self.editor.ScrollToLine(self.editor.LineFromPosition(self.editor.GetCurrentPos()))

    def OnTimer(self, evt):
        self.tune_list_controller.SelectOnlyTuneIfTuneNotSelected()

    def InitEditorFromSettings(self):
        font_info = self.settings.get('font')
        if font_info:
            self.InitEditor(font_info[-1], font_info[0])
        else:
            self.InitEditor()

    def InitEditor(self, font_face=None, font_size=None):
        editor = self.editor
        editor.ClearDocumentStyle()
        editor.SetLexer(stc.STC_LEX_CONTAINER)
        editor.SetProperty("fold", "0")
        editor.SetUseTabs(False)
        if not WX4:
            editor.SetUseAntiAliasing(True)

        if not font_face:
            fixedWidthFonts = ['Bitstream Vera Sans Mono', 'Courier New', 'Courier']
            #fixedWidthFonts = ['Lucida Grande', 'Monaco' 'Inconsolata', 'Consolas', 'Deja Vu Sans Mono', 'Droid Sans Mono', 'Courier', 'Andale Mono', 'Monaco', 'Courier New', 'Courier']
            wantFonts = fixedWidthFonts[:]
            size = 16
            if wx.Platform == "__WXMSW__":
                size = 10
            if wx.Platform == "__WXGTK__":
                size = 12
            fonts = wx.FontEnumerator()
            fonts.EnumerateFacenames()
            font_names = fonts.GetFacenames()
            font = None
            while wantFonts:
                font = wantFonts.pop(0)
                if font in font_names:
                    break
        else:
            font = font_face
            size = font_size
        editor.SetFont(wx.Font(size, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, faceName=font))

        editor.SetProperty("fold", "0")
        appearance = current_appearance()
        style_color = lambda key: appearance.style_color(self.settings, key)
        apply_editor_appearance(editor, appearance, style_color, font, size)

        def set_style(style_id, palette_key, attributes=''):
            editor.StyleSetSpec(style_id, "fore:%s,face:%s,%ssize:%d" % (style_color(palette_key), font, attributes, size))

        styler = self.styler
        set_style(styler.STYLE_DEFAULT, 'style_default_color')
        set_style(styler.STYLE_CHORD, 'style_chord_color')
        set_style(styler.STYLE_COMMENT_NORMAL, 'style_comment_color')
        set_style(styler.STYLE_COMMENT_SPECIAL, 'style_specialcomment_color')
        set_style(styler.STYLE_BAR, 'style_bar_color', 'bold,')
        set_style(styler.STYLE_FIELD, 'style_field_color', 'bold,')
        set_style(styler.STYLE_FIELD_VALUE, 'style_fieldvalue_color')
        set_style(styler.STYLE_EMBEDDED_FIELD, 'style_embeddedfield_color', 'bold,')
        set_style(styler.STYLE_EMBEDDED_FIELD_VALUE, 'style_embeddedfieldvalue_color')
        set_style(styler.STYLE_FIELD_INDEX, 'style_fieldindex_color', 'bold,underline,')
        set_style(styler.STYLE_STRING, 'style_string_color')
        set_style(styler.STYLE_LYRICS, 'style_lyrics_color')
        set_style(styler.STYLE_GRACE, 'style_grace_color')
        set_style(styler.STYLE_ORNAMENT, 'style_ornament_color', 'bold,')
        set_style(styler.STYLE_ORNAMENT_PLUS, 'style_ornamentplus_color')
        set_style(styler.STYLE_ORNAMENT_EXCL, 'style_ornamentexcl_color')
        self.error_marks.set_colors(style_color('style_error_color'), style_color('style_warning_color'))

        # style changes and indicator fills never fire OnModified, so a squiggle cannot re-trigger a refresh
        editor.SetModEventMask(wx.stc.STC_MODEVENTMASKALL & ~(wx.stc.STC_MOD_CHANGESTYLE | wx.stc.STC_MOD_CHANGEINDICATOR | wx.stc.STC_PERFORMED_USER))
        editor.Colourise(0, editor.GetLength())


    # 1.3.6.1 [SS] 2015-01-19
    # When AbcToSvg is called in a thread, we should not try to write to the EasyAbc frame
    # since there is a chance that the resource is already being used by the main program.
    # To prevent this, I have moved this code to a separate method.
    def update_statusbar_and_messages(self):
        # P09 2014-10-26 [SS]
        MyInfoFrame.update_text() # 1.3.6.3 [JWDJ] 2015-04-27

        # 1.3.6 2014-12-16 [SS]
        MyAbcFrame.update_text() # 1.3.6.3 [JWDJ] 2015-04-27


        # 1.3.6.3 2015-03-15 [SS]
        if app_state.messages.find('Error') != -1 or app_state.messages.find('error') != -1:
            self.statusbar.SetStatusText(_('{0} reported some errors').format('Abcm2ps'))
        elif app_state.messages.find('Warning') != -1 or app_state.messages.find('warning') != -1:
            self.statusbar.SetStatusText(_('{0} reported some warnings').format('Abcm2ps'))
        else:
            self.statusbar.SetStatusText('')

    def OnReducedMargins(self, evt):
        self.settings['reduced_margins'] = self.mni_reduced_margins.IsChecked()
        self.score_view.refresh_tunes()

    def load_settings(self):
        try:
            settings = pickle.load(open(self.settings_file, 'rb'))
        except Exception:
            settings = {} # ignore non-existant settings file (it will be created when the program exits)
        self.settings.update(settings)
        return self.settings

    def load_and_apply_settings(self, load_window_size_pos=False, load_perspective=True):
        settings = self.load_settings()

        self.editor.SetZoom(settings.get('zoom', 0))
        if load_window_size_pos:
            # 1.3.6.3 [JWDJ] 2015-04-25 # sometimes window was unreachable because window_x and window_y set to -32000
            window_x = max(settings.get('window_x', 40), 0)
            window_y = max(settings.get('window_y', 40), 0)
            window_width = max(settings.get('window_width', 1000), 600)
            window_height = max(settings.get('window_height', 800), 400)
            dimensions = window_x, window_y, window_width, window_height
            if WX4:
                self.SetSize(*dimensions)
            else:
                self.SetDimensions(*dimensions)
        if load_perspective:
            perspective = settings.get('perspective')
            # 1.3.6.3 [JWDJ] 2015-04-14 only load perspective if there is any.
            if perspective:
                self.manager.LoadPerspective(perspective)
        self.bpm_slider.SetValue(0)
        self.zoom_slider.SetValue(settings.get('score_zoom', DEFAULT_ZOOM))
        self.mni_auto_refresh.Check(settings.get('auto_refresh', True))
        self.mni_reduced_margins.Check(settings.get('reduced_margins', True))
        self.mni_TA_active.Check(settings.get('typing_assistance_active', True))
        self.mni_TA_auto_case.Check(settings.get('typing_assistance_auto_case', False))
        self.mni_TA_do_re_mi.Check(settings.get('typing_assistance_do_re_mi', False))
        self.mni_TA_add_note_durations.Check(settings.get('typing_assistance_add_note_durations', False))
        self.mni_TA_add_bar.Check(settings.get('typing_assistance_add_bar', False))
        self.mni_TA_add_bar_auto.Check(settings.get('typing_assistance_add_bar_auto', True))
        self.mni_TA_add_right.Check(settings.get('typing_assistance_add_right', True))
        self.score_view.OnZoomSlider(None)
        self.Update()
        self.Refresh()
        self.Maximize(settings.get('is_maximized', False))

        menu_builder.update_recent_files_menu(self)

        for i, width in enumerate(self.settings.get('tune_col_widths', [37, 100])):
            self.tune_list.SetColumnWidth(i, width)

        self.settings['record_bpm'] = self.settings.get('record_bpm', 70)
        item = self.bpm_menu.FindItemById(self.bpm_menu.FindItem(str(self.settings['record_bpm'])))
        item.Check()

        self.settings['record_metre'] = self.settings.get('record_metre', '3/4')
        item = self.metre_menu.FindItemById(self.metre_menu.FindItem(self.settings['record_metre']))
        item.Check()

        # reset captions since this is ruined by LoadPerspective
        self.manager.GetPane('abc editor').Caption(_("ABC code"))
        self.manager.GetPane('tune list').Caption(_("Tune list"))
        self.manager.GetPane('tune preview').Caption(_("Musical score"))
        self.manager.GetPane('error message').Caption(_("ABC errors")).Hide()
        self.manager.GetPane('abcassist').Caption(_("ABC assist")) # 1.3.6.3 [JWDJ] 2015-04-21 added ABC assist
        self.manager.Update()
        self.music_pane.reset_scrolling()

    def save_settings(self):
        settings = self.settings
        settings['zoom'] = self.editor.GetZoom()
        settings['window_x'], settings['window_y'] = self.Position
        settings['window_width'], settings['window_height'] = self.Size
        settings['perspective'] = self.manager.SavePerspective()
        settings['tempo'] = int(100.0 * self.playback.get_tempo_multiplier()) # 1.3.6.4 [JWDJ] not really necessary since setting 'tempo' is not used anymore
        settings['score_zoom'] = self.zoom_slider.GetValue()
        settings['auto_refresh'] = self.mni_auto_refresh.IsChecked()
        settings['reduced_margins'] = self.mni_reduced_margins.IsChecked()
        settings['typing_assistance_active'] = self.mni_TA_active.IsChecked()
        settings['typing_assistance_auto_case'] = self.mni_TA_auto_case.IsChecked()
        settings['typing_assistance_do_re_mi'] = self.mni_TA_do_re_mi.IsChecked()
        settings['typing_assistance_add_note_durations'] = self.mni_TA_add_note_durations.IsChecked()
        settings['typing_assistance_add_bar'] = self.mni_TA_add_bar.IsChecked()
        settings['typing_assistance_add_bar_auto'] = self.mni_TA_add_bar_auto.IsChecked()
        settings['typing_assistance_add_right'] = self.mni_TA_add_right.IsChecked()
        self.settings['tune_col_widths'] = [self.tune_list.GetColumnWidth(i) for i in range(self.tune_list.GetColumnCount())]

        try:
            pickle.dump(settings, open(self.settings_file, 'wb'))
        except IOError:
            pass


    # p09 This is a new function which verifies that the critical abcmidi
    # support functions are available. It also attempts to find the paths
    # to ghostscript if it is installed.  2014-10-14 [SS]
    def restore_settings(self):
        settings = self.settings

        abcm2ps_path = settings.get('abcm2ps_path')

        if not abcm2ps_path or not os.path.exists(abcm2ps_path):
            abcm2ps_path = get_default_path_for_executable('abcm2ps')

        if os.path.exists(abcm2ps_path):
            settings['abcm2ps_path'] = abcm2ps_path # 1.3.6 [SS] 2014-11-12
        else:
            dlg = wx.MessageDialog(self, _('abcm2ps was not found here. You need it to view the music. Go to settings and indicate the path.'), _('Warning'), wx.OK)
            dlg.ShowModal()

        abc2midi_path = settings.get('abc2midi_path', '')

        if not abc2midi_path or not os.path.exists(abc2midi_path):
            abc2midi_path = get_default_path_for_executable('abc2midi')

        if os.path.exists(abc2midi_path):
            settings['abc2midi_path'] = abc2midi_path # 1.3.6 [SS] 2014-11-12
        else:
            dlg = wx.MessageDialog(self, _('abc2midi was not found here. You need it to play the music. Go to settings and indicate the path.'), _('Warning'), wx.OK)
            dlg.ShowModal()

        midi2abc_path = settings.get('midi2abc_path')

        #1.3.6.4 [SS] 2015-06-22
        if not midi2abc_path or not os.path.exists(midi2abc_path):
            midi2abc_path = get_default_path_for_executable('midi2abc')

        if os.path.exists(midi2abc_path):
            settings['midi2abc_path'] = midi2abc_path
        else:
            dlg = wx.MessageDialog(self, _('midi2abc was not found here. You need it to play the music. Go to settings and indicate the path.'), _('Warning'), wx.OK)
            dlg.ShowModal()

        abc2abc_path = settings.get('abc2abc_path')

        if not abc2abc_path or not os.path.exists(abc2abc_path):
            abc2abc_path = get_default_path_for_executable('abc2abc')

        if os.path.exists(abc2abc_path):
            settings['abc2abc_path'] = abc2abc_path # 1.3.6 [SS] 2014-11-12
        else:
            # print('%s ***  not found ***' % abc2abc_path)
            dlg = wx.MessageDialog(self, _('abc2abc was not found here. You need it to transpose the music. Go to settings and indicate the path.'), _('Warning'), wx.OK)
            dlg.ShowModal()

        midiplayer_path = settings.get('midiplayer_path')
        if not midiplayer_path:
            settings['midiplayer_path'] = ''
        else:
            # 1.3.6.4 [SS] 2015-05-27
            if not os.path.exists(midiplayer_path):
                dlg = wx.MessageDialog(self, _('The midiplayer was not found. You will not be able to play the MIDI file.'), _('Warning'), wx.OK)
                dlg.ShowModal()

        # A stored path that no longer exists is as good as no path at all: the
        # converter it named may have been uninstalled, or removed by an OS
        # upgrade (Apple dropped /usr/bin/pstopdf in Sonoma). Detect again
        # rather than keeping a value that cannot produce a PDF.
        gs_path = settings.get('gs_path')
        if not gs_path or not os.path.exists(gs_path):
            replacement = find_ps_to_pdf_converter()
            if not replacement and gs_path:
                msg = _('The executable %s could not be found') % gs_path
                dlg = wx.MessageDialog(self, msg, _('Warning'), wx.OK)
                dlg.ShowModal()
            settings['gs_path'] = replacement

        #Fix midi_program_ch settings - 1.3.5 to 1.3.6 compatibility 2014-11-14
        midi_program_ch_list = ['midi_program_ch%d' % ch for ch in range(1, 16 + 1)]
        for channel in range(16):
            if settings.get(midi_program_ch_list[channel]):
                pass
            else:
                settings[midi_program_ch_list[channel]] = [default_midi_instrument, default_midi_volume, default_midi_pan]

        #delete 'one_instrument_only'. It is no longer used. 1.3.6 [SS] 2014-11-20
        try:
            del self.settings['one_instrument_only']
        except:
            pass

        # 1.3.6 [SS] 2014-12-18
        new_settings = [('midi_program', default_midi_instrument), ('midi_chord_program', 24),
                        ('transposition',0), ('tuning',440),
                        ('nodynamics', False), ('nofermatas', False),
                        ('nograce', False), ('barfly', True),
                        ('searchfolder', self.app_dir), ('xmlcompressed', False),
                        ('xmlunfold', False), ('xmlmidi', False), ('xml_v','0'), ('xml_d', '0'),
                        ('xml_b','0'), ('xml_c', '0'), ('xml_n', '0'), ('xml_u', '0'),
                        ('xml_p', ''),
                        ('abcm2ps_number_bars', False), ('abcm2ps_no_lyrics', False),
                        ('abcm2ps_refnumbers', False), ('abcm2ps_ignore_ends', False),
                        ('abcm2ps_leftmargin', '1.78'), ('abcm2ps_rightmargin', '1.78'),
                        ('abcm2ps_topmargin', '1.00'), ('abcm2ps_botmargin', '1.00'),
                        ('abcm2ps_scale', '0.75'), ('abcm2ps_clean', False),
                        ('abcm2ps_defaults', True), ('abcm2ps_pagewidth', '21.59'),
                        ('abcm2ps_pageheight', '27.94'), ('midiplayer_parameters', ''),
                        ('bpmtempo', 120), ('chordvol', default_midi_volume), ('bassvol', default_midi_volume),
                        ('melodyvol', default_midi_volume), ('midi_intro', 0), ('version', program_version)
                       ]

        # 1.3.6 [SS] 2014-12-16
        for item in new_settings:
            term = item[0]
            value = item[1]
            if term in self.settings:
                pass
            else:
                self.settings[term] = value

        self.settings['gchord'] = 'default' # 1.3.6 [SS] 2014-11-26

#p09 2014-10-22


#1.3.6.4 [SS] 2015-06-22


class MyApp(wx.App):
    def __init__(self, *args, **kargs):
        self._frames = []
        self.settings = {}
        wx.App.__init__(self, *args, **kargs)

    def CheckCanDrawSharpFlat(self):
        dc = wx.MemoryDC(wx_bitmap(200, 200, 32))
        dc.SetBackground(wx.WHITE_BRUSH)
        dc.Clear()
        dc = wx.GraphicsContext.Create(dc)
        try:
            for text in (u'G\u266d', u'G\u266f'):
                font_size = 12
                wxfont = wx.Font(font_size, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, 'Helvetica', wx.FONTENCODING_DEFAULT )
                wxfont.SetPointSize(font_size)
                font = dc.CreateFont(wxfont, wx_colour('black'))
                dc.SetFont(font)
                (width, height, descent, externalLeading) = dc.GetFullTextExtent(text)
                dc.DrawText(text, 100, 100-height+descent)
            self.settings['can_draw_sharps_and_flats'] = True
        except wx.PyAssertionError:
            self.settings['can_draw_sharps_and_flats'] = False


    def NewMainFrame(self, options = None):
        frame = MainFrame(None, 0, self.app_dir, self.settings, options or {})
        self._frames.append(frame)
        return frame

    def UnRegisterFrame(self, frame):
        self._frames.remove(frame)

    def GetAllFrames(self):
        L = self._frames[:]
        L.sort(key=lambda f: not f.IsActive()) # make sure an active frame comes first in the list
        return L

    def MacOpenFile(self, filename):	# [EPO] 2018-11-20 TODO  dup open file creates two frames (why?)
        """Called for files dropped on dock icon, or opened via finders context menu"""
        #dlg = wx.MessageDialog(None,
        #                       "This app was just asked to open:\n%s\n"%filename,
        #                       "File Dropped",
        #                       wx.OK|wx.ICON_INFORMATION)
        #dlg.ShowModal()
        #dlg.Destroy()
        #frame = self.NewMainFrame()
        #frame.Show(True)
        #self.SetTopWindow(frame)
        ##path = os.path.abspath(sys.argv[1]).decode(sys.getfilesystemencoding())
        #self.frame.document.load_or_import(filename)
        if not self.frame.editor.GetModify() and not self.frame.document.current_file:     # if a new unmodified document
            self.frame.document.load(filename)
        else:
            self.frame = self.NewMainFrame()
            self.frame.document.load(filename)
            
    def MacNewFile(self):
        #dlg = wx.MessageDialog(None,
        #                       "This app was just asked to launch",
        #                       "App started",
        #                       wx.OK|wx.ICON_INFORMATION)
        #dlg.ShowModal()
        #dlg.Destroy()
        recent_file = self.settings.get('recentfiles', '').split('|')[0]
        if recent_file and os.path.exists(recent_file):
            path = recent_file

        if path :
            self.frame.document.load_or_import(path)

    def OnInit(self):
        try:
            self.SetAppName('EasyABC')
            #wx.SystemOptions.SetOptionInt('msw.window.no-clip-children', 1)
            app_dir = self.app_dir = wx.StandardPaths.Get().GetUserLocalDataDir()
            if not os.path.exists(app_dir):
                os.mkdir(app_dir)
            cache_dir = os.path.join(app_dir, 'cache')
            if not os.path.exists(cache_dir):
                os.mkdir(cache_dir)
            default_lang = wx.LANGUAGE_DEFAULT
            locale = wx.Locale(language=default_lang)
            locale.AddCatalogLookupPathPrefix(os.path.join(cwd, 'locale'))
            locale.AddCatalog('easyabc')
            self.locale = locale # keep this reference alive
            global current_locale
            current_locale = locale
            wx.ToolTip.Enable(True)
            wx.ToolTip.SetDelay(1000)

            self.CheckCanDrawSharpFlat()
            options = {}
            
            path = None
            if len(sys.argv) > 1:
                if sys.version_info >= (3,0,0): #FAU 20210101: In Python3 there isn't anymore the decode.
                    args = sys.argv
                else:
                    fse = sys.getfilesystemencoding()
                    args = [arg.decode(fse) for arg in sys.argv]

                i = 0
                while i < len(args):
                    arg = args[i]
                    i += 1
                    if arg.startswith('-'):
                        arg = arg[1:]
                        if arg == 'exclusive':
                            options[arg] = 'True'
                    else:
                        path = os.path.abspath(arg)

            #p08 We need to be able to find app.frame [SS] 2014-10-14
            self.frame = self.NewMainFrame(options)
            self.frame.Show(True)
            self.SetTopWindow(self.frame)

            # 1.3.8.4 [mist] Load most recent file
            if not path:
                recent_file = self.settings.get('recentfiles', '').split('|')[0]
                if recent_file and os.path.exists(recent_file):
                    path = recent_file

            #FAU: on Mac the sys.frozen is set by py2app and pyinstaller and is unset otherwise getattr( sys, 'frozen', False)
            if path and wx.Platform != "__WXMAC__":
                self.frame.document.load_or_import(path)
        except:
            sys.stdout.write(traceback.format_exc())
        return True

if __name__ == '__main__':
    app = MyApp(0)

    #import wx.lib.inspection
    #wx.lib.inspection.InspectionTool().Show()

    app.MainLoop()
    app_state.running = False
current_locale = None
app = None
