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
from collections import namedtuple

import wx
from wx import GetTranslation as _

from appearance import DEFAULT_NOTE_HIGHLIGHT as default_note_highlight_color, \
    DEFAULT_NOTE_HIGHLIGHT_FOLLOW as default_note_highlight_follow_color, current_appearance
from background_threads import pypm
from constants import control_margin, cwd, default_midi_volume, default_midi_instrument, default_midi_pan
from generalmidi import general_midi_instruments
from wxhelper import WX4


class MyNoteBook(wx.Frame):
    ''' Settings Notebook '''
    def __init__(self, parent, settings, statusbar):
        wx.Frame.__init__(self, parent, wx.ID_ANY, _("Abc settings"), style=wx.DEFAULT_FRAME_STYLE, name='settingsbook')
        # Add a panel so it looks the correct on all platforms
        p = wx.Panel(self)
        nb = wx.Notebook(p)
        # 1.3.6.4 [SS] 2015-05-26 added statusbar
        abcsettings = AbcFileSettingsFrame(nb, settings, statusbar, parent.playback.mc)
        abcm2pspage = MyAbcm2psPage(nb, settings, abcsettings)
        self.chordpage = MyChordPlayPage(nb, settings)
        self.voicepage = MyVoicePage(nb, settings)
        # 1.3.6.1 [SS] 2015-02-02
        xmlpage    = MusicXmlPage(nb, settings)
        colorsettings = ColorSettingsFrame(nb, settings)
        nb.AddPage(abcm2pspage, _("Abcm2ps"))
        self.chordpage_id = nb.PageCount
        nb.AddPage(self.chordpage, _("Abc2midi"))
        self.voicepage_id = nb.PageCount
        nb.AddPage(self.voicepage, _("Voices"))
        nb.AddPage(xmlpage, _("MusicXML"))
        nb.AddPage(abcsettings, _("File Settings"))
        nb.AddPage(colorsettings, _("Colors"))
        nb.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.OnPageChanged)

        sizer = wx.BoxSizer()
        sizer.Add(nb, 1, wx.ALL|wx.EXPAND)
        p.SetSizer(sizer)
        sizer.Fit(self)

    def OnPageChanged(self, event):
        if event.GetSelection() == self.voicepage_id:
            self.voicepage.FillControls()
        elif event.GetSelection() == self.chordpage_id:
            self.chordpage.FillControls()
        event.Skip()


