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
import webbrowser

import wx
import wx.html
import wx.stc as stc
import wx.lib.agw.hypertreelist as htl
from wx.lib.scrolledpanel import ScrolledPanel
from wx import GetTranslation as _

from abc_transform import sort_abc_tunes
from aligner import extract_incipit
from app_state import app_state
from appearance import current_appearance
from constants import cwd, control_margin, program_name
from exceptions import AbortException
from tune_model import text_to_lines
from wxhelper import WX4, get_normal_fontsize, apply_editor_appearance


def generate_incipits_abc(settings, tune_list_controller, tune_count, editor):
    def get_num_music_lines_in_tune(abc):
        try:
            notes = re.split(r'K:.*\s*', abc, 1)[1]  # extract part after first K: field
            notes = re.sub(r'\[\w:.*?\]', '', notes) # remove fields
            return len([l for l in text_to_lines(notes) if l.strip()])  # return number of non-empty lines
        except IndexError:
            return 1

    result = []
    for i in range(tune_count):
        tune = tune_list_controller.GetTune(i)

        # make a copy of the tune header in order to be able to restore it after the incip extraction
        lines = text_to_lines(tune.abc)
        header = []
        title_count = 0
        for line in lines:
            if re.match('[a-zA-Z]:', line):
                if line[0] == 'T':
                    title_count += 1
                    if title_count > settings['incipits_numtitles']:
                        continue
                if line[0] != 'W':
                    header.append(line)
            elif re.match(r'\s*%', line):
                pass
            else:
                break

        incipit_parts = extract_incipit(os.linesep.join([tune.header, tune.abc]),
                                        num_bars=settings['incipits_numbars'],
                                        num_repeats=settings['incipits_numrepeats'])
        #abc = '[I:staffbreak]'.join(incipit_parts)
        abc = (os.linesep+'[T:][M:none]'+os.linesep).join(incipit_parts)
        abc = os.linesep.join(header + [abc, ''])
        result.append(abc)

    # extract file header
    lines = []
    get_line = editor.GetLine
    for i in range(editor.GetLineCount()):
        line = get_line(i)
        if line.startswith('X:') or line.startswith('T:'):
            break
        elif re.match(r'%%.*|[a-zA-Z_]:.*', line):
            lines.append(line.rstrip())

    lines.append('')
    lines.append('%%topspace 0.0cm')
    lines.append('%%staffsep 0.7cm')
    lines.append('%%titleformat T-1') # C1 S1')
    lines.append('%%maxshrink 1.4')
    lines.append('%%musiconly 1')
    lines.append('%%printtempo 0')
    lines.append('%%titlefont Helvetica-Oblique 16')
    lines.append('%%subtitlefont Helvetica-Oblique 13')
    lines.append('')
    lines.append('')
    file_header = lines[:]
    lines.extend(result)
    abc_code = os.linesep.join(lines)

    if settings['incipits_sortfields']:
        sort_fields = re.findall('[A-Za-z]', settings['incipits_sortfields'])
        abc_code = sort_abc_tunes(abc_code, sort_fields)

    if settings['incipits_twocolumns']:
        parts = file_header

        # extract each tune (incipit)
        pos = [m.start(1) for m in re.compile('(^X:)', re.M).finditer(abc_code)] + [20 * 1024**2]
        all_tunes = [abc_code[s1:s2].strip() + os.linesep for s1, s2 in zip(pos[0:], pos[1:])]

        while all_tunes:
            # extract left column tunes with a total of max <<incipits_rows>> rows
            num_lines = 0
            left_tunes = []
            while all_tunes:
                n = get_num_music_lines_in_tune(all_tunes[0])
                if num_lines == 0 or num_lines + n <= settings['incipits_rows']:
                    left_tunes.append(all_tunes.pop(0))
                    num_lines += n
                else:
                    break

            # extract right column tunes with a total of max <<incipits_rows>> rows
            num_lines = 0
            right_tunes = []
            while all_tunes:
                n = get_num_music_lines_in_tune(all_tunes[0])
                if num_lines == 0 or num_lines + n <= settings['incipits_rows']:
                    right_tunes.append(all_tunes.pop(0))
                    num_lines += n
                else:
                    break

            left_col = ['%%multicol start',
                        '%%rightmargin 11.5cm',
                        '%%leftmargin 1.5cm', ''] + left_tunes
            right_col = ['%%multicol new',
                        '%%rightmargin 1.5cm',
                        '%%leftmargin 11.5cm', ''] + right_tunes + ['', '%%multicol end', '%%newpage', '']
            parts.extend(left_col)
            parts.extend(right_col)
        abc_code = os.linesep.join(parts)

    return abc_code


