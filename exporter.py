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
import shutil
import traceback
import zipfile
from io import StringIO

import wx
from wx import GetTranslation as _

from abc_midi_export import AbcToMidi
from abc_tools import AbcToAbc, AbcToPDF, AbcToSvg, get_output_from_process, launch_file
from aligner import align_lines
from app_state import app_state
from dialogs import ErrorFrame
from tune_model import Tune, text_to_lines
from utils import ensure_file_name_does_not_exist
from xml2abc_interface import abc_to_xml


def comment_pageheight(abc):
    return re.sub(r'(?m)^%%pageheight\b', '% %%pageheight', abc)


def create_tune_from_multi_abc(frame, abc, header, num_header_lines):
    if frame.document.current_file:
        title = os.path.splitext(os.path.basename(frame.document.current_file))[0]
    else:
        title = _('Untitled')
    return Tune('', title, '', 0, 0, abc, header, num_header_lines)


class Exporter(object):
    """Exporting tunes to MIDI, audio, PDF, SVG, MusicXML, HTML and ABC, and the transpose/note-length/align-bars tools."""

    def __init__(self, frame):
        self.frame = frame

    def GetFileNameForTune(self, tune, file_extension):
        filename = tune.title
        if not filename:
            filename = '%s' % tune.xnum
        filename = re.sub(r'[\\/:"*?<>|]', ' ', filename).strip()
        filename = filename + file_extension
        return filename

    def OnExportToClipboard(self, evt):
        abc = os.linesep.join(tune.abc for tune in self.frame.tune_list_controller.GetSelectedTunes(add_file_header=False))
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(abc))
            wx.TheClipboard.Close()

    def OnExportMidi(self, evt):
        self.export_tunes(_('Midi file'), '.mid', self.export_midi, only_selected=True)

    #Add an export all tunes to MIDI option
    def OnExportAllMidi(self, evt):
        self.export_tunes(_('Midi file'), '.mid', self.export_midi, only_selected=False)

    def export_midi(self, tune, filepath):
        tempo_multiplier = self.frame.playback.get_tempo_multiplier()
        midi_tune = AbcToMidi(tune.abc, tune.header, self.frame.cache_dir, self.frame.settings, self.frame.statusbar, tempo_multiplier)
        if midi_tune:
            try:
                shutil.copy(midi_tune.midi_file, filepath)
                return True
            except:
                pass
                # print('failed to create %s' % filepath)
            finally:
                midi_tune.cleanup()
        return False

    def OnExportToMP3(self, evt):
        if self.frame.playback.uses_fluidsynth:
            self.export_tunes(_('MP3 file'), '.mp3', self.export_mp3, only_selected=True)
        else:
            self.frame.playback.ReportFluidSynthIsMissing()

    def OnExportToAAC(self, evt):
        if self.frame.playback.uses_fluidsynth:
            self.export_tunes(_('AAC file'), '.m4a', self.export_aac, only_selected=True)
        else:
            self.frame.playback.ReportFluidSynthIsMissing()

    def OnExportToWave(self, evt):
        if self.frame.playback.uses_fluidsynth:
            self.export_tunes(_('Wave file'), '.wav', self.export_wave, only_selected=True)
        else:
            self.frame.playback.ReportFluidSynthIsMissing()

    def export_wave(self, tune, filepath):
        tempo_multiplier = self.frame.playback.get_tempo_multiplier()
        midi_tune = AbcToMidi(tune.abc, tune.header, self.frame.cache_dir, self.frame.settings, self.frame.statusbar, tempo_multiplier)
        if midi_tune:
            try:
                self.frame.playback.mc.render_to_file(midi_tune.midi_file, filepath)
                return True
            except:
                self.frame.statusbar.SetStatusText(_('Failed to create {0}').format(filepath))
            finally:
                midi_tune.cleanup()
        return False

    def export_mp3(self, tune, filepath):
        self.export_ffmpeg(tune, filepath)

    def export_aac(self, tune, filepath):
        self.export_ffmpeg(tune, filepath)

    def export_ffmpeg(self, tune, filepath):
        ffmpeg_path = self.frame.settings['ffmpeg_path']
        if ffmpeg_path and os.path.exists(ffmpeg_path):
            base_name, ext = os.path.splitext(filepath)
            tmp_file = base_name + '.wav'
            if not self.export_wave(tune, tmp_file):
                return

            if os.path.exists(tmp_file):
                cmd = [ffmpeg_path, '-y', '-nostdin', '-i', tmp_file, '-vn', filepath]
                if ext == '.m4a':
                    cmd = [ffmpeg_path, '-y', '-nostdin', '-i', tmp_file, '-c:a', 'aac', '-q:a', '0.5', filepath]

                if os.path.exists(filepath):
                    os.remove(filepath)
                app_state.messages += '\nffmpeg\n' + " ".join(cmd)
                stdout_value, stderr_value, returncode = get_output_from_process(cmd)
                if returncode != 0:
                    app_state.messages += stderr_value
                    app_state.messages += stdout_value
                    print(stderr_value)
                    print(stdout_value)
                    print(returncode)

                if os.path.exists(tmp_file):
                    os.remove(tmp_file)
        else:
            dlg = wx.MessageDialog(self.frame, _('ffmpeg was not found here. Go to settings and indicate the path'), _('Warning'), wx.OK)
            dlg.ShowModal()

    #Add an export all tunes to individual PDF option
    def OnExportAllPDFFiles(self, evt):
        self.export_pdf_tunes(only_selected=False)

    def OnExportPDF(self, evt):
        self.export_pdf_tunes(only_selected=True)

    def OnExportAllPDF(self, evt):
        self.export_pdf_tunes(only_selected=False, single_file=True)

    def OnExportSelectedToSinglePDF(self, evt):
        self.export_pdf_tunes(only_selected=True, single_file=True)

    def export_pdf(self, tune, filepath):
        pdf_file = AbcToPDF(self.frame.settings, tune.abc, tune.header, self.frame.cache_dir, self.frame.settings.get('abcm2ps_extra_params', ''),
                            self.frame.settings.get('abcm2ps_path', ''),
                            self.frame.settings.get('gs_path',''),
                            #self.frame.settings.get('ps2pdf_path',''),
                            self.frame.settings.get('abcm2ps_format_path', ''))
        if pdf_file:
            return self.copy_to_destination_and_launch_file(pdf_file, filepath)

        return False

    def export_pdf_tunes(self, only_selected=False, single_file=False):
        gs_path = self.frame.settings.get('gs_path')
        if not gs_path:
            dlg = wx.MessageDialog(self.frame, _('EasyABC needs an external program called GhostScript to generate PDFs. You can get it from https://www.ghostscript.com/download/'), _('Warning'), wx.OK)
            dlg.ShowModal()
            return
        if not os.path.exists(gs_path):
            dlg = wx.MessageDialog(self.frame, _('ghostscript was not found here. Go to settings and indicate the path'), _('Warning'), wx.OK)
            dlg.ShowModal()
            return

        self.export_tunes(_('PDF file'), '.pdf', self.export_pdf, only_selected=only_selected, single_file=single_file)

    def OnExportSVG(self, evt):
        self.export_tunes(_('SVG file'), '.svg', self.export_svg, only_selected=True)

    def export_svg(self, tune, filepath):
        # 1.3.6 [SS] 2014-12-02 2014-12-07
        svg_files, error = AbcToSvg(tune.abc, tune.header,
                                    self.frame.cache_dir,
                                    self.frame.settings,
                                    target_file_name=filepath,
                                    with_annotations=False)
        if svg_files:
            return launch_file(svg_files[0])
        return False

    def OnExportMusicXML(self, evt):
        self.export_tunes_to_musicxml(only_selected=True)

    def OnExportAllMusicXML(self, evt):
        self.export_tunes_to_musicxml(only_selected=False)

    def export_tunes_to_musicxml(self, only_selected):
        mxl = self.frame.settings['xmlcompressed']
        app_state.messages = u'abc_to_mxl   compression = ' + str(mxl) + '\n'
        extension = '.xml'
        filetype = _('MusicXML')
        if mxl:
            extension = '.mxl'
            filetype = _('Compressed MusicXML')

        self.export_tunes(filetype, extension, self.export_musicxml, only_selected=only_selected)

    def export_musicxml(self, tune, filepath):
        mxl = self.frame.settings['xmlcompressed']
        pageFormat = []
        errors = []
        # 1.3.6.3 [SS] 2015-05-07
        info_messages = []
        try:
            abc_to_xml(tune.header + os.linesep + tune.abc, filepath, mxl, pageFormat, info_messages)
        except Exception as e:
            error_msg = traceback.format_exc() + os.linesep + os.linesep.join(errors)
            mdlg = ErrorFrame(self.frame, _('Error during conversion of X:{0} ("{1}"): {2}').format(tune.xnum, tune.title, error_msg))
            result = mdlg.ShowModal()
            mdlg.Destroy()
            return result == wx.ID_OK  # if ok is pressed, continue to process other tunes, if cancel, do not process more tunes

        # 1.3.6 [SS] 2014-12-10
        for infoline in info_messages:
            app_state.messages += infoline
        return True

    def OnExportHTML(self, evt):
        self.export_tunes(_('HTML file'), '.html', self.export_html, only_selected=True)

    def OnExportInteractiveHTML(self, evt):
        self.export_tunes(_('HTML file (interactive)'), '.html', self.export_interactive_html, only_selected=True, single_file=True)

    def export_html(self, tune, filepath):
        # 1.3.6 [SS] 2014-12-02 2014-12-07
        svg_files, error = AbcToSvg(tune.abc, tune.header,
                                    self.frame.cache_dir,
                                    self.frame.settings,
                                    with_annotations=False)
        if svg_files:
            with open(filepath, 'w', encoding='utf-8', newline='') as f:
                f.write('<html xmlns="http://www.w3.org/1999/xhtml">\n')
                f.write('<head><meta http-equiv="Content-Type" content="text/html; charset=UTF-8"/> </head>\n')
                f.write('<body>\n\n')
                for fn in svg_files:
                    with open(fn, 'r', encoding='utf-8', newline='') as svg_file:
                        svg = svg_file.read()
                    svg = svg[svg.index('<svg'):]
                    f.write(svg)
                    f.write('\n\n')
                f.write('</body></html>')
            return launch_file(filepath)
        return False

    def export_interactive_html(self, tune, filepath):
        abc = tune.abc
        if '%%MIDI drummap' in abc:
            abc = re.sub(r'%%MIDI drummap\s+(?P<note>\^[A-Ga-g])\s+(?P<midinote>\d+)', r'%%percmap \g<note> \g<midinote> x', abc)
            abc = re.sub(r'%%MIDI drummap\s+(?P<note>_[A-Ga-g])\s+(?P<midinote>\d+)', r'%%percmap \g<note> \g<midinote> circle-x', abc)
            abc = abc.replace('%%MIDI drummap ', '%%percmap ')

        if self.frame.settings.get('play_chords') or '%%MIDI gchord' in abc:
            # prepend gchordon to each tune body
            abclines = text_to_lines(abc)
            new_abc_lines = []
            header_started = False
            for line in abclines:
                new_abc_lines.append(line)
                if line.startswith('X:'):
                    header_started = True
                elif line.startswith('K:') and header_started:
                    new_abc_lines.append('%%MIDI gchordon')
                    header_started = False
            abc = '\n'.join(new_abc_lines)

        with open(filepath, 'w', encoding='utf-8', newline='') as f:
            f.write('<!DOCTYPE HTML>\n')
            f.write('<html>\n<head>\n')
            f.write('<meta http-equiv="Content-Type" content="text/html; charset=UTF-8"/>\n')
            f.write('<script src="http://moinejf.free.fr/js/abcweb-1.js"></script>\n')
            f.write('<script src="http://moinejf.free.fr/js/snd-1.js"></script>\n')
            f.write('<style type="text/css">\n')
            f.write('svg {display:block}\n')
            f.write('@media print{body{margin:0;padding:0;border:0}.nop{display:none}}\n')
            f.write('</style>\n')
            f.write('</head>\n<body>\n<script type="text/vnd.abc">\n\n\n')
            f.write(comment_pageheight(tune.header))
            f.write('\n')
            f.write(comment_pageheight(abc))
            f.write('\n\n\n</script>\n</body>\n</html>')
        return launch_file(filepath)

    def OnExportAllHTML(self, evt):
        self.export_tunes(_('HTML file'), '.html', self.export_html, only_selected=False, single_file=True)

    def OnExportAllInteractiveHTML(self, evt):
        self.export_tunes(_('HTML file'), '.html', self.export_interactive_html, only_selected=False, single_file=True)

    def OnExportAllEpub(self, evt):
        tunes = []
        for i in range(self.frame.tune_list.GetItemCount()):
            self.frame.tune_list.Select(i)
            tunes.append(self.frame.tune_list_controller.GetSelectedTune())
        if tunes:
            if self.frame.document.current_file:
                filename = os.path.splitext(self.frame.document.current_file)[0] + '.epub'
            else:
                filename = ''
            dlg = wx.FileDialog(self.frame, message=_("Export all tunes as ..."), defaultFile=os.path.basename(filename), wildcard=_("Epub file") + " (*.epub)|*.epub", style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
            try:
                if dlg.ShowModal() == wx.ID_OK:
                    self.frame.SetCursor(wx.HOURGLASS_CURSOR)
                    path = dlg.GetPath()
                    zip = zipfile.ZipFile(path, 'w')
                    zip.writestr('mimetype', 'application/epub+zip')
                    zip.writestr('META-INF/container.xml',
                                 '''<?xml version="1.0"?>
                                        <container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
                                            <rootfiles> <rootfile full-path="OEBPS/book.opf" media-type="application/oebps-package+xml" /> </rootfiles>
                                        </container>''')
                    opf = '''<package unique-identifier="pub-id">
                            <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
                                <dc:identifier id="pub-id">urn:uuid:A1B0D67E-2E81-4DF5-9E67-A64CBE366809</dc:identifier>
                                <dc:title>ABC tunebook</dc:title>
                                <dc:language>en</dc:language>
                                <meta property="dcterms:modified">2012-05-01T12:00:00Z</meta>
                            </metadata>
                            <manifest>
                              %s
                            </manifest>
                        </package>'''

                    f = StringIO()
                    f.write('''<html xmlns="http://www.w3.org/1999/xhtml">''')
                    f.write('''<head><meta http-equiv="Content-Type" content="text/html; charset=UTF-8"/>
                      <style type="text/css">
                        svg { float: left; clear: both; }
                      </style>
                    </head>
                    <body>\n\n''')
                    num_pages = []
                    for i, tune in enumerate(tunes):
                        # 1.3.6 [SS] 2014-12-02 2014-12-07
                        svg_files, error = AbcToSvg(tune.abc, tune.header,
                                                    self.frame.cache_dir,
                                                    self.frame.settings,
                                                    with_annotations=False,
                                                    one_file_per_page=False)
                        self.frame.update_statusbar_and_messages()
                        if svg_files:
                            for j, fn in enumerate(svg_files):
                                zip.write(fn, 'OEBPS/Contents/tune%.2d_page%.2d.svg' % (i+1, j+1))
                    f.write('</body></html>')
                    zip.close()
                    self.frame.SetCursor(wx.STANDARD_CURSOR)
                    #launch_file(path)
            finally:
                dlg.Destroy() # 1.3.6.3 [JWDJ] 2015-04-21 always clean up dialog window

    def copy_to_destination_and_launch_file(self, file_name, destination_path):
        try:
            shutil.copy(file_name, destination_path)
            return launch_file(destination_path)
        except IOError as ex:
            pass
            # print(u'Failed to create %s: %s' % (destination_path.encode('utf-8'), os.strerror(ex.errno)))
        return False

    def OnExportToABC(self, evt):
        self.export_tunes(_('ABC file'), '.abc', self.export_abc, only_selected=True, single_file=True)

    def export_abc(self, tune, filepath):
        with open(filepath, 'w', encoding='utf-8', newline='') as f:
            f.write(tune.header)
            f.write(os.linesep)
            f.write(tune.abc)
        frame = self.frame.document.OnNew()
        frame.document.load(filepath.decode('utf-8'))
        return True

    def export_tune(self, tune, file_type, extension, convert_func, path, show_save_dialog=True):
        # 1.3.6.3 [SS] 2015-05-07
        filename = self.GetFileNameForTune(tune, extension)
        filepath = os.path.join(path or '', filename)
        filepath = ensure_file_name_does_not_exist(filepath)

        if show_save_dialog:
            wildcard = u'{0} (*{1})|*{1}'.format(file_type, extension)
            default_dir, filename = os.path.split(filepath)
            dlg = wx.FileDialog(self.frame, message=_("Export tune as ..."), defaultFile=filename, defaultDir=default_dir, wildcard=wildcard, style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
            try:
                if dlg.ShowModal() == wx.ID_OK:
                    filepath = dlg.GetPath()
                else:
                    return False
            finally:
                dlg.Destroy() # 1.3.6.3 [JWDJ] 2015-04-21 always clean up dialog window

        if convert_func(tune, filepath):
            app_state.messages = app_state.messages + u'creating '+ filepath + u'\n'
            # 1.3.6 [SS] 2014-12-08
            self.frame.statusbar.SetStatusText(_('{0} was written').format(file_type))
            return True
        return False

    def export_tunes(self, file_type, extension, convert_func, only_selected=False, single_file=False):
        if single_file:
            if only_selected:
                selected_tunes = self.frame.tune_list_controller.GetSelectedTunes(add_file_header=False)
                if selected_tunes:
                    if len(selected_tunes) == 1:
                        tunes = self.frame.tune_list_controller.GetSelectedTunes(add_file_header=True)
                    else:
                        abc = os.linesep.join(tune.abc for tune in selected_tunes)
                        header, num_header_lines = self.frame.tune_list_controller.GetFileHeaderBlock()
                        tunes = [create_tune_from_multi_abc(self.frame, abc, header, num_header_lines)]
                else:
                    tunes = []
            else:
                abc, header, num_header_lines = self.frame.editor.GetText(), '', 0
                tunes = [create_tune_from_multi_abc(self.frame, abc, header, num_header_lines)]
        else:
            if only_selected:
                tunes = self.frame.tune_list_controller.GetSelectedTunes()
            else:
                tunes = [self.frame.tune_list_controller.GetTune(i) for i in range(self.frame.tune_list.GetItemCount())]

        if len(tunes) == 0:
            return

        individual_save_dialog = only_selected or single_file

        if self.frame.document.current_file:
            path = os.path.dirname(self.frame.document.current_file)
        else:
            path = ''

        if not individual_save_dialog:
            dlg = wx.DirDialog(self.frame, message=_("Choose a directory..."), style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
            try:
                if dlg.ShowModal() == wx.ID_OK:
                    path = dlg.GetPath()
                else:
                    return
            finally:
                dlg.Destroy() # 1.3.6.3 [JWDJ] 2015-04-21 always clean up dialog window

        app_state.messages = u''

        self.frame.statusbar.SetStatusText(_('{0} files to create').format(len(tunes)))
        progdialog = None
        try:
            self.frame.SetCursor(wx.HOURGLASS_CURSOR)

            # 1.3.6 [SS] 2014-12-08
            progdialog = wx.ProgressDialog(_('Exporting'), _('Remaining time'), len(tunes),
                                           style = wx.PD_CAN_ABORT | wx.PD_ELAPSED_TIME | wx.PD_REMAINING_TIME | wx.PD_AUTO_HIDE)
            j = 0
            for tune in tunes:
                j += 1
                running = progdialog.Update(j)
                if not running[0]:
                    break

                try:
                    success = self.export_tune(tune, file_type, extension, convert_func, path, show_save_dialog=individual_save_dialog)
                except Exception as e:
                    error_msg = traceback.format_exc()
                    print(error_msg)
                    success = False

                if not success:
                    break
        finally:
            self.frame.SetCursor(wx.STANDARD_CURSOR)
            if progdialog:
                progdialog.Destroy()
        self.frame.update_statusbar_and_messages()
        if success:
            self.frame.statusbar.SetStatusText(_('Export completed'))
        else:
            self.frame.statusbar.SetStatusText(_('Export failed'))

    def AbcToAbcCurrentTune(self, params):
        abc2abc_path = self.frame.settings['abc2abc_path'] # 1.3.6 [SS] 2014-11-12
        tune = self.frame.tune_list_controller.GetSelectedTune()
        if tune:
            trailing_space = tune.abc[-(len(tune.abc) - len(tune.abc.rstrip())):]
            (abc, error_msg) = AbcToAbc(tune.abc, self.frame.cache_dir, params, abc2abc_path)
            if abc is not None:
                self.frame.editor.BeginUndoAction()
                self.frame.editor.SetSelection(tune.offset_start, tune.offset_end)
                self.frame.editor.ReplaceSelection(abc.rstrip() + trailing_space)
                self.frame.editor.SetSelection(tune.offset_start, self.frame.editor.GetCurrentPos()-len(trailing_space))
                self.frame.editor.EndUndoAction()
            if error_msg:
                wx.MessageDialog(self.frame,
                                 _('abc2abc error/warnings: ') + os.linesep + error_msg,
                                 _('Abc2abc error message'), wx.OK | wx.CANCEL | wx.ICON_WARNING).ShowModal()

    def OnHalveL(self, evt):
        self.AbcToAbcCurrentTune(['-v'])
    def OnDoubleL(self, evt):
        self.AbcToAbcCurrentTune(['-d'])
    def OnTranspose(self, num_semitones):
        self.AbcToAbcCurrentTune(['-t', str(num_semitones)])
    def OnAlignBars(self, evt):
        tune = self.frame.tune_list_controller.GetSelectedTune()
        if not tune:
            return
        first_line = self.frame.editor.LineFromPosition(self.frame.editor.GetSelectionStart())
        last_line = self.frame.editor.LineFromPosition(self.frame.editor.GetSelectionEnd())
        # if not multiple lines are select, then apply the alignment to the whole tune
        if first_line == last_line:
            first_line = self.frame.editor.LineFromPosition(tune.offset_start)
            last_line = self.frame.editor.LineFromPosition(tune.offset_end)

        # find the lines and line numbers that should be affected by the alignment (eg. field lines like K: should be excluded)
        line_numbers = []
        lines = []
        for i in range(first_line, last_line+1):
            line = self.frame.editor.GetLine(i)
            if not re.match(r'[a-zA-Z]:', line) and not line.startswith('%') and line.strip():
                line_numbers.append(i)
                lines.append(line)

        # if there are more than two lines to align
        if len(lines) >= 2:
            # align the lines
            lines = align_lines(tune.abc, lines, True)

            # copy them back into the ABC editor
            self.frame.editor.BeginUndoAction()
            for (i, line) in zip(line_numbers, lines):
                p1, p2 = self.frame.editor.PositionFromLine(i), self.frame.editor.GetLineEndPosition(i)
                self.frame.editor.SetSelection(p1, p2)
                self.frame.editor.ReplaceSelection(line.rstrip())
            self.frame.editor.EndUndoAction()