class AbcFileSettingsFrame(wx.Panel):
    # 1.3.6.4 [SS] 2015-05-26 added statusbar
    def __init__(self, parent, settings, statusbar, mc):
        wx.Panel.__init__(self, parent)
        self.settings = settings
        self.statusbar = statusbar
        self.mc = mc
        border = control_margin

        PathEntry = namedtuple('PathEntry', 'name display_name tooltip add_default wildcard on_change')

        # 1.3.6.3 [JWDJ] 2015-04-27 replaced TextCtrl with ComboBox for easier switching of versions
        self.needed_path_entries = [
            PathEntry('abcm2ps', _('abcm2ps executable:'), _('This executable is used to display the music'), True, None, None),
            PathEntry('abc2midi', _('abc2midi executable:'), _('This executable is used to make the midi file'), True, None, None),
            PathEntry('abc2abc', _('abc2abc executable:'), _('This executable is used to transpose the music'), True, None, None),
            # 1.3.6.4 [SS] 2015-06-22
            PathEntry('midi2abc', _('midi2abc executable:'), _('This executable is used to disassemble the output midi file'), True, None, None),
            PathEntry('gs', _('ghostscript executable:'), _('This executable is used to create PDF files'), False, None, None),
            PathEntry('nwc2xml', _('nwc2xml executable:'), _('For NoteWorthy Composer - Windows only'), False, None, None),
            PathEntry('ffmpeg', _('ffmpeg executable:'), _('This executable is used to convert music to compressed formats'), False, None, None),
            PathEntry('midiplayer', _('midiplayer:'), _('Your preferred MIDI player'), False, None, self.midiplayer_changed),
            PathEntry('soundfont', _('SoundFont:'), _('Your preferred SoundFont (.sf2)'), False, 'SoundFont (*.sf2;*.sf3)|*.sf2;*.sf3', self.soundfont_changed)
        ]


        if wx.Platform == "__WXMSW__":
            self.exe_file_mask = '*.exe'
        else:
            self.exe_file_mask = '*'

        sizer = wx.GridBagSizer()
        if wx.Platform == "__WXMAC__":
            sizer.Add(wx.StaticText(self, wx.ID_ANY, _('File paths to required executables') + ':'), pos=(0,0), span=(0,2), flag=wx.ALL, border=border)
            r = 1
        else:
            r = 0

        self.browsebutton_to_control = {}
        self.browsebutton_to_wildcard = {}
        self.control_to_name = {}
        self.afterchanged = {}
        for entry in self.needed_path_entries:
            setting_name = '%s_path' % entry.name
            current_path = self.settings.get(setting_name, '')
            self.afterchanged[setting_name] = entry.on_change
            setting_name_choices = '%s_path_choices' % entry.name
            path_choices = self.settings.get(setting_name_choices, '').split('|')
            path_choices = self.keep_existing_paths(path_choices)
            path_choices = self.append_exe(current_path, path_choices)
            if entry.add_default:
                path_choices = self.append_exe(self.get_default_path(entry.name), path_choices)
            control = wx.ComboBox(self, wx.ID_ANY, size=wx.Size(450,22),choices=path_choices, style=wx.CB_DROPDOWN)
            # [SS] 1.3.6.4 2015-12-23
            if current_path:
                control.SetValue(current_path)
            control.Bind(wx.EVT_TEXT, self.OnChangePath, control)

            self.control_to_name[control] = entry.name
            if entry.tooltip:
                control.SetToolTip(wx.ToolTip(entry.tooltip))

            browse_button = wx.Button(self, wx.ID_ANY, _('Browse...'))
            self.browsebutton_to_control[browse_button] = control
            self.browsebutton_to_wildcard[browse_button] = entry.wildcard
            sizer.Add(wx.StaticText(self, wx.ID_ANY, entry.display_name), pos=(r,0), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
            sizer.Add(control, pos=(r,1), flag=wx.ALL | wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, border=border)
            sizer.Add(browse_button, pos=(r,2), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)

            browse_button.Bind(wx.EVT_BUTTON, self.OnBrowse, browse_button)

            r += 1

        sizer.AddGrowableCol(1)

        if wx.Platform == "__WXMAC__":
            box2 = sizer
        else:
            box2 = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, _("File paths to required executables")), wx.VERTICAL)
            box2.Add(sizer, flag=wx.ALL | wx.EXPAND)

        self.chkIncludeHeader = wx.CheckBox(self, wx.ID_ANY, _('Include file header when rendering tunes'))

        # 1.3.6.3 [SS] 2015-04-29
        extraplayerparam = wx.StaticText(self, wx.ID_ANY, _("Extra MIDI player parameters"))
        self.extras = wx.TextCtrl(self, wx.ID_ANY, size=(200, 22))

        midiplayer_params_sizer = wx.GridBagSizer()
        midiplayer_params_sizer.Add(self.chkIncludeHeader, pos=(0,0), span=(0,2), flag=wx.ALL, border=border)
        midiplayer_params_sizer.Add(extraplayerparam, pos=(1,0), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        midiplayer_params_sizer.Add(self.extras, pos=(1,1), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)

        self.restore_settings = wx.Button(self, wx.ID_ANY, _('Restore settings')) # 1.3.6.3 [JWDJ] 2015-04-25 renamed
        check_toolTip = _('Restore default file paths to abcm2ps, abc2midi, abc2abc, ghostscript when blank')
        self.restore_settings.SetToolTip(wx.ToolTip(check_toolTip))

        # build settings dialog with the previously defined box
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(box2, flag=wx.ALL | wx.EXPAND, border=10)
        # 1.3.6.1 [SS] 2015-01-28
        self.sizer.Add(midiplayer_params_sizer, flag=wx.ALL | wx.EXPAND, border=border)
        self.sizer.Add(self.restore_settings, flag=wx.ALL | wx.ALIGN_RIGHT, border=border)

        self.SetSizer(self.sizer)
        self.SetAutoLayout(True)
        self.Centre()
        self.sizer.Fit(self)

        self.chkIncludeHeader.SetValue(self.settings.get('abc_include_file_header', True))
        self.extras.SetValue(self.settings.get('midiplayer_parameters', ''))

        # 1.3.6.1 [SS] 2015-01-28
        self.chkIncludeHeader.Bind(wx.EVT_CHECKBOX, self.On_Chk_IncludeHeader, self.chkIncludeHeader)
        # 1.3.6.3 [SS] 2015-04-29
        self.extras.Bind(wx.EVT_TEXT, self.On_extra_midi_parameters, self.extras)

        self.restore_settings.Bind(wx.EVT_BUTTON, self.OnRestoreSettings, self.restore_settings)

    def OnBrowse(self, evt):
        control = self.browsebutton_to_control[evt.EventObject]
        wildcard = self.browsebutton_to_wildcard[evt.EventObject]
        if (wildcard is None):
            wildcard = self.exe_file_mask
        path = control.GetValue()
        default_dir, default_file = os.path.split(path) # 1.3.6.3 [JWDJ] uses current folder as default
        dlg = wx.FileDialog(
            self, message=_("Choose a file"), defaultDir=default_dir, defaultFile=default_file, wildcard=wildcard, style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_CHANGE_DIR )
        try:
            if dlg.ShowModal() == wx.ID_OK:
                path = dlg.GetPath()
                control.SetValue(path)
                if wx.Platform != "__WXMSW__":
                    # 1.3.6.4 [SS] 2015-06-23
                    self.change_path_for_control(control, path)  # 1.3.6.4 [JWDJ] 2015-06-23 in case control.SetValue(path) does not trigger OnChangePath
        finally:
            dlg.Destroy() # 1.3.6.3 [JWDJ] 2015-04-21 always clean up dialog window

    def OnChangePath(self, evt):
        if wx.Platform == "__WXMAC__":
            self.statusbar.SetStatusText('Updating path') # for Mac-users to see
        control = evt.EventObject
        path = evt.String
        self.change_path_for_control(control, path)

    def change_path_for_control(self, control, path):
        name = self.control_to_name[control]
        setting_name = '%s_path' % name
        self.settings[setting_name] = path
        if isinstance(control, wx.ComboBox):
            setting_name_choices = '%s_path_choices' % name
            paths = self.append_exe(path, control.Items)
            self.settings[setting_name_choices] = '|'.join(paths)
        # 1.3.6.4 [SS] 2015-05-26
        self.statusbar.SetStatusText(setting_name + ' was updated to '+ path)
        on_changed = self.afterchanged.get(setting_name)
        if on_changed is not None:
            on_changed(path)

    def midiplayer_changed(self, path):
        app = wx.GetApp()
        app.frame.update_play_button() # 1.3.6.3 [JWDJ] 2015-04-21 playbutton enabling centralized

    def soundfont_changed(self, sf2_path):
        try:
            if os.path.exists(sf2_path):
                wait = wx.BusyCursor()
                self.mc.set_soundfont(sf2_path)         # load another sound font
                del wait
        except:
            pass

    def On_Chk_IncludeHeader(self, event):
        self.settings['abc_include_file_header'] = self.chkIncludeHeader.GetValue()

    # [SS] 2015-04-29
    def On_extra_midi_parameters(self, event):
        self.settings['midiplayer_parameters'] = self.extras.GetValue()

    def OnRestoreSettings(self, event):
        # 1.3.6.1 [SS] 2015-02-03
        result = wx.MessageBox(_("This button will restore some of the paths to the executables (abcmp2s, abc2midi, etc.) to "
        "their defaults. In order that the program knows which paths to restore, you need to make those paths blank prior to continuing. "
        "You can do this by selecting the entry box, cntr-A to select all and cntr-X to delete. "
        "If this was not done, click Cancel first and then try again."),
                               _("Proceed?"), wx.ICON_QUESTION | wx.OK | wx.CANCEL)
        if result == wx.OK:
            for entry in self.needed_path_entries:
                setting_name = '%s_choices' % entry.name
                if setting_name in self.settings:
                    del self.settings[setting_name] # 1.3.6.3 [JWDJ] clean up unwanted paths

            frame = wx.GetApp()._frames[0]
            frame.restore_settings()
            frame.settingsbook.Show(False)
            frame.settingsbook.Destroy()
            frame.settingsbook = MyNoteBook(self, self.settings, self.statusbar)
            frame.settingsbook.Show()

    def append_exe(self, path, paths):
        if path and not path in paths and os.path.isfile(path) and os.access(path, os.X_OK):
            paths.append(path)
        return paths

    def keep_existing_paths(self, paths):
        result = []
        for path in paths:
            if path and os.path.exists(path):
                result.append(path)
        return result

    def get_default_path(self, executable):
        if wx.Platform == "__WXMSW__":
            return os.path.join(cwd, 'bin', '%s.exe' % executable)
        elif wx.Platform == "__WXMAC__":
            return os.path.join(cwd, 'bin', executable)
        else:
            return os.path.join(cwd, 'bin', executable)


class MyChordPlayPage (wx.Panel):
    def __init__(self, parent, settings):
        wx.Panel.__init__(self, parent)
        gridsizer = wx.FlexGridSizer(20, 4, 2, 2)
        # midi_box to set default instrument for playback
        midi_box = wx.GridBagSizer()
        border = control_margin
        self.settings = settings

        # 1.3.6.4 [SS] 2015-05-28 shrunk width from 250 to 200
        self.cmbMidiProgram = wx.ComboBox(self, wx.ID_ANY, choices=[], size=(200, 26), style=wx.CB_DROPDOWN | wx.CB_READONLY)
        #1.3.6.4 [SS] 2015-07-08
        self.sliderVol = wx.Slider(self, value=default_midi_volume, minValue=0, maxValue=127,
                                size=(128, -1), style=wx.SL_HORIZONTAL)
        self.Voltxt = wx.StaticText(self, wx.ID_ANY, " ")

        self.cmbMidiChordProgram = wx.ComboBox(self, wx.ID_ANY, choices=[], size=(200, 26), style=wx.CB_DROPDOWN | wx.CB_READONLY)
        #1.3.6.4 [SS] 2015-06-07
        self.sliderChordVol = wx.Slider(self, value=default_midi_volume, minValue=0, maxValue=127,
                                size=(128, -1), style=wx.SL_HORIZONTAL)
        self.ChordVoltxt = wx.StaticText(self, wx.ID_ANY, " ")

        self.cmbMidiBassProgram = wx.ComboBox(self, wx.ID_ANY, choices=[], size=(200, 26), style=wx.CB_DROPDOWN | wx.CB_READONLY)
        self.sliderBassVol = wx.Slider(self, value=default_midi_volume, minValue=0, maxValue=127,
                                size=(128, -1), style=wx.SL_HORIZONTAL)
        self.BassVoltxt = wx.StaticText(self, wx.ID_ANY, " ")

        #1.3.6.4 [SS] 2015-06-10
        self.sliderbeatsperminute = wx.Slider(self, value=120, minValue=60, maxValue=240,
                                size=(80, -1), style=wx.SL_HORIZONTAL)
        self.slidertranspose = wx.Slider(self, value=0, minValue=-11, maxValue=11,
                                size=(80, -1), style=wx.SL_HORIZONTAL)
        self.slidertuning = wx.Slider(self, value=440, minValue=415, maxValue=466,
                                size=(80, -1), style=wx.SL_HORIZONTAL)
        self.beatsperminutetxt = wx.StaticText(self, wx.ID_ANY, " ")
        self.transposetxt      = wx.StaticText(self, wx.ID_ANY, " ")
        self.tuningtxt         = wx.StaticText(self, wx.ID_ANY, " ")

        #1.3.6 [SS] 2014-11-21
        self.chkPlayChords = wx.CheckBox(self, wx.ID_ANY, _('Play chords'))
        self.nodynamics = wx.CheckBox(self, wx.ID_ANY, _('Ignore Dynamics'))
        self.nofermatas = wx.CheckBox(self, wx.ID_ANY, _('Ignore Fermatas'))
        self.nograce    = wx.CheckBox(self, wx.ID_ANY, _('No Grace Notes'))
        self.barfly     = wx.CheckBox(self, wx.ID_ANY, _('Barfly Mode'))
        self.midi_intro = wx.CheckBox(self, wx.ID_ANY, _('Count in'))

        #1.3.6 [SS] 2014-11-26
        gchordtxt = wx.StaticText(self, wx.ID_ANY, _("gchord pattern"))
        self.gchordcombo = wx.ComboBox(self, wx.ID_ANY, 'default', (-1, -1), (128, -1), [], wx.CB_DROPDOWN)
        gchordchoices = ['default', 'f', 'fzfz', 'gi', 'gihi', 'f4c2', 'ghihgh', 'g2hg2h']
        self.SetGchordChoices(gchordchoices)

        midi_box.Add(wx.StaticText(self, wx.ID_ANY, _('Instrument for playback') + ': '), pos=(0,0), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        midi_box.Add(self.sliderVol, pos=(0,2), flag=wx.ALL | wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, border=border)
        midi_box.Add(self.Voltxt, pos=(0,3), flag=wx.ALL| wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, border=border)
        midi_box.Add(self.cmbMidiProgram, pos=(0,1), flag=wx.ALL | wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, border=border)
        midi_box.Add(wx.StaticText(self, wx.ID_ANY, _("Instrument for chord's playback") + ': '), pos=(1,0), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        midi_box.Add(self.cmbMidiChordProgram, pos=(1,1), flag=wx.ALL | wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, border=border)
        midi_box.Add(self.sliderChordVol, pos=(1,2), flag=wx.ALL| wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, border=border)
        midi_box.Add(self.ChordVoltxt, pos=(1,3), flag=wx.ALL| wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, border=border)
        midi_box.Add(wx.StaticText(self, wx.ID_ANY, _("Instrument for bass chord's playback") + ': '), pos=(2,0), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        midi_box.Add(self.cmbMidiBassProgram, pos=(2,1), flag=wx.ALL | wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, border=border)
        midi_box.Add(self.sliderBassVol, pos=(2,2), flag=wx.ALL| wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, border=border)
        midi_box.Add(self.BassVoltxt, pos=(2,3), flag=wx.ALL| wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, border=border)

        # 1.3.6.4 [SS] 2015-06-10
        midi_box.Add(wx.StaticText(self, wx.ID_ANY, _("Default Tempo") + ': '), pos=(3,0), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        midi_box.Add(self.sliderbeatsperminute, pos=(3,1), flag=wx.ALL | wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, border=border)
        midi_box.Add(self.beatsperminutetxt, pos=(3,2), flag=wx.ALL | wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, border=border)
        midi_box.Add(wx.StaticText(self, wx.ID_ANY, _("Transposition") + ': '), pos=(4,0), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        midi_box.Add(self.slidertranspose, pos=(4,1), flag=wx.ALL | wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, border=border)
        midi_box.Add(self.transposetxt, pos=(4,2), flag=wx.ALL | wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, border=border)
        midi_box.Add(wx.StaticText(self, wx.ID_ANY, _("Tuning") + ': '), pos=(5,0), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        midi_box.Add(self.slidertuning, pos=(5,1), flag=wx.ALL | wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, border=border)
        midi_box.Add(self.tuningtxt, pos=(5,2), flag=wx.ALL | wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, border=border)

        midi_box.Add(self.chkPlayChords, pos=(6,0), flag=wx.ALL | wx.EXPAND, border=border)
        midi_box.Add(self.nodynamics, pos=(6,1), flag=wx.ALL | wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, border=border)
        midi_box.Add(self.nofermatas, pos=(7,0), flag=wx.ALL | wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, border=border)
        midi_box.Add(self.nograce, pos=(7,1), flag=wx.ALL | wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, border=border)
        midi_box.Add(self.barfly, pos=(8,0), flag=wx.ALL | wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, border=border)
        midi_box.Add(self.midi_intro, pos=(8,1), flag=wx.ALL | wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, border=border)
        midi_box.Add(gchordtxt, pos=(9,0), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        midi_box.Add(self.gchordcombo, pos=(9,1), flag=wx.ALL | wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, border=border)

        self.chkPlayChords.SetValue(self.settings.get('play_chords', False))
        self.slidertranspose.SetValue(self.settings.get('transposition', 0))
        self.transposetxt.SetLabel(str(self.settings.get('transposition', 0)))
        self.slidertuning.SetValue(self.settings.get('tuning', 440))
        self.tuningtxt.SetLabel(str(self.settings.get('tuning', 440)))
        self.sliderVol.SetValue(int(self.settings.get('melodyvol', default_midi_volume)))
        self.Voltxt.SetLabel(str(self.settings.get('melodyvol', default_midi_volume)))
        self.sliderChordVol.SetValue(int(self.settings.get('chordvol', default_midi_volume)))
        self.ChordVoltxt.SetLabel(str(self.settings.get('chordvol', default_midi_volume)))
        self.sliderBassVol.SetValue(int(self.settings.get('bassvol', default_midi_volume)))
        self.BassVoltxt.SetLabel(str(self.settings.get('bassvol', default_midi_volume)))
        self.nodynamics.SetValue(self.settings.get('nodynamics', False))
        self.nofermatas.SetValue(self.settings.get('nofermatas', False))
        self.nograce.SetValue(self.settings.get('nograce', False))
        self.barfly.SetValue(self.settings.get('barfly', True))
        # 1.3.6.4 [SS[ 2015-07-05
        self.midi_intro.SetValue(self.settings.get('midi_intro', False))
        # 1.3.6.4 [SS] 2015-06-10
        bpmtempo = self.settings.get('bpmtempo', 120)
        self.sliderbeatsperminute.SetValue(int(bpmtempo))
        self.beatsperminutetxt.SetLabel(str(bpmtempo))

        beatsperminute_toolTip = _('Quarter notes per minute')
        ChordVol_toolTip = _('Volume level for chordal accompaniment')
        BassVol_toolTip  = _('Volume level for bass accompaniment')
        barfly_toolTip = _('The Barfly stress model is enabled provided the rhythm designator (R:) is recognized')
        nodynamics_toolTip = _('Dynamic markings like ff mp pp etc. are ignored if enabled')
        nofermatas_toolTip = _('Fermata markings are ignored if enabled')
        nograce_toolTip = _('Grace notes are ignored if enabled')
        transpose_toolTip = _('Transpose by the number of semitones')
        tuning_toolTip = _('Frequency of A in Hz')
        count_toolTip  = _('Two rest bars before music starts')
        vol_toolTip = _('Volume of melody line if the tune does not have any voices')

        self.sliderbeatsperminute.SetToolTip(wx.ToolTip(beatsperminute_toolTip))
        self.sliderChordVol.SetToolTip(wx.ToolTip(ChordVol_toolTip))
        self.sliderBassVol.SetToolTip(wx.ToolTip(BassVol_toolTip))
        self.nodynamics.SetToolTip(wx.ToolTip(nodynamics_toolTip))
        self.nofermatas.SetToolTip(wx.ToolTip(nofermatas_toolTip))
        self.nograce.SetToolTip(wx.ToolTip(nograce_toolTip))
        self.barfly.SetToolTip(wx.ToolTip(barfly_toolTip))
        self.midi_intro.SetToolTip(wx.ToolTip(count_toolTip))
        self.slidertranspose.SetToolTip(wx.ToolTip(transpose_toolTip))
        self.slidertuning.SetToolTip(wx.ToolTip(tuning_toolTip))
        self.sliderVol.SetToolTip(wx.ToolTip(vol_toolTip))

        #1.3.6 [SS] 2014-11-24
        self.chkPlayChords.Bind(wx.EVT_CHECKBOX, self.OnPlayChords)
        self.nodynamics.Bind(wx.EVT_CHECKBOX, self.OnNodynamics)
        self.nofermatas.Bind(wx.EVT_CHECKBOX, self.OnNofermatas)
        self.nograce.Bind(wx.EVT_CHECKBOX, self.OnNograce)
        self.barfly.Bind(wx.EVT_CHECKBOX, self.OnBarfly)
        self.sliderbeatsperminute.Bind(wx.EVT_SCROLL, self.OnBeatsPerMinute)
        self.slidertranspose.Bind(wx.EVT_SCROLL, self.OnTranspose)
        self.slidertuning.Bind(wx.EVT_SCROLL, self.OnTuning)
        #1.3.6.4 [SS] 2015-06-07
        self.sliderChordVol.Bind(wx.EVT_SCROLL, self.OnChordVol)
        self.sliderBassVol.Bind(wx.EVT_SCROLL, self.OnBassVol)
        #1.3.6.4 [SS] 2015-07-05
        self.midi_intro.Bind(wx.EVT_CHECKBOX, self.OnMidiIntro)
        #1.3.6.4 [SS] 2015-07-09
        self.sliderVol.Bind(wx.EVT_SCROLL, self.OnMelodyVol)

        #1.3.6 [SS] 2014-11-26
        self.gchordcombo.Bind(wx.EVT_COMBOBOX, self.OnGchordSelection, self.gchordcombo)
        self.gchordcombo.Bind(wx.EVT_TEXT, self.OnGchordSelection, self.gchordcombo)
        self.gchordcombo.SetToolTip(wx.ToolTip(_('f = fundamental\nc = chord\nz = rest\n\nfor chord C:\nf -> C,,\nc -> [C,E,G]\ng -> C\nh -> E\ni -> G\nj -> B\nG -> C,,\nH -> E,,\nI -> G,,\nJ -> B,')))

        #1.3.6 [SS] 2014-11-15
        self.cmbMidiProgram.Bind(wx.EVT_COMBOBOX, self.OnMidi_Program)
        self.cmbMidiChordProgram.Bind(wx.EVT_COMBOBOX, self.On_midi_chord_program)
        self.cmbMidiBassProgram.Bind(wx.EVT_COMBOBOX, self.On_midi_bass_program)

        self.SetSizer(midi_box)
        self.SetAutoLayout(True)
        self.Fit()
        self.Layout()
        self.controls_initialized = False

    def FillControls(self):
        if self.controls_initialized:
            return

        instruments = general_midi_instruments
        self.cmbMidiProgram.Append(instruments)
        self.cmbMidiChordProgram.Append(instruments)
        self.cmbMidiBassProgram.Append(instruments)
        try:
            self.cmbMidiProgram.Select(self.settings.get('midi_program', default_midi_instrument))
            self.cmbMidiChordProgram.Select(self.settings.get('midi_chord_program', 25))
            self.cmbMidiBassProgram.Select(self.settings.get('midi_bass_program', 25))
        except:
            pass

        self.controls_initialized = True


    def OnPlayChords(self, evt):
        self.settings['play_chords'] = self.chkPlayChords.GetValue()

# 1.3.6 [SS] 2014-11-24
    def OnNodynamics(self, evt):
        self.settings['nodynamics'] = self.nodynamics.GetValue()

    def OnNofermatas(self, evt):
        self.settings['nofermatas'] = self.nofermatas.GetValue()

    def OnNograce(self, evt):
        self.settings['nograce'] = self.nograce.GetValue()

    def OnBarfly(self, evt):
        self.settings['barfly'] = self.barfly.GetValue()

# 1.3.6.4 [SS] 2015-07-05
    def OnMidiIntro(self, evt):
        self.settings['midi_intro'] = self.midi_intro.GetValue()

    def OnMidi_Program(self, evt):
        self.settings['midi_program'] = self.cmbMidiProgram.GetSelection()

    def On_midi_chord_program(self, evt):
        self.settings['midi_chord_program'] = self.cmbMidiChordProgram.GetSelection()

    def On_midi_bass_program(self, evt):
        self.settings['midi_bass_program'] = self.cmbMidiBassProgram.GetSelection()

# 1.3.6 [SS] 2014-11-26
    def SetGchordChoices(self, choices):
        ''' sets the gchord string choices in the gchord combo widget '''
        self.gchordcombo.Clear()
        for item in choices:
            self.gchordcombo.Append(item)

    def OnGchordSelection(self, evt):
        ''' saves the gchord string selection '''
        self.settings['gchord'] = self.gchordcombo.GetValue()

# 1.3.6.4 [SS] 2015-06-10
    def OnBeatsPerMinute(self, evt):
        self.settings['bpmtempo'] = str(self.sliderbeatsperminute.GetValue())
        self.beatsperminutetxt.SetLabel(str(self.settings['bpmtempo']))


# 1.3.6.3 [SS] 2015-03-19
    def OnTranspose(self, evt):
        self.settings['transposition'] = self.slidertranspose.GetValue()
        self.transposetxt.SetLabel(str(self.settings['transposition']))

# 1.3.6.3 [SS] 2015-03-19
    def OnTuning(self, evt):
        self.settings['tuning'] = self.slidertuning.GetValue()
        self.tuningtxt.SetLabel(str(self.settings['tuning']))

#1.3.6.4 [SS] 2015-06-07
    def OnChordVol(self, evt):
        self.settings['chordvol'] = self.sliderChordVol.GetValue()
        self.ChordVoltxt.SetLabel(str(self.sliderChordVol.GetValue()))

#1.3.6.4 [SS] 2015-06-07
    def OnBassVol(self, evt):
        self.settings['bassvol'] = self.sliderBassVol.GetValue()
        self.BassVoltxt.SetLabel(str(self.sliderBassVol.GetValue()))

#1.3.6.4 [SS] 2015-07-09
    def OnMelodyVol(self, evt):
        melodyvol = self.sliderVol.GetValue()
        self.settings['melodyvol'] = melodyvol
        self.Voltxt.SetLabel(str(melodyvol))


class MyVoicePage(wx.Panel):
    def __init__(self, parent, settings):
        wx.Panel.__init__(self, parent)
        self.settings = settings
        border = control_margin
        channel = 1
        self.controls_initialized = False

        # definition of box for voice 1 to 16 (MIDI is limited to 16 channels)
        self.cmbMidiProgramCh_list = {}
        self.sldMidiControlVolumeCh_list = {}
        self.textValueMidiControlVolumeCh_list = {}
        self.sldMidiControlPanCh_list = {}
        self.textValueMidiControlPanCh_list = {}
        self.chkPerVoice = wx.CheckBox(self, wx.ID_ANY, _('Separate defaults per voice'))
        separate_defaults_per_voice = settings.get('separate_defaults_per_voice', False)
        self.chkPerVoice.Value = separate_defaults_per_voice
        self.chkPerVoice.Bind(wx.EVT_CHECKBOX, self.OnToggleDefaultsPerVoice)
        midi_box = wx.GridBagSizer()
        midi_box.Add(wx.StaticText(self, wx.ID_ANY, _('Default instrument:')), pos=(0,1), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        midi_box.Add(wx.StaticText(self, wx.ID_ANY, _('Main Volume:')), pos=(0,3), span=(0,2), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        midi_box.Add(wx.StaticText(self, wx.ID_ANY, _('L/R Balance:')), pos=(0,6), span=(0,2), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)

        # For each of the 16th voice, instrument, volume and balance can be set separately
        instrument_choices = []  # instruments fill be filled when tab is selected to speed up ABC settings
        controls = []
        for channel in range(1, 16+1):
            cmbMidiProgram = wx.ComboBox(self, wx.ID_ANY, choices=instrument_choices, size=(200, 26),
                                                            style=wx.CB_READONLY)
            controls.append(cmbMidiProgram)
            self.cmbMidiProgramCh_list[channel] = cmbMidiProgram
            volumeSlider = wx.Slider(self, value=default_midi_volume, minValue=0, maxValue=127,
                                                                size=(80, -1), style=wx.SL_HORIZONTAL)
            # A text field is added to show value of slider as activating option SL_LABELS will show to many information
            self.sldMidiControlVolumeCh_list[channel] = volumeSlider
            controls.append(volumeSlider)

            volumeText = wx.StaticText(self, wx.ID_ANY, str(default_midi_volume), style=wx.ALIGN_RIGHT |
                                                                wx.ST_NO_AUTORESIZE, size=(30, 20))
            self.textValueMidiControlVolumeCh_list[channel] = volumeText

            panSlider = wx.Slider(self, value=default_midi_pan, minValue=0, maxValue=127,
                                                                size=(80, -1), style=wx.SL_HORIZONTAL)
            self.sldMidiControlPanCh_list[channel] = panSlider
            controls.append(panSlider)

            # A text field is added to show value of slider as activating option SL_LABELS will show to many information
            panText = wx.StaticText(self, wx.ID_ANY, str(default_midi_pan), style=wx.ALIGN_RIGHT |
                                                                wx.ST_NO_AUTORESIZE, size=(30, 20))
            self.textValueMidiControlPanCh_list[channel] = panText

            midi_box.Add(wx.StaticText(self, wx.ID_ANY, _('Voice n.%d: ') % channel), pos=(channel,0),
                         flag=wx.ALIGN_CENTER_VERTICAL, border=border)
            midi_box.Add(cmbMidiProgram, pos=(channel,1), flag=wx.ALIGN_CENTER_VERTICAL | wx.EXPAND)
            #3rd column (col=2) is unused on purpose to leave some space (maybe replaced with some other spacer option later on)
            midi_box.Add(volumeSlider, pos=(channel,3),
                         flag=wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_CENTER_HORIZONTAL)
            midi_box.Add(volumeText, pos=(channel,4),
                         flag=wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_CENTER_HORIZONTAL)
            #6th column (col=5) is unused on purpose to leave some space (maybe replaced with some other spacer option later on)
            midi_box.Add(panSlider, pos=(channel,6),
                         flag=wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_CENTER_HORIZONTAL)
            midi_box.Add(panText, pos=(channel,7),
                         flag=wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_CENTER_HORIZONTAL)
            #Some properties are added to the slider to be able to update the associated text field with value when slider is moved
            volumeSlider.currentchannel=channel
            volumeSlider.Bind(wx.EVT_SCROLL, self.OnVolumeSliderScroll)
            panSlider.currentchannel=channel
            panSlider.Bind(wx.EVT_SCROLL, self.OnPanSliderScroll)
            # Binding
            cmbMidiProgram.currentchannel=channel
            cmbMidiProgram.Bind(wx.EVT_COMBOBOX, self.OnProgramSelection)

        # reset buttons box
        self.reset = wx.Button(self, wx.ID_ANY, _('&Reset'))
        controls.append(self.reset)
        if WX4:
            btn_box = wx.BoxSizer()
            btn_box.Add(self.reset)
        else:
            btn_box = wx.BoxSizer(wx.HORIZONTAL)
            btn_box.Add(self.reset, flag=wx.ALIGN_RIGHT)

        if not separate_defaults_per_voice:
            for control in controls:
                control.Disable() # IsEnabled = separate_defaults_per_voice
        self.voices_controls = controls

        reset_toolTip = _('The instrument for all voices is set to the default midi program. The volume and pan are set to 96/64.')
        self.reset.SetToolTip(wx.ToolTip(reset_toolTip))
        self.reset.Bind(wx.EVT_BUTTON, self.OnResetDefault)

        # add all box to the dialog to be displayed
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.chkPerVoice, flag=wx.ALL, border=border)
        self.sizer.Add(midi_box, flag=wx.ALL | wx.ALIGN_CENTER, border=border)
        self.sizer.Add(btn_box, flag=wx.ALL | wx.ALIGN_RIGHT, border=border)

        self.SetSizer(self.sizer)

        # try to set selection on previously defined instrument or default one or Piano
        self.midi_program_ch_list = ['midi_program_ch%d' % ch for ch in range(1, 16 + 1)]

    def OnToggleDefaultsPerVoice(self, event):
        separate_defaults_per_voice = event.EventObject.GetValue()
        self.settings['separate_defaults_per_voice'] = separate_defaults_per_voice
        controls = self.voices_controls
        if separate_defaults_per_voice:
            self.FillControls()
            for control in controls:
                control.Enable()
        else:
            for control in controls:
                control.Disable()

    def FillControls(self):
        if self.controls_initialized or not self.settings.get('separate_defaults_per_voice', False):
            return

        instruments = general_midi_instruments
        for channel in range(1, 16+1):
            self.cmbMidiProgramCh_list[channel].Append(instruments)
            try:
                setting_name = self.midi_program_ch_list[channel-1]
                midi_info = self.settings.get(setting_name)
                if midi_info is None:
                    midi_info = [self.settings.get('midi_program', default_midi_instrument), default_midi_volume, default_midi_pan]
                self.cmbMidiProgramCh_list[channel].Select(midi_info[0])
                self.sldMidiControlVolumeCh_list[channel].SetValue(midi_info[1])
                self.textValueMidiControlVolumeCh_list[channel].SetLabel(str(midi_info[1]))
                self.sldMidiControlPanCh_list[channel].SetValue(midi_info[2])
                self.textValueMidiControlPanCh_list[channel].SetLabel(str(midi_info[2]))
            except:
                pass

        self.controls_initialized = True

    def OnProgramSelection(self, evt):
        obj = evt.GetEventObject()
        self.update_setting_for_channel(obj.currentchannel)

    def OnVolumeSliderScroll(self, evt):
        obj = evt.GetEventObject()
        val = obj.GetValue()
        channel = obj.currentchannel
        self.textValueMidiControlVolumeCh_list[channel].SetLabel("%d" % val)
        self.update_setting_for_channel(channel)

    def OnPanSliderScroll(self, evt):
        obj = evt.GetEventObject()
        val = obj.GetValue()
        channel = obj.currentchannel
        self.textValueMidiControlPanCh_list[channel].SetLabel("%d" % val)
        self.update_setting_for_channel(channel)

    def update_setting_for_channel(self, channel):
        self.settings[self.midi_program_ch_list[channel-1]] = [self.cmbMidiProgramCh_list[channel].GetSelection(),
                                                               self.sldMidiControlVolumeCh_list[channel].GetValue(),
                                                               self.sldMidiControlPanCh_list[channel].GetValue()]


    def OnResetDefault(self, evt):
        try:
            for channel in range(1, 16+1):
                self.cmbMidiProgramCh_list[channel].Select(self.settings.get('midi_program', default_midi_instrument))
                self.sldMidiControlVolumeCh_list[channel].SetValue(default_midi_volume)
                self.textValueMidiControlVolumeCh_list[channel].SetLabel(str(default_midi_volume))
                self.sldMidiControlPanCh_list[channel].SetValue(default_midi_pan)
                self.textValueMidiControlPanCh_list[channel].SetLabel(str(default_midi_pan))

                self.settings[self.midi_program_ch_list[channel-1]] = [self.cmbMidiProgramCh_list[channel].GetSelection(),
                                                                       self.sldMidiControlVolumeCh_list[channel].GetValue(),
                                                                       self.sldMidiControlPanCh_list[channel].GetValue()]
        except:
            pass


class MidiSettingsFrame(wx.Dialog):
    def __init__(self, parent, settings):
        wx.Dialog.__init__(self, parent, wx.ID_ANY, _('Midi device settings'), wx.DefaultPosition, wx.Size(130, 80))
        self.settings = settings
        border = control_margin
        sizer = wx.GridBagSizer(0, 0)
        sizer.Add(wx.StaticText(self, wx.ID_ANY, _('Input device')), wx.GBPosition(0, 0), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        sizer.Add(wx.StaticText(self, wx.ID_ANY, _('Output device')), wx.GBPosition(1, 0), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)

        inputDevices = [_('None')]
        inputDeviceIDs = [None]
        outputDevices = [_('None')]
        outputDeviceIDs = [None]
        if pypm is not None:
            if wx.Platform == "__WXMAC__":
                n = pypm.get_count()
            else:
                n = pypm.CountDevices()
        else:
            n = 0
        for i in range(n):
            if wx.Platform == "__WXMAC__":
                interface, name, input, output, opened = pypm.get_device_info(i)
                try:
                    name = str(name,'utf-8')
                except:
                    name = str(name,'mac_roman')
            else:
                interface, name, input, output, opened = pypm.GetDeviceInfo(i)
            if input:
                inputDevices.append(name)
                inputDeviceIDs.append(i)
            elif output:
                outputDevices.append(name)
                outputDeviceIDs.append(i)
        self.inputDeviceIDs = inputDeviceIDs
        self.outputDeviceIDs = outputDeviceIDs

        self.inputDevice = wx.ComboBox(self, wx.ID_ANY, size=(250, 22), choices=inputDevices, style=wx.CB_DROPDOWN | wx.CB_READONLY)
        self.outputDevice = wx.ComboBox(self, wx.ID_ANY, size=(250, 22), choices=outputDevices, style=wx.CB_DROPDOWN | wx.CB_READONLY)
        self.inputDevice.SetSelection(0)
        self.outputDevice.SetSelection(0)
        if settings.get('midi_device_in', None) in inputDeviceIDs:
            self.inputDevice.SetSelection(inputDeviceIDs.index(settings.get('midi_device_in', None)))
        if settings.get('midi_device_out', None) in outputDeviceIDs:
            self.outputDevice.SetSelection(outputDeviceIDs.index(settings.get('midi_device_out', None)))

        self.ok = wx.Button(self, wx.ID_ANY, _('&Ok'))
        self.cancel = wx.Button(self, wx.ID_ANY, _('&Cancel'))
        # 1.3.6.1 [JWdJ] 2015-01-30 Swapped next two lines so OK-button comes first (OK Cancel)
        if WX4:
            box = wx.BoxSizer()
            box.Add(self.ok, wx.ID_OK)
            box.Add(self.cancel, wx.ID_CANCEL)
        else:
            box = wx.BoxSizer(wx.HORIZONTAL)
            box.Add(self.ok, wx.ID_OK, flag=wx.ALIGN_RIGHT)
            box.Add(self.cancel, wx.ID_CANCEL, flag=wx.ALIGN_RIGHT)

        sizer.Add(self.inputDevice, wx.GBPosition(0, 1), flag=wx.EXPAND | wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        sizer.Add(self.outputDevice, wx.GBPosition(1, 1), flag=wx.EXPAND | wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        sizer.Add(box, wx.GBPosition(2, 0), (1, 2), flag=0 | wx.ALL | wx.ALIGN_RIGHT, border=border)
        self.ok.SetDefault()

        self.SetSizer(sizer)
        self.SetAutoLayout(True)
        self.Centre()
        sizer.Fit(self)

        self.ok.Bind(wx.EVT_BUTTON, self.OnOk)
        self.cancel.Bind(wx.EVT_BUTTON, self.OnCancel)

    def OnOk(self, evt):
        self.settings['midi_device_in'] = self.inputDeviceIDs[self.inputDevice.GetSelection()]
        self.settings['midi_device_out'] = self.outputDeviceIDs[self.outputDevice.GetSelection()]
        self.EndModal(wx.ID_OK)

    def OnCancel(self, evt):
        self.EndModal(wx.ID_CANCEL)


class MyAbcm2psPage(wx.Panel):
    # 1.3.6.1 [SS] 2015-02-02
    def __init__(self, parent, settings, abcsettingspage):
        wx.Panel.__init__(self, parent)
        self.settings = settings
        self.abcsettingspage = abcsettingspage
        border = control_margin
        headingtxt = _('The options in this page controls how the music score is displayed.\n\n')
        heading = wx.StaticText(self, wx.ID_ANY, headingtxt)

        clean      = wx.StaticText(self, wx.ID_ANY, _("No page settings"))
        defaults   = wx.StaticText(self, wx.ID_ANY, _("EasyABC defaults"))
        numberbars = wx.StaticText(self, wx.ID_ANY, _("Include bar numbers"))
        refnumbers = wx.StaticText(self, wx.ID_ANY, _("Add X reference number"))
        nolyrics   = wx.StaticText(self, wx.ID_ANY, _("Suppress lyrics"))
        linends    = wx.StaticText(self, wx.ID_ANY, _("Ignore line ends"))
        leftmarg   = wx.StaticText(self, wx.ID_ANY, _("Left margin (cm)"))
        rightmarg  = wx.StaticText(self, wx.ID_ANY, _("Right margin (cm)"))
        topmarg    = wx.StaticText(self, wx.ID_ANY, _("Top margin (cm)"))
        botmarg = wx.StaticText(self, wx.ID_ANY, _("Bottom margin (cm)"))
        # 1.3.6.1 [SS] 2015-01-28
        pagewidth = wx.StaticText(self, wx.ID_ANY, _("Page width (cm)"))
        pageheight = wx.StaticText(self, wx.ID_ANY, _("Page height (cm)"))

        scalefact  = wx.StaticText(self, wx.ID_ANY, _("Scale factor (eg. 0.8)"))
        self.chkm2psclean = wx.CheckBox(self, wx.ID_ANY, '')
        self.chkm2psdef   = wx.CheckBox(self, wx.ID_ANY, '')
        self.chkm2psbar = wx.CheckBox(self, wx.ID_ANY, '')
        self.chkm2psref = wx.CheckBox(self, wx.ID_ANY, '')
        self.chkm2pslyr = wx.CheckBox(self, wx.ID_ANY, '')
        self.chkm2psend = wx.CheckBox(self, wx.ID_ANY, '')

        extras = wx.StaticText(self, wx.ID_ANY, _("Extra parameters"))
        self.extras = wx.TextCtrl(self, wx.ID_ANY, size=(350, 22))
        formatf = wx.StaticText(self, wx.ID_ANY, _("Format file"))
        # 1.3.6.4 [SS] 2015-09-11 2015-09-21
        try:
            self.format_choices = self.settings.get('abcm2ps_format_choices', '').split('|')
        except:
            self.format_choices = []
        # 1.3.6.4 [SS] 2015-09-11
        self.formatf  = wx.ComboBox(self, wx.ID_ANY, choices=self.format_choices, size = (350, -1), style=wx.CB_DROPDOWN)

        self.browsef = wx.Button(self, wx.ID_ANY, _('Browse...'), size = (-1, 22))

        self.leftmargin  = wx.TextCtrl(self, wx.ID_ANY, size=(55, 22))
        self.rightmargin = wx.TextCtrl(self, wx.ID_ANY, size=(55, 22))
        self.topmargin = wx.TextCtrl(self, wx.ID_ANY, size=(55, 22))
        self.botmargin = wx.TextCtrl(self, wx.ID_ANY, size=(55, 22))
        self.pagewidth = wx.TextCtrl(self, wx.ID_ANY, size=(55, 22))
        self.pageheight =wx.TextCtrl(self, wx.ID_ANY, size=(55, 22))

        # 1.3.6.1 [SS] 2015-12-28
        pagewidth_toolTip = _('The default is {0}').format('21.59')
        pageheight_toolTip = _('The default is {0}').format('27.94')
        leftmargin_toolTip = _('The default is {0}').format('1.78')
        rightmargin_toolTip = _('The default is {0}').format('1.78')
        topmargin_toolTip = _('The default is {0}').format('1.00')
        botmargin_toolTip = _('The default is {0}').format('1.00')
        extras_toolTip = _('Additional command line parameters to abcm2ps')
        formatf_toolTip = _('Right click the mouse to remove all choices')
        self.pagewidth.SetToolTip(wx.ToolTip(pagewidth_toolTip))
        self.pageheight.SetToolTip(wx.ToolTip(pageheight_toolTip))
        self.leftmargin.SetToolTip(wx.ToolTip(leftmargin_toolTip))
        self.rightmargin.SetToolTip(wx.ToolTip(rightmargin_toolTip))
        self.topmargin.SetToolTip(wx.ToolTip(topmargin_toolTip))
        self.botmargin.SetToolTip(wx.ToolTip(botmargin_toolTip))
        self.extras.SetToolTip(wx.ToolTip(extras_toolTip))
        self.formatf.SetToolTip(wx.ToolTip(formatf_toolTip))

        chkm2psdef_toolTip = _('Use the factory page settings of EasyABC')
        self.chkm2psdef.SetToolTip(wx.ToolTip(chkm2psdef_toolTip))
        chkm2psclean_toolTip = _('Do not add page settings')
        self.chkm2psclean.SetToolTip(wx.ToolTip(chkm2psclean_toolTip))

        self.chkm2psclean.SetValue(self.settings.get('abcm2ps_clean', False))
        self.chkm2psdef.SetValue(self.settings.get('abcm2ps_defaults'))
        self.chkm2psbar.SetValue(self.settings.get('abcm2ps_number_bars', False))
        self.chkm2psref.SetValue(self.settings.get('abcm2ps_refnumbers', False))
        self.chkm2pslyr.SetValue(self.settings.get('abcm2ps_no_lyrics', False))
        self.chkm2psend.SetValue(self.settings.get('abcm2ps_ignore_ends', False))
        self.leftmargin.SetValue(self.settings.get('abcm2ps_leftmargin', '1.78'))
        self.rightmargin.SetValue(self.settings.get('abcm2ps_rightmargin', '1.78'))
        self.topmargin.SetValue(self.settings.get('abcm2ps_topmargin', '1.0'))
        self.botmargin.SetValue(self.settings.get('abcm2ps_botmargin', '1.0'))
        # 1.3.6.1 [SS] 2015-01-28
        self.pagewidth.SetValue(self.settings.get('abcm2ps_pagewidth', '21.59'))
        self.pageheight.SetValue(self.settings.get('abcm2ps_pageheight', 27.94))
        self.extras.SetValue(self.settings.get('abcm2ps_extra_params', ''))
        self.formatf.SetValue(self.settings.get('abcm2ps_format_path', ''))

        self.chkm2psclean.Bind(wx.EVT_CHECKBOX, self.OnAbcm2psClean)
        self.chkm2psdef.Bind(wx.EVT_CHECKBOX, self.OnAbcm2psDefaults)
        self.chkm2psbar.Bind(wx.EVT_CHECKBOX, self.OnAbcm2psBar)
        self.chkm2pslyr.Bind(wx.EVT_CHECKBOX, self.OnAbcm2pslyrics)
        self.chkm2psref.Bind(wx.EVT_CHECKBOX, self.OnAbcm2psref)
        self.chkm2psend.Bind(wx.EVT_CHECKBOX, self.OnAbcm2psend)
        self.leftmargin.Bind(wx.EVT_TEXT, self.OnPSleftmarg, self.leftmargin)
        self.rightmargin.Bind(wx.EVT_TEXT, self.OnPSrightmarg, self.rightmargin)
        self.topmargin.Bind(wx.EVT_TEXT, self.OnPStopmarg, self.topmargin)
        self.botmargin.Bind(wx.EVT_TEXT, self.OnPSbotmarg, self.botmargin)
        # 1.3.6.1 [SS] 2015-01-28
        self.formatf.Bind(wx.EVT_TEXT, self.OnFormat, self.formatf)
        self.formatf.Bind(wx.EVT_RIGHT_DOWN, self.OnClean, self.formatf) #1.3.6.4
        self.extras.Bind(wx.EVT_TEXT, self.On_extra_params, self.extras)
        self.browsef.Bind(wx.EVT_BUTTON, self.OnBrowse_format, self.browsef)
        # 1.3.6.1 [SS] 2015-01-29
        self.pagewidth.Bind(wx.EVT_TEXT, self.OnPSpagewidth, self.pagewidth)
        self.pageheight.Bind(wx.EVT_TEXT, self.OnPSpageheight, self.pageheight)

        # 1.3.6 [SS] 2014-12-16
        # 1.3.6.3 [SS] 2015-03-15
        #fval = self.settings.get('abcm2ps_scale',0.9)
        self.scaleval = wx.TextCtrl(self, wx.ID_ANY, size=(50,22))
        self.scaleval.SetValue(self.settings.get('abcm2ps_scale',0.9))
        self.scaleval.SetToolTip(wx.ToolTip(_('Scales the separation between staff lines. Recommended value is {0}.'.format('0.80'))))

        # 1.3.6.2 [SS] 2015-04-21
        self.scaleval.Bind(wx.EVT_TEXT, self.OnPSScale, self.scaleval)

        grid_sizer = wx.GridBagSizer()
        grid_sizer.Add(heading, pos=(0,0), span=(1,7), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)

        grid_sizer.Add(clean, pos=(1,0), span=(1,2), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border )
        grid_sizer.Add(self.chkm2psclean, pos=(1,2), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border )

        grid_sizer.Add(defaults, pos=(1,4), span=(1,2), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border )
        grid_sizer.Add(self.chkm2psdef, pos=(1,6), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border )

        grid_sizer.Add(numberbars, pos=(3,0), span=(1,2), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border )
        grid_sizer.Add(self.chkm2psbar, pos=(3,2), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border )

        grid_sizer.Add(refnumbers, pos=(3,4), span=(1,2), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border )
        grid_sizer.Add(self.chkm2psref, pos=(3,6), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border )

        grid_sizer.Add(nolyrics, pos=(4,0), span=(1,2), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border )
        grid_sizer.Add(self.chkm2pslyr, pos=(4,2), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border )

        grid_sizer.Add(linends, pos=(4,4), span=(1,2), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border )
        grid_sizer.Add(self.chkm2psend, pos=(4,6), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border )

        self.grid_sizer_page_format = wx.GridBagSizer()
        self.grid_sizer_page_format.Add(leftmarg, pos=(0,0), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border )
        self.grid_sizer_page_format.Add(self.leftmargin, pos=(0,1), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border )

        self.grid_sizer_page_format.Add(rightmarg, pos=(0,3), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border )
        self.grid_sizer_page_format.Add(self.rightmargin, pos=(0,4), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border )

        self.grid_sizer_page_format.Add(topmarg, pos=(1,0), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border )
        self.grid_sizer_page_format.Add(self.topmargin, pos=(1,1), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border )

        self.grid_sizer_page_format.Add(botmarg, pos=(1,3), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border )
        self.grid_sizer_page_format.Add(self.botmargin, pos=(1,4), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border )

        self.grid_sizer_page_format.Add(pagewidth, pos=(2,0), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border )
        self.grid_sizer_page_format.Add(self.pagewidth, pos=(2,1), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border )

        self.grid_sizer_page_format.Add(pageheight, pos=(2,3), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border )
        self.grid_sizer_page_format.Add(self.pageheight, pos=(2,4), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border )

        self.grid_sizer_page_format.Add(scalefact, pos=(3,0), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border )
        self.grid_sizer_page_format.Add(self.scaleval, pos=(3,1), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border )

        grid_sizer.Add(self.grid_sizer_page_format, pos=(2,1), span=(1,6), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border )

        grid_sizer.Add(extras, pos=(5,0), span=(1,2), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border )
        grid_sizer.Add(self.extras, pos=(5,2), span=(1,5), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border )
        grid_sizer.Add(formatf, pos=(6,0), span=(1,2), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border )
        grid_sizer.Add(self.formatf, pos=(6,2), span=(1,3), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border )
        grid_sizer.Add(self.browsef, pos=(6,5), span=(1,2), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border )


        # 1.3.6.1 [SS] 2015-01-08
        if self.settings['abcm2ps_clean'] or self.settings['abcm2ps_defaults']:
            for sizeritem in self.grid_sizer_page_format.GetChildren():
                sizeritem.Show(False)
        else:
            for sizeritem in self.grid_sizer_page_format.GetChildren():
                sizeritem.Show(True)
        self.SetSizer(grid_sizer)
        self.SetAutoLayout(True)
        self.Fit()
        self.Layout()

    def OnAbcm2psClean(self, evt):
        self.settings['abcm2ps_clean'] = self.chkm2psclean.GetValue()
        if self.settings['abcm2ps_clean'] or self.settings['abcm2ps_defaults']:
        #    #self.box.Show(self.gridsizer3, show=False)
            for sizeritem in self.grid_sizer_page_format.GetChildren():
                sizeritem.Show(False)
        else:
            #self.box.Show(self.gridsizer3, show=True)
            for sizeritem in self.grid_sizer_page_format.GetChildren():
                sizeritem.Show(True)
        self.Layout()

    def OnAbcm2psDefaults(self, evt):
        self.settings['abcm2ps_defaults'] = self.chkm2psdef.GetValue()
        if self.settings['abcm2ps_clean'] or self.settings['abcm2ps_defaults']:
        #    self.box.Show(self.gridsizer3, show=False)
            for sizeritem in self.grid_sizer_page_format.GetChildren():
                sizeritem.Show(False)
        else:
        #    self.box.Show(self.gridsizer3, show=True)
            for sizeritem in self.grid_sizer_page_format.GetChildren():
                sizeritem.Show(True)
        self.Layout()

    def OnAbcm2psBar(self, evt):
        self.settings['abcm2ps_number_bars'] = self.chkm2psbar.GetValue()

    def OnAbcm2pslyrics(self, evt):
        self.settings['abcm2ps_no_lyrics'] = self.chkm2pslyr.GetValue()

    def OnAbcm2psref(self, evt):
        self.settings['abcm2ps_refnumbers'] = self.chkm2psref.GetValue()

    def OnAbcm2psend(self, evt):
        self.settings['abcm2ps_ignore_ends'] = self.chkm2psend.GetValue()

    # 1.3.6.2 [SS] 2015-03-15
    def OnPSScale(self, evt):
        val = self.scaleval.GetValue()
        m   = re.findall(r"\d+.\d+|\d+",val)
        if len(m) > 0 and 0.1 < float(val) < 1.5:
            self.settings['abcm2ps_scale'] = str(val)

    def OnPSleftmarg(self, evt):
        # 1.3.6.1 [SS] 2015-01-13
        val = self.leftmargin.GetValue()
        # extract only the number
        m   = re.findall(r"\d+.\d+|\d+",val)
        if len(m) > 0:
            val = str(m[0])
            self.settings['abcm2ps_leftmargin'] = val

    def OnPSrightmarg(self, evt):
        # 1.3.6.1 [SS] 2015-01-13
        val = self.rightmargin.GetValue()
        m   = re.findall(r"\d+.\d+|\d+",val)
        if len(m) > 0:
            val = str(m[0])
            self.settings['abcm2ps_rightmargin'] = val

    def OnPStopmarg(self, evt):
        # 1.3.6.1 [SS] 2015-01-13
        val = self.topmargin.GetValue()
        m   = re.findall(r"\d+.\d+|\d+",val)
        if len(m) > 0:
            val = str(m[0])
            self.settings['abcm2ps_topmargin'] = val

    def OnPSbotmarg(self, evt):
        # 1.3.6.1 [SS] 2015-01-13
        val = self.botmargin.GetValue()
        m   = re.findall(r"\d+.\d+|\d+",val)
        if len(m) > 0:
            val = str(m[0])
            self.settings['abcm2ps_botmargin'] = val

    # 1.3.6.1 [SS] 2015-01-28
    def OnPSpagewidth(self, evt):
        val = self.pagewidth.GetValue()
        m   = re.findall(r"\d+.\d+|\d+",val)
        if len(m) > 0:
            val = str(m[0])
            self.settings['abcm2ps_pagewidth'] = val

    def OnPSpageheight(self, evt):
        val = self.pageheight.GetValue()
        m   = re.findall(r"\d+.\d+|\d+",val)
        if len(m) > 0:
            val = str(m[0])
            self.settings['abcm2ps_pageheight'] = val

    def OnFormat(self, evt):
        path = evt.String
        self.set_format_path(path)
        # 1.3.6.4 [SS] 2015-09-11
        self.update_format_choices(path)
        # [SS] the SetItems does not work correctly in wxpython 2.7
        #self.formatf.SetItems(str(self.settings['abcm2ps_format_choices']))

    # 1.3.6.4 [SS] 2015-09-21
    def OnClean(self, evt):
        #print "right click"
        #if evt.ControlDown():
            #print "control down"
        result = wx.MessageBox(_("This will remove the selections in the combobox."), _("Proceed?"), wx.ICON_QUESTION | wx.YES | wx.NO)
        #print self.formatf.GetItems()
        if result == wx.YES:
            #self.formatf.Clear()
            self.formatf.SetItems([])
            self.settings['abcm2ps_format_choices'] = self.formatf.GetItems()


    def On_extra_params(self, evt):
        self.settings['abcm2ps_extra_params'] = self.extras.GetValue()

    def OnBrowse_format(self, evt):
        path = self.settings.get('abcm2ps_format_path', '')
        if not path:
            path = self.settings.get('previous_abcm2ps_format_path', '')
        default_dir, default_file = os.path.split(path)
        dlg = wx.FileDialog(
                self, message=_("Find PostScript format file"), defaultFile=default_file, defaultDir=default_dir, style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_CHANGE_DIR )
        try:
            if dlg.ShowModal() == wx.ID_OK:
                path = dlg.GetPath()
                self.formatf.SetValue(path)
                self.update_format_choices(path)
        finally:
            dlg.Destroy() # 1.3.6.3 [JWDJ] 2015-04-21 always clean up dialog window

    def update_format_choices(self, path):
        # 1.3.6.4 [SS] 2015-09-11
        if path and not path in self.format_choices and os.path.isfile(path) and os.access(path, os.R_OK):
            self.format_choices.append(path)
            self.settings['abcm2ps_format_choices'] = '|'.join(self.format_choices)
            if wx.Platform != "__WXMSW__":
                self.set_format_path(path)  # 1.3.6.4 [SS] 2015-09-17 in case control.SetValue(path) does not trigger OnChangePath

    def set_format_path(self, path):
        old_path = self.settings.get('abcm2ps_format_path', '')
        if old_path and path != old_path:
            self.settings['previous_abcm2ps_format_path'] = old_path
        self.settings['abcm2ps_format_path'] = path
        self.Parent.Parent.Parent.Parent.refresh_tunes()


class ColorSettingsFrame(wx.Panel):
    def __init__(self, parent, settings):
        wx.Panel.__init__(self, parent)
        self.settings = settings
        border = control_margin

        grid_sizer = wx.GridBagSizer()

        notecolors    = wx.StaticText(self, wx.ID_ANY, _('Colors for note highlighting in music score'))
        editorcolors  = wx.StaticText(self, wx.ID_ANY, _('Colors of ABC code highlighting in editor'))

        note_highlight_color = self.settings.get('note_highlight_color', default_note_highlight_color)
        note_highlight_color_label = wx.StaticText(self, wx.ID_ANY, _("Note highlight color"))
        self.note_highlight_color_picker = wx.ColourPickerCtrl(self, wx.ID_ANY, colour=wx.Colour(note_highlight_color))

        note_highlight_follow_color = self.settings.get('note_highlight_follow_color', default_note_highlight_follow_color)
        note_highlight_follow_color_label = wx.StaticText(self, wx.ID_ANY, _("Note highlight color when follow score"))
        self.note_highlight_follow_color_picker = wx.ColourPickerCtrl(self, wx.ID_ANY, colour=wx.Colour(note_highlight_follow_color))

        appearance = current_appearance()
        score_paper_label = wx.StaticText(self, wx.ID_ANY, _("Paper color of music score"))
        self.score_paper_picker = wx.ColourPickerCtrl(self, wx.ID_ANY, colour=wx.Colour(appearance.style_color(self.settings, 'score_paper')))

        grid_sizer.Add(notecolors,pos=(0,0),span=(1,10), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)

        grid_sizer.Add(note_highlight_color_label, pos=(1,1), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        grid_sizer.Add(self.note_highlight_color_picker, pos=(1,2), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        grid_sizer.Add(note_highlight_follow_color_label, pos=(1,4), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        grid_sizer.Add(self.note_highlight_follow_color_picker, pos=(1,5), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        grid_sizer.Add(score_paper_label, pos=(1,7), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        grid_sizer.Add(self.score_paper_picker, pos=(1,8), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        self.score_paper_picker.SetToolTip(wx.ToolTip(_('Background color of the music score on screen; printing and export stay on white paper')))
        self.score_paper_picker.Bind(wx.EVT_COLOURPICKER_CHANGED, self.OnScorePaperChanged)

        note_highlight_color_tooltip = _('Color of selected note')
        self.note_highlight_color_picker.SetToolTip(wx.ToolTip(note_highlight_color_tooltip))
        self.note_highlight_color_picker.Bind(wx.EVT_COLOURPICKER_CHANGED, self.OnNoteHighlightColorChanged)
        note_highlight_follow_color_tooltip = _('Color of currently playing note')
        self.note_highlight_follow_color_picker.SetToolTip(wx.ToolTip(note_highlight_follow_color_tooltip))
        self.note_highlight_follow_color_picker.Bind(wx.EVT_COLOURPICKER_CHANGED, self.OnNoteHighlightFollowColorChanged)

        self.style_labels = {
            'style_default_color':_("Default color"),
            'style_chord_color':_("Color of chords"),
            'style_bar_color':_("Color of bars"),
            'style_comment_color':_("Color of comment"),
            'style_specialcomment_color':_("Color of instructions/commands"),
            'style_fieldindex_color':_("Color of field index"),
            'style_field_color':_("Color of ABC fields"),
            'style_fieldvalue_color':_("Color of ABC fields value"),
            'style_embeddedfield_color':_("Color of embedded ABC fields"),
            'style_embeddedfieldvalue_color':_("Color of embedded ABC fields values"),
            'style_string_color':_("Color of string"),
            'style_lyrics_color':_("Color of lyrics"),
            'style_ornament_color':_("Color of ornament"),
            'style_ornamentplus_color':_("Color of ornament plus"),
            'style_ornamentexcl_color':_("Color of ornament excl"),
            'style_error_color':_("Color of errors"),
            'style_warning_color':_("Color of warnings"),
            'style_grace_color':_("Color of grace notes"),
            'style_selection_color':_("Color of selection"),
        }

        grid_sizer.Add(editorcolors,pos=(3,0),span=(1,10), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        i=4
        j=1
        self.color_picker = {}
        for key, label in self.style_labels.items():
            color = appearance.style_color(self.settings, key)
            color_text_label = wx.StaticText(self, wx.ID_ANY, label)
            self.color_picker[key] = wx.ColourPickerCtrl(self, wx.ID_ANY, colour=wx.Colour(color))
            grid_sizer.Add(color_text_label, pos=(i,j), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
            grid_sizer.Add(self.color_picker[key], pos=(i,j+1), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
            self.color_picker[key].Bind(wx.EVT_COLOURPICKER_CHANGED, lambda evt, temp=key: self.OnFontColorChanged(evt,temp))
            if j>=7:
                i+=1
                j=1
            else:
                j+=3

        self.restore_color = wx.Button(self, wx.ID_ANY, _('Restore default colors'))
        check_toolTip = _('Restore default colors')
        self.restore_color.SetToolTip(wx.ToolTip(check_toolTip))

        grid_sizer.Add(self.restore_color, pos=(i+1,7), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        self.restore_color.Bind(wx.EVT_BUTTON, self.OnRestoreDefaultColors, self.restore_color)

        self.SetSizer(grid_sizer)
        self.SetAutoLayout(True)
        self.Fit()
        self.Layout()

    @property
    def main_frame(self):
        return self.Parent.Parent.Parent.Parent

    @staticmethod
    def picked_color(picker):
        return picker.GetColour().GetAsString(flags=wx.C2S_HTML_SYNTAX)

    def OnNoteHighlightColorChanged(self, evt):
        color = self.picked_color(self.note_highlight_color_picker)
        self.settings['note_highlight_color'] = color
        self.main_frame.renderer.highlight_color = color

    def OnNoteHighlightFollowColorChanged(self, evt):
        color = self.picked_color(self.note_highlight_follow_color_picker)
        self.settings['note_highlight_follow_color'] = color
        self.main_frame.renderer.highlight_follow_color = color

    def UpdateEditor(self):
        self.main_frame.InitEditorFromSettings()

    def store_style_color(self, palette_key, color):
        self.settings[current_appearance().style_settings_key(palette_key)] = color

    def OnFontColorChanged(self, evt, palette_key):
        self.store_style_color(palette_key, self.picked_color(self.color_picker[palette_key]))
        self.UpdateEditor()

    def OnScorePaperChanged(self, evt):
        self.store_style_color('score_paper', self.picked_color(self.score_paper_picker))
        self.main_frame.ApplyScorePaper()

    def OnRestoreDefaultColors(self, evt):
        self.settings['note_highlight_color'] = default_note_highlight_color
        self.note_highlight_color_picker.SetColour(default_note_highlight_color)
        self.settings['note_highlight_follow_color'] = default_note_highlight_follow_color
        self.note_highlight_follow_color_picker.SetColour(default_note_highlight_follow_color)
        appearance = current_appearance()
        for key, color in appearance.style_palette.items():
            self.store_style_color(key, color)
            if key in self.color_picker:
                self.color_picker[key].SetColour(color)
        self.score_paper_picker.SetColour(appearance.style_palette['score_paper'])
        self.UpdateEditor()
        self.main_frame.ApplyScorePaper()


class MusicXmlPage(wx.Panel):
    def __init__(self, parent, settings):
        wx.Panel.__init__(self,parent)
        self.settings = settings
        border = control_margin

        #headingtxt = _("The settings on this page control behaviour of the functions abc2xml and xml2abc.\nYou find these functions under Files/export and import. Hovering the mouse over\none of the checkboxes will provide more explanation. Further documentation can be found\nin the Readme.txt files which come with the abc2xml.py-??.zip and xml2abc.py-??.zip\ndistributions available from the Wim Vree's web site.\n\n")
        headingtxt = _("The settings on this page control behaviour of the functions abc2xml and xml2abc.\n\nYou find these functions under Files/export and import. Hovering the mouse over one of the checkboxes will provide more explanation.\nFurther documentation can be found from the Wim Vree's web site.\n")

        heading    = wx.StaticText(self, wx.ID_ANY, headingtxt)
        abc2xml    = wx.StaticText(self, wx.ID_ANY, _("abc2xml options"))
        compressed = wx.StaticText(self, wx.ID_ANY, _('Compressed xml'))
        xml2abc    = wx.StaticText(self, wx.ID_ANY, _('xml2abc option'))
        unfold     = wx.StaticText(self, wx.ID_ANY, _('Unfold Repeats'))
        mididata   = wx.StaticText(self, wx.ID_ANY, _('Midi Data'))
        volta      = wx.StaticText(self, wx.ID_ANY, _('Volta type setting'))
        numchar    = wx.StaticText(self, wx.ID_ANY, _('characters/line'))
        numbars    = wx.StaticText(self, wx.ID_ANY, _('bars per line'))
        credit     = wx.StaticText(self, wx.ID_ANY, _('credit filter'))
        ulength    = wx.StaticText(self, wx.ID_ANY, _('unit length'))
        xmlpage    = wx.StaticText(self, wx.ID_ANY, _('Page settings'))

        self.chkXmlCompressed = wx.CheckBox(self, wx.ID_ANY, '')
        self.chkXmlUnfold = wx.CheckBox(self, wx.ID_ANY, '')
        self.chkXmlMidi = wx.CheckBox(self, wx.ID_ANY, '')
        self.voltaval = wx.TextCtrl(self, wx.ID_ANY, size=(55, 22))
        self.maxchars = wx.TextCtrl(self, wx.ID_ANY, size=(55, 22))
        self.maxbars  = wx.TextCtrl(self, wx.ID_ANY, size=(55, 22))
        self.creditval = wx.TextCtrl(self, wx.ID_ANY, size=(55, 22))
        self.unitval  = wx.TextCtrl(self, wx.ID_ANY, size=(55, 22))
        self.XmlPage = wx.TextCtrl(self, wx.ID_ANY, size=(55, 22))
        #FAU Todo: expand option list to latest xml2abc capabilities

        self.chkXmlCompressed.SetValue(self.settings.get('xmlcompressed',False))
        self.chkXmlUnfold.SetValue(self.settings.get('xmlunfold',False))
        self.chkXmlMidi.SetValue(self.settings.get('xmlmidi',False))
        self.voltaval.SetValue(str(self.settings.get('xml_v')))
        self.maxbars.SetValue(self.settings.get('xml_b'))
        self.maxchars.SetValue(self.settings.get('xml_n'))
        self.creditval.SetValue(self.settings.get('xml_c'))
        self.unitval.SetValue(str(self.settings.get('xml_d')))
        self.XmlPage.SetValue(self.settings.get('xml_p'))

        # 1.3.6 [SS] 2014-12-19
        XmlCompressed_toolTip = _('When checked, abc2xml produces compressed xml files with extension mxl.')
        self.chkXmlCompressed.SetToolTip(wx.ToolTip(XmlCompressed_toolTip))
        XmlUnfold_toolTip = _('When checked, xml2abc turns off repeat translation and instead unfolds simple repeats.')
        self.chkXmlUnfold.SetToolTip(wx.ToolTip(XmlUnfold_toolTip))
        XmlMidi_toolTip = _('When checked, xml2abc outputs commands for midi volume and panning and the channel number. These commands are output in addition to the midi program number when it is present in the xml file.')
        self.chkXmlMidi.SetToolTip(wx.ToolTip(XmlMidi_toolTip))
        XmlPage_toolTip = _('The page format includes 6 numbers, eg. 0.7,25,15,1.2,1.2,1.2,1.2 which sets the scale to 0.7, the page height to 25 cm, the page width to 15 cm, and left, right, top and bottom margins to 1.2 cm. If the page format is blank, default values are assumed.')
        self.XmlPage.SetToolTip(wx.ToolTip(XmlPage_toolTip))
        maxchars_toolTip = _('Unless CPL is 0, it sets the maximum length for ABC output to CPL characters. The default is 100 characters. An integer number of bars, at least one, is always output.')
        self.maxchars.SetToolTip(wx.ToolTip(maxchars_toolTip))
        maxbars_toolTip = _('When not zero, BPL sets the number of bars per line. If both CPL and BPL is given, only CPL is used.')
        self.maxbars.SetToolTip(wx.ToolTip(maxbars_toolTip))
        creditval_toolTip = _('This filter tries to eliminate redundant T: fields. A higher level (up to 6) does less filtering. The default is 0 which filters as much as possible.')
        self.creditval.SetToolTip(wx.ToolTip(creditval_toolTip))
        unitval_toolTip = _('Unless D is 0, it sets the unit length for the output to abc field command L: 1/D. This overrides the computation of the optimal unit length.')
        self.unitval.SetToolTip(wx.ToolTip(unitval_toolTip))
        voltaval_toolTip = _("The default (V=0) translates volta brackets in all voices. V=1 prevents abcm2ps to write volta brackets on all but the first voice. (A %%repbra 0 command is added to each voice that hides its volta's.) When V=2 abcm2ps only typesets volta brackets on the first voice of each xml-part. When V=3 the volta brackets are only translated for the first abc voice, which has the same effect on the output of abcm2ps as V=1, but the abc code is not suited for abc2midi.")
        self.voltaval.SetToolTip(wx.ToolTip(voltaval_toolTip))

        # 1.3.6 [SS] 2014-12-20
        self.chkXmlCompressed.Bind(wx.EVT_CHECKBOX, self.OnXmlCompressed)
        self.chkXmlUnfold.Bind(wx.EVT_CHECKBOX, self.OnXmlUnfold)
        self.chkXmlMidi.Bind(wx.EVT_CHECKBOX, self.OnXmlMidi)
        self.voltaval.Bind(wx.EVT_TEXT, self.OnVolta)
        self.maxbars.Bind(wx.EVT_TEXT, self.OnMaxbars)
        self.maxchars.Bind(wx.EVT_TEXT, self.OnMaxchars)
        self.creditval.Bind(wx.EVT_TEXT, self.OnCreditval)
        self.unitval.Bind(wx.EVT_TEXT, self.OnUnitval)
        self.XmlPage.Bind(wx.EVT_TEXT, self.OnXmlPage)

        grid_sizer = wx.GridBagSizer()
        grid_sizer_abc2xml = wx.GridBagSizer()
        grid_sizer_xml2abc = wx.GridBagSizer()

        flags=wx.BOTTOM | wx.RIGHT | wx.ALIGN_CENTER_VERTICAL

        grid_sizer.Add(heading, pos=(0,0), span=(1,4), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)

        grid_sizer_abc2xml.Add(abc2xml, pos=(0,0), span=(1,3), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        grid_sizer_abc2xml.Add(compressed, pos=(1,1), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        grid_sizer_abc2xml.Add(self.chkXmlCompressed, pos=(1,2), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)

        grid_sizer_xml2abc.Add(xml2abc, pos=(0,0), span=(1,3), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)

        grid_sizer_xml2abc.Add(unfold, pos=(1,1), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        grid_sizer_xml2abc.Add(self.chkXmlUnfold, pos=(1,2), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)

        grid_sizer_xml2abc.Add(mididata, pos=(2,1), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        grid_sizer_xml2abc.Add(self.chkXmlMidi, pos=(2,2), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)

        grid_sizer_xml2abc.Add(volta, pos=(3,1), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        grid_sizer_xml2abc.Add(self.voltaval, pos=(3,2), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)

        grid_sizer_xml2abc.Add(numchar, pos=(4,1), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        grid_sizer_xml2abc.Add(self.maxchars, pos=(4,2), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)

        grid_sizer_xml2abc.Add(numbars, pos=(5,1), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        grid_sizer_xml2abc.Add(self.maxbars, pos=(5,2), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)

        grid_sizer_xml2abc.Add(credit, pos=(6,1), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        grid_sizer_xml2abc.Add(self.creditval, pos=(6,2), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)

        grid_sizer_xml2abc.Add(ulength, pos=(7,1), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        grid_sizer_xml2abc.Add(self.unitval, pos=(7,2), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)

        grid_sizer_xml2abc.Add(xmlpage, pos=(8,1), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        grid_sizer_xml2abc.Add(self.XmlPage, pos=(8,2), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)

        grid_sizer.Add(grid_sizer_abc2xml, pos=(1,0), flag=wx.ALL | wx.ALIGN_TOP, border=border)
        grid_sizer.Add(50, 40, pos=(1,1))
        grid_sizer.Add(grid_sizer_xml2abc, pos=(1,2), flag=wx.ALL | wx.ALIGN_TOP, border=border)

        self.SetSizer(grid_sizer)
        self.SetAutoLayout(True)
        self.Fit()
        self.Layout()

    def OnXmlCompressed(self, evt):
        self.settings['xmlcompressed'] = self.chkXmlCompressed.GetValue()

    def OnXmlUnfold(self, evt):
        self.settings['xmlunfold'] = self.chkXmlUnfold.GetValue()

    def OnXmlMidi(self, evt):
        self.settings['xmlmidi'] = self.chkXmlMidi.GetValue()

    def OnVolta(self, evt):
        self.settings['xml_v'] = self.voltaval.GetValue()

    def OnMaxbars(self, evt):
        self.settings['xml_b'] = self.maxbars.GetValue()

    def OnMaxchars(self, evt):
        self.settings['xml_n'] = self.maxchars.GetValue()

    def OnCreditval(self, evt):
        self.settings['xml_c'] = self.creditval.GetValue()

    def OnUnitval(self, evt):
        self.settings['xml_d'] = self.unitval.GetValue()

    def OnXmlPage(self, evt):
        self.settings['xml_p'] = self.XmlPage.GetValue()


class MidiOptionsFrame(wx.Dialog):
    def __init__(self, parent, ID=-1, title='', key='', metre='3/4', default_len='1/16'):
        wx.Dialog.__init__(self, parent, ID, _('ABC Options'), wx.DefaultPosition, wx.Size(300, 80))

        border = control_margin
        sizer = wx.GridBagSizer(control_margin, control_margin)
        sizer.Add(wx.StaticText(self, wx.ID_ANY, u'K: ' + _('Key signature')), wx.GBPosition(0, 0), flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=border)
        sizer.Add(wx.StaticText(self, wx.ID_ANY, u'M: ' + _('Metre')), wx.GBPosition(1, 0), flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=border)
        sizer.Add(wx.StaticText(self, wx.ID_ANY, u'L: ' + _('Default note length')), wx.GBPosition(2, 0), flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=border)
        sizer.Add(wx.StaticText(self, wx.ID_ANY, u'T: ' + _('Title')), wx.GBPosition(3, 0), flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=border)
        sizer.Add(wx.StaticText(self, wx.ID_ANY, _('Bars per line')), wx.GBPosition(4, 0), flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=border)
        sizer.Add(wx.StaticText(self, wx.ID_ANY, _('Numbers of notes in anacrusis')), wx.GBPosition(5, 0), flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=border)

        self.key = wx.TextCtrl(self, wx.ID_ANY, size=(150, 22))
        self.metre = wx.TextCtrl(self, wx.ID_ANY, size=(150, 22))
        self.default_len = wx.TextCtrl(self, wx.ID_ANY, size=(150, 22))
        self.title = wx.TextCtrl(self, wx.ID_ANY, size=(150, 22))
        self.bpl = wx.TextCtrl(self, wx.ID_ANY, size=(150, 22))
        self.num_notes_in_anacrusis = wx.TextCtrl(self, wx.ID_ANY, size=(150, 22))
        self.triplet_detection = wx.CheckBox(self, wx.ID_ANY, _('Detect triplets'))
        self.broken_rythm_detection = wx.CheckBox(self, wx.ID_ANY, _('Detect broken rythms'))
        self.slur_triplets = wx.CheckBox(self, wx.ID_ANY, _('Use slurs on triplets'))
        self.slur_8ths = wx.CheckBox(self, wx.ID_ANY, _('Use slurs on eights (useful for some waltzes)'))
        self.slur_16ths = wx.CheckBox(self, wx.ID_ANY, _('Use slurs on first pair of sixteenth (useful for some 16th polskas)'))
        self.ok = wx.Button(self, wx.ID_ANY, _('&Ok'))
        self.cancel = wx.Button(self, wx.ID_ANY, _('&Cancel'))
        # 1.3.6.1 [JWdJ] 2015-01-30 Swapped next two lines so OK-button comes first (OK Cancel)
        if WX4:
            box = wx.BoxSizer()
            box.Add(self.ok, wx.ID_OK)
            box.Add(self.cancel, wx.ID_CANCEL)
        else:
            box = wx.BoxSizer(wx.HORIZONTAL)
            box.Add(self.ok, wx.ID_OK, flag=wx.ALIGN_RIGHT)
            box.Add(self.cancel, wx.ID_CANCEL, flag=wx.ALIGN_RIGHT)

        sizer.Add(self.key,                     wx.GBPosition(0, 1), flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=border)
        sizer.Add(self.metre,                   wx.GBPosition(1, 1), flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=border)
        sizer.Add(self.default_len,             wx.GBPosition(2, 1), flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=border)
        sizer.Add(self.title,                   wx.GBPosition(3, 1), flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=border)
        sizer.Add(self.bpl,                     wx.GBPosition(4, 1), flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=border)
        sizer.Add(self.num_notes_in_anacrusis,  wx.GBPosition(5, 1), flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=border)
        sizer.Add(self.triplet_detection,       wx.GBPosition(6, 0), (1, 2), flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=border)
        sizer.Add(self.broken_rythm_detection,  wx.GBPosition(7, 0), (1, 2), flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=border)
        sizer.Add(self.slur_triplets,           wx.GBPosition(8, 0), (1, 2), flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=border)
        sizer.Add(self.slur_8ths,               wx.GBPosition(9, 0), (1, 2), flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=border)
        sizer.Add(self.slur_16ths,              wx.GBPosition(10,0), (1, 2), flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=border)
        sizer.Add(box,                          wx.GBPosition(11,0), (1, 2), flag=0 | wx.LEFT | wx.RIGHT | wx.ALIGN_RIGHT, border=border)

        self.triplet_detection.SetValue(True)
        self.broken_rythm_detection.SetValue(True)
        self.slur_triplets.SetValue(False)
        self.slur_16ths.SetValue(False)
        self.key.SetValue(key)
        self.metre.SetValue(str(metre))
        self.default_len.SetValue(str(default_len))
        self.num_notes_in_anacrusis.SetValue('0')
        self.bpl.SetValue('4')
        self.title.SetValue(title)
        self.ok.SetDefault()

        self.SetSizer(sizer)
        self.SetAutoLayout(True)
        self.Centre()
        sizer.Fit(self)

        self.ok.Bind(wx.EVT_BUTTON, self.OnOk)
        self.cancel.Bind(wx.EVT_BUTTON, self.OnCancel)

    def OnOk(self, evt):
        self.EndModal(wx.ID_OK)

    def OnCancel(self, evt):
        self.EndModal(wx.ID_CANCEL)