class FieldReferenceTree(htl.HyperTreeList):

    def __init__(self, parent, id=wx.ID_ANY, pos=wx.DefaultPosition,
                 size=wx.DefaultSize,
                 style=wx.SUNKEN_BORDER,
                 agwStyle=wx.TR_HAS_BUTTONS | wx.TR_HAS_VARIABLE_ROW_HEIGHT | wx.TR_HIDE_ROOT | wx.TR_ROW_LINES):

        htl.HyperTreeList.__init__(self, parent, id, pos, size, style, agwStyle)
        self.AddColumn(_('Field'))
        self.AddColumn(_('Description'))
        self.SetMainColumn(0)
        self.root = self.AddRoot("Hidden root")

        if wx.Platform == "__WXMSW__":
            self.EnableSelectionVista(True)

        # 1.3.6.2 [JWDJ] moved get_sections to AbcStructure.get_sections
        from tune_elements import AbcStructure # 1.3.7.1 [JWDJ] 2016-1 because of translation this import has to be done as late as possible
        for (title, fields) in AbcStructure.get_sections(cwd):
            child = self.AppendItem(self.root, title)
            self.SetPyData(child, None)
            self.SetItemText(child, '', 1)
            for (field_name, description) in fields:
                child2 = self.AppendItem(child, field_name)
                self.SetPyData(child2, None)
                self.SetItemText(child2, description, 1)
        self.SetColumnWidth(0, 250)
        self.SetColumnWidth(1, 800)

        # 1.3.6.2 [JWDJ] moved get_sections to AbcStructure.get_sections


class IncipitsFrame(wx.Dialog):
    def __init__(self, parent, settings):
        self.settings = settings
        wx.Dialog.__init__(self, parent, wx.ID_ANY, _('Generate incipits file...'), wx.DefaultPosition, wx.Size(530, 260))
        border = control_margin
        sizer = box1 = wx.GridBagSizer()
        lb1 = wx.StaticText(self, wx.ID_ANY, _('Number of bars to extract:'))
        lb2 = wx.StaticText(self, wx.ID_ANY, _('Maximum number of repeats to extract:'))
        lb3 = wx.StaticText(self, wx.ID_ANY, _('Maximum number of titles/subtitles to extract:'))
        lb4 = wx.StaticText(self, wx.ID_ANY, _('Fields to sort by (eg. T):'))
        lb5 = wx.StaticText(self, wx.ID_ANY, _('Number of rows per column:'))
        self.edNumBars       = wx.SpinCtrl(self, wx.ID_ANY, "", min=1, max=10, initial=self.settings.get('incipits_numbars', 2))
        self.edNumRepeats    = wx.SpinCtrl(self, wx.ID_ANY, "", min=1, max=10, initial=self.settings.get('incipits_numrepeats', 1))
        self.edNumTitles     = wx.SpinCtrl(self, wx.ID_ANY, "", min=0, max=10, initial=self.settings.get('incipits_numtitles', 1))
        self.edSortFields    = wx.TextCtrl(self, wx.ID_ANY, self.settings.get('incipits_sortfields', ''))
        self.chkTwoColumns   = wx.CheckBox(self, wx.ID_ANY, _('&Two column output'))
        self.edNumRows       = wx.SpinCtrl(self, wx.ID_ANY, "", min=1, max=40, initial=self.settings.get('incipits_rows', 10))
        self.chkTwoColumns.SetValue(self.settings.get('incipits_twocolumns', True))
        for c in [self.edNumBars, self.edNumRepeats, self.edNumTitles, self.edNumRows, self.edSortFields]:
            c.SetValue(c.GetValue()) # this seems to be needed on OSX

        sizer.Add(lb1,                  pos=(0,0), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        sizer.Add(self.edNumBars,       pos=(0,1), flag=wx.EXPAND | wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        sizer.Add(lb2,                  pos=(1,0), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        sizer.Add(self.edNumRepeats,    pos=(1,1), flag=wx.EXPAND | wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        sizer.Add(lb3,                  pos=(2,0), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        sizer.Add(self.edNumTitles,     pos=(2,1), flag=wx.EXPAND | wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        sizer.Add(lb4,                  pos=(3,0), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        sizer.Add(self.edSortFields,    pos=(3,1), flag=wx.EXPAND | wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        sizer.Add(self.chkTwoColumns,   pos=(4,1), flag=wx.EXPAND | wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        sizer.Add(lb5,                  pos=(5,0), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)
        sizer.Add(self.edNumRows,       pos=(5,1), flag=wx.EXPAND | wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=border)

        # ok, cancel buttons
        self.ok = wx.Button(self, wx.ID_ANY, _('&Ok'))
        self.cancel = wx.Button(self, wx.ID_ANY, _('&Cancel'))
        self.ok.SetDefault()
        # 1.3.6.1 [JWdJ] 2015-01-30 Swapped next two lines so OK-button comes first (OK Cancel)
        if WX4:
            btn_box = wx.BoxSizer(wx.HORIZONTAL)
            btn_box.Add(self.ok, wx.ID_OK)
            btn_box.Add(self.cancel, wx.ID_CANCEL)
        else:
            btn_box = wx.BoxSizer(wx.HORIZONTAL)
            btn_box.Add(self.ok, wx.ID_OK, flag=wx.ALIGN_RIGHT)
            btn_box.Add(self.cancel, wx.ID_CANCEL, flag=wx.ALIGN_RIGHT)

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(box1, flag=wx.ALL | wx.EXPAND, border=10)
        self.sizer.Add(btn_box, flag=wx.ALL | wx.ALIGN_RIGHT, border=10)
        self.SetAutoLayout(True)
        self.Centre()
        self.sizer.Fit(self)
        self.SetSizer(self.sizer)

        self.ok.Bind(wx.EVT_BUTTON, self.OnOk)
        self.cancel.Bind(wx.EVT_BUTTON, self.OnCancel)
        self.chkTwoColumns.Bind(wx.EVT_CHECKBOX, self.OnTwoColumns)
        self.GrayUngray()
        self.save_settings()

    def GrayUngray(self):
        self.edNumRows.Enable(self.chkTwoColumns.IsChecked())

    def OnTwoColumns(self, evt):
        self.GrayUngray()

    def save_settings(self):
        self.settings['incipits_numbars'] = self.edNumBars.GetValue()
        self.settings['incipits_numrepeats'] = self.edNumRepeats.GetValue()
        self.settings['incipits_numtitles'] = self.edNumTitles.GetValue()
        self.settings['incipits_sortfields'] = self.edSortFields.GetValue().strip()
        self.settings['incipits_twocolumns'] = self.chkTwoColumns.IsChecked()
        self.settings['incipits_rows'] = self.edNumRows.GetValue()
        if self.settings['incipits_rows'] <= 0:
            self.settings['incipits_rows'] = 1

    def OnOk(self, evt):
        self.save_settings()
        self.EndModal(wx.ID_OK)

    def OnCancel(self, evt):
        self.EndModal(wx.ID_CANCEL)


class ErrorFrame(wx.Dialog):
    def __init__(self, parent, error_msg):
        wx.Dialog.__init__(self, parent, wx.ID_ANY, _('Errors'), wx.DefaultPosition, wx.Size(700, 80))
        border = 10

        sizer = wx.BoxSizer(wx.VERTICAL)
        font_size = get_normal_fontsize() # 1.3.6.3 [JWDJ] one function to set font size
        font = wx.Font(font_size, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, "Courier New")
        self.error = wx.TextCtrl(self, wx.ID_ANY, error_msg, size=(700, 300), style=wx.TE_MULTILINE|wx.TE_PROCESS_ENTER|wx.HSCROLL)
        self.error.SetFont(font)

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

        sizer.Add(self.error, flag=wx.EXPAND | wx.TOP | wx.LEFT | wx.RIGHT, border=border)
        sizer.Add(box, flag=wx.ALL | wx.ALIGN_RIGHT, border=border)
        self.ok.SetDefault()

        self.SetSizer(sizer)
        self.SetAutoLayout(True)
        self.Centre()
        sizer.Fit(self)

        self.Bind(wx.EVT_KEY_DOWN, self.OnKeyDownEvent)
        self.ok.Bind(wx.EVT_BUTTON, self.OnOk)
        self.cancel.Bind(wx.EVT_BUTTON, self.OnCancel)

    def OnKeyDownEvent(self, evt):
        if evt.GetKeyCode() == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
        else:
            evt.Skip()

    def OnOk(self, evt):
        self.EndModal(wx.ID_OK)

    def OnCancel(self, evt):
        self.EndModal(wx.ID_CANCEL)


class ProgressFrame(wx.Frame):
    def __init__(self, parent, ID, title=_('Converting...')):
        wx.Frame.__init__(self, parent, ID, title, wx.DefaultPosition, wx.Size(500, 80))
        self.gauge = wx.Gauge(self, wx.ID_ANY, 100, (0, 0), (500, 80))
        self.Centre()
    def SetPercent(self, percent):
        self.gauge.SetValue(percent)


class MyMidiTextTree(wx.Frame):
    def __init__(self,title):
        wx.Frame.__init__(self, wx.GetApp().TopWindow, wx.ID_ANY, title, wx.DefaultPosition, wx.Size(450, 350))

        hbox = wx.BoxSizer(wx.HORIZONTAL)
        vbox = wx.BoxSizer(wx.VERTICAL)
        panel1 = wx.Panel(self, -1)

        self.tree = wx.TreeCtrl(panel1, 1, wx.DefaultPosition, (-1, -1), wx.TR_HAS_BUTTONS )
        vbox.Add(self.tree, 1, wx.EXPAND)
        hbox.Add(panel1, 1, wx.EXPAND)
        panel1.SetSizer(vbox)
        self.SetSizer(hbox)
        self.Centre()

    def LoadMidiData(self,data):
        self.tree.DeleteAllItems()
        tracknum = '0'
        trk = {}
        for line in data:
            col = line.find('Track')
            if col == 0:
                words = line.split(' ')
                tracknum = words[1]
                trk[tracknum] = self.tree.AppendItem(self.root,line)
            else:
                if tracknum == '0':
                    self.root = self.tree.AddRoot(line)
                    continue
                self.tree.AppendItem(trk[tracknum],line)
        self.tree.Expand(self.root)


class MyInfoFrame(wx.Frame):
    ''' Creates the TextCtrl for displaying any messages from abc2midi or abcm2ps. '''
    def __init__(self):
        # 1.3.6.1 [JWdJ] 2014-01-30 Resizing message window fixed
        wx.Frame.__init__(self, wx.GetApp().TopWindow, wx.ID_ANY, _("Messages"),style=wx.DEFAULT_FRAME_STYLE,name='infoframe',size=(600,240))
        # Add a panel so it looks the correct on all platforms
        self.panel = ScrolledPanel(self)
        self.basicText = wx.TextCtrl(self.panel, wx.ID_ANY, "",style=wx.TE_MULTILINE | wx.TE_READONLY)
        # 1.3.6.3 [JWDJ] changed to fixed font so Abcm2ps-messages with a ^ make sense
        font = wx.Font(10, wx.FONTFAMILY_MODERN, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        self.basicText.SetFont(font)
        sizer = wx.BoxSizer()
        sizer.Add(self.basicText,1, wx.ALL|wx.EXPAND)
        self.panel.SetSizer(sizer)
        self.panel.SetupScrolling()

    def ShowText(self,text):
        self.basicText.Clear()
        self.basicText.AppendText(text)

    # 1.3.6.3 [JWDJ] 2015-04-27
    @staticmethod
    def update_text():
        win = wx.FindWindowByName('infoframe')
        if win is not None:
            win.ShowText(app_state.messages)


class MyAbcFrame(wx.Frame):
    ''' Creates the TextCtrl for displaying any messages from abc2midi or abcm2ps. '''
    def __init__(self):
        wx.Frame.__init__(self, wx.GetApp().TopWindow, wx.ID_ANY, _("Processed Abc Tune"),style=wx.DEFAULT_FRAME_STYLE,name='abctuneframe')
        # 1.3.6.3 [JWdJ] 2015-04-22 bugfix: resizing processed abc tune page now works correctly
        self.basicText = stc.StyledTextCtrl(self, wx.ID_ANY, (-1, -1), (600, 450))
        self.basicText.SetMarginLeft(15)
        self.basicText.SetMarginWidth(1, 40)
        self.basicText.SetMarginType(1, stc.STC_MARGIN_NUMBER)

        self.ApplyAppearance()

        sizer = wx.BoxSizer()
        sizer.Add(self.basicText,1, wx.ALL | wx.EXPAND)
        self.SetSizer(sizer)
        sizer.Fit(self)

    def ApplyAppearance(self):
        font = wx.Font(10, wx.FONTFAMILY_MODERN, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        appearance = current_appearance()
        apply_editor_appearance(self.basicText, appearance, appearance.style_palette.__getitem__, font.GetFaceName(), font.GetPointSize())

    def ShowText(self, text):
        try:
            self.basicText.SetEditable(True)
        except:
            pass
        self.basicText.ClearAll() # 1.3.6.4 [SS] 2015-06-17
        self.basicText.AppendText(text)
        try:
            self.basicText.SetEditable(False) # 1.3.6.3 [JWdJ] 2015-04-22 abc code not editable
        except:
            pass # 1.3.6.3 [JWdJ] 2015-05-02 older wx-versions do not support SetEditable

    # 1.3.6.3 [JWDJ] 2015-04-27
    @staticmethod
    def update_text():
        win = wx.FindWindowByName('abctuneframe')
        if win is not None:
            win.ShowText(app_state.visible_abc_code)


class MyTunesListFrame(wx.Frame):
    ''' Creates the TextCtrl for displaying the tunes list'''
    def __init__(self):
        # 1.3.6.1 [JWdJ] 2014-01-30 Resizing message window fixed
        wx.Frame.__init__(self, wx.GetApp().TopWindow, wx.ID_ANY, _("List of tunes"),style=wx.DEFAULT_FRAME_STYLE,name='tuneslistframe',size=(600,240))
        # Add a panel so it looks the correct on all platforms
        self.panel = ScrolledPanel(self)
        self.basicText = wx.TextCtrl(self.panel, wx.ID_ANY, "",style=wx.TE_MULTILINE | wx.TE_READONLY)
        # 1.3.6.3 [JWDJ] changed to fixed font so Abcm2ps-messages with a ^ make sense
        font = wx.Font(10, wx.FONTFAMILY_MODERN, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        self.basicText.SetFont(font)
        sizer = wx.BoxSizer()
        sizer.Add(self.basicText,1, wx.ALL|wx.EXPAND)
        self.panel.SetSizer(sizer)
        self.panel.SetupScrolling()

    def ShowText(self,text):
        self.basicText.Clear()
        self.basicText.AppendText(text)


class AboutFrame(wx.Dialog):
    htmlpage = '''
<html>
<body bgcolor="{background}" text="{text}">
<center><img src="img/abclogo.png"/>
</center>
<p><b>{program_name}</b><br/>
an open source ABC editor for Windows, OSX and Linux. It is published under the <a href="https://www.gnu.org/licenses/gpl-2.0.html">GNU Public License</a>. </p>
<p><center>initial repository was at <a href="https://www.nilsliberg.se/ksp/easyabc/">https://www.nilsliberg.se/ksp/easyabc/</a></center></p>
<p><center>Now documentation available here<a href="https://easyabc.sourceforge.net">https://easyabc.sourceforge.net</a></center></p>
<p><u>Features</u>:</p>
<ul style="line-height: 150%; margin-top: 3px;">
  <li> Good ABC standard coverage thanks to internal use of abcm2ps and abc2midi
  <li> Syntax highlighting
  <li> Zoom support
  <li> Import MusicXML, MIDI and Noteworthy Composer files (the midi to abc translator is custom made in order to produce legible abc code with more sensible beams than the typical midi2abc output).
  <li> Export to MIDI, SVG, PDF (single tune or whole tune book).
  <li> Select notes by clicking on them and add music symbols by using drop-down menus in the toolbar.
  <li> Play the active tune as midi
  <li> Record songs from midi directly in the program (no OSX support at the moment).<br/>
  Just press Rec, play on your midi keyboard and then press Stop.
  <li> The musical score is automatically updated as you type in ABC code.
  <li> Support for unicode (utf-8) and other encodings.
  <li> Transpose and halve/double note length functionality (using abc2abc)
  <li> An abcm2ps format file can easily be specified in the settings.
  <li> ABC fields in the file header are applied to every single tune in a tune book.
  <li> Automatic alignment of bars on different lines
  <li> Available in <img src="img/new.gif"/>German, Dutch, Italian, French, Danish, Swedish, German and English</li>
  <li> Functions to generate incipits, sort tunes and renumber X: fields.</li>
  <li> Musical search function - search for note sequences irrespectively of key, etc. <img src="img/new.gif"/></li>
</ul>

<p><b>EasyABC</b> is brought to you by <b>Nils Liberg</b>, Copyright &copy; 2010-2012.</p>
<p><b>EasyABC</b> is maintained by <b>Jan Wybren de Jong</b>, <b>Seymour Shlien</b> and  by <b>Fr&eacute;d&eacute;ric Aup&eacute;pin</b> for Mac adaptation</p>
<p><b>Credits</b> - software components used by EasyABC:</p>
<ul class="nicelist">
<li><a href="http://moinejf.free.fr/">abcm2ps</a> for converting ABC code to note images (developed/maintained by Jean-Fran&ccedil;ois Moine)</li>
<li><a href="http://abc.sourceforge.net/abcMIDI/">abc2midi</a> for converting ABC code to midi (by James Allwright, maintained by Seymour Shlien)</li>
<li><a href="https://wim.vree.org/svgParse/xml2abc.html">xml2abc</a> for converting from MusicXML to ABC (by Willem Vree)</li>
<li><a href="https://sites.google.com/site/juria90/nwc">nwc2xml</a> for converting from Noteworthy Composer format to ABC via XML (by James Lee)</li>
<li><a href="https://www.wxpython.org/">wxPython</a> cross-platform user-interface framework</li>
<li><a href="https://www.scintilla.org/">scintilla</a> for the text editor used for ABC code</li>
<li><a href="https://www.mxm.dk/products/public/pythonmidi">python midi package</a> for the initial parsing of midi files to be imported</li>
<li><a href="https://www.pygame.org/download.shtml">pygame</a> (which wraps <a href="https://sourceforge.net/apps/trac/portmedia/wiki/portmidi">portmidi</a>) for real-time midi input</li>
<li><a href="https://www.fluidsynth.org/">FluidSynth</a> for playing midi (and made fit for Python with a <a href="https://wim.vree.org/svgParse/testplayer.html">player</a> by <a href="https://wim.vree.org/svgParse/">Willem Vree</a>)</li>
<li><a href="https://github.com/jheinen/mplay">Python MIDI Player</a> for playing midi on Mac</li>
<li>Thanks to Guido Gonzato for providing the fields and command reference extracted from his <a href="https://abcplus.sourceforge.net/#ABCGuide">Making music with ABC guide</a>.</li>
<li><br>Many thanks to the translators: Valerio&nbsp;Pelliccioni, Guido&nbsp;Gonzato&nbsp;(italian), Bendix&nbsp;R&oslash;dgaard&nbsp;(danish), Fr&eacute;d&eacute;ric&nbsp;Aup&eacute;pin&nbsp;(french), Bernard&nbsp;Weichel&nbsp;(german), Jan&nbsp;Wybren&nbsp;de&nbsp;Jong&nbsp;(dutch) and Wu&nbsp;Xiaotian&nbsp;(chinese).</li>
<li>Universal binaries of <a href="https://abcplus.sourceforge.net/#abcm2ps">abcm2ps</a> and <a href="https://abcplus.sourceforge.net/#abcmidi">abc2midi</a> for OSX are available thanks to Chuck&nbsp;Boody and Guido Gonzato</li>
</ul>

<p><b>Links</b></p>
<ul class="nicelist">
<li><a href="https://abcnotation.com/">abcnotation.com</a></li>
<li><a href="http://abcplus.sourceforge.net/">abcplus.sourceforge.net</a></li>
<li><a href="http://moinejf.free.fr/">Jef Moine's abcm2ps page</a></li>
<li><a href="https://abcmidi.sourceforge.io/">Seymour Shlien's abcMIDI page</a></li>
<li><a href="http://www.folkwiki.se/">folkwiki.se - Swedish folk music</a> (initial involvement of Nils here is the reason why he implemented the program)</li>
</ul>
</body>
</html>
'''

    def __init__(self, parent):
        wx.Dialog.__init__(self, parent, wx.ID_ANY, _('About EasyABC'), size=(900, 600) )
        about_html = wx.html.HtmlWindow(self, -1)
        appearance = current_appearance()
        about_html.SetPage(self.htmlpage.format(
            program_name=program_name,
            background=appearance.html(appearance.window_background),
            text=appearance.html(appearance.text)))
        button = wx.Button(self, wx.ID_OK, _('&Ok'))
        button.SetDefault()

        # Definition of the padding of the window
        lc = wx.LayoutConstraints()
        lc.top.SameAs(self, wx.Top, 5)
        lc.left.SameAs(self, wx.Left, 5)
        lc.bottom.SameAs(button, wx.Top, 5)
        lc.right.SameAs(self, wx.Right, 5)
        about_html.SetConstraints(lc)

        # Definition of the position of the OK button
        lc = wx.LayoutConstraints()
        lc.bottom.SameAs(self, wx.Bottom, 5)
        lc.centreX.SameAs(self, wx.CentreX)
        lc.width.AsIs()
        lc.height.AsIs()
        button.SetConstraints(lc)

        about_html.Bind(wx.html.EVT_HTML_LINK_CLICKED, self.OnLinkClicked)

        self.SetAutoLayout(True)
        self.Layout()
        self.CentreOnParent(wx.BOTH)

    def OnLinkClicked(self, evt):
        webbrowser.open(evt.GetLinkInfo().GetHref())
        return wx.html.HTML_BLOCK


class MyFileDropTarget(wx.FileDropTarget):
    def __init__(self, frame):
        wx.FileDropTarget.__init__(self)
        self.frame = frame

    def OnDropFiles(self, x, y, filenames):
        frame = self.frame
        self.frame.Raise()

        # if it's just a single file and we don't have anything else loaded, just load the file normally
        if len(filenames) == 1 and not frame.editor.GetText().strip() and not frame.editor.GetModify() and not frame.current_file and os.path.splitext(filenames[0])[1].lower() in ['.txt', '.abc', '.mcm', '']:   # if a new unmodified document
            frame.load(filenames[0])
        else:
            try:
                try:
                    self.frame.editor.BeginUndoAction()
                    progress = ProgressFrame(self.frame, -1)
                    progress.Show(True)
                    for i, filename in enumerate(filenames):
                        if not self.frame.OnDropFile(filename):
                            break
                        progress.SetPercent(100 * (i+1) / len(filenames))
                finally:
                    self.frame.editor.EndUndoAction()
                    progress.Close()
            except AbortException:
                pass
            self.frame.UpdateTuneList()
            self.frame.tune_list.Select(self.frame.tune_list.GetItemCount()-1)
            self.frame.OnTuneSelected(None)
