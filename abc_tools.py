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
import subprocess
import sys
import webbrowser

import wx
from wx import GetTranslation as _

from abc_character_encoding import ensure_unicode
from abc_transform import process_abc_code
from app_state import app_state
from constants import cwd, abcm2ps_default_encoding
from dialogs import MyMidiTextTree
from exceptions import Abcm2psException, NWCConversionException
from tool_run import ABCM2PS, ABC2ABC, MIDI2ABC, NWC2XML, GHOSTSCRIPT, get_output_from_process

if wx.Platform == "__WXMSW__":
    import win32process


# Locations searched when gs is not on PATH. An app bundle launched from Finder
# inherits the bare login PATH, which contains neither Homebrew prefix.
gs_search_paths = ['/opt/homebrew/bin/gs', '/usr/local/bin/gs', '/opt/local/bin/gs', '/usr/bin/gs']


def start_process(cmd):
    """ Starts a process
    :param cmd: tuple containing executable and command line parameter
    :return: nothing
    """
    # 1.3.6.4 [SS] 2015-05-01
    if wx.Platform == "__WXMSW__":
        creationflags = win32process.DETACHED_PROCESS
    else:
        creationflags = 0
    # 1.3.6.4 [SS] 2015-05-27
    #process = subprocess.Popen(cmd,shell=False,stdin=None,stdout=subprocess.PIPE,stderr=subprocess.PIPE,close_fds=True,creationflags=creationflags)
    process = subprocess.Popen(cmd, shell=False, stdin=None, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creationflags)
    stdout_value, stderr_value = process.communicate()
    app_state.messages += '\n' + (stderr_value + stdout_value).decode('utf-8', 'replace')
    return


def show_in_browser(url):
    handle = webbrowser.get()
    handle.open(url)


def launch_file(filepath):
    ''' open the given document using its associated program '''
    if wx.Platform == "__WXMSW__":
        os.startfile(filepath)
    elif wx.Platform == "__WXMAC__":
        subprocess.call(('open', filepath))
    elif os.name == 'posix':
        subprocess.call(('xdg-open', filepath))
    return True


def get_default_path_for_executable(name):
    if wx.Platform == "__WXMSW__":
        exe_name = '{0}.exe'.format(name)
    else:
        exe_name = name

    path = os.path.join(cwd, 'bin', exe_name)
    if wx.Platform == "__WXGTK__":
        if not os.path.exists(path):
            path = '/usr/local/bin/{0}'.format(name)
        if not os.path.exists(path):
            path = '/usr/bin/{0}'.format(name)

    return path


def get_ghostscript_path():
    ''' Fetches the ghostscript path from the windows registry and returns it.
        This function may not see the 64-bit ghostscript installations, especially
        if Python was compiled as a 32-bit application.
    '''
    if sys.version_info >= (3,0,0):
        import winreg
    else:
        import _winreg as winreg

    available_versions = []
    for reg_key_name in [r"SOFTWARE\\GPL Ghostscript", r"SOFTWARE\\GNU Ghostscript"]:
        try:
            aReg = winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE)
            aKey = winreg.OpenKey(aReg, reg_key_name)
            for i in range(100):
                try:
                    version = winreg.EnumKey(aKey, i)
                    bKey = winreg.OpenKey(aReg, reg_key_name + "\\%s" % version)
                    value, _ = winreg.QueryValueEx(bKey, 'GS_DLL')
                    winreg.CloseKey(bKey)
                    path = os.path.join(os.path.dirname(value), 'gswin32c.exe')
                    if os.path.exists(path):
                        available_versions.append((version, path))
                    path = os.path.join(os.path.dirname(value), 'gswin64c.exe')
                    if os.path.exists(path):
                        available_versions.append((version, path))
                except EnvironmentError:
                    break
            winreg.CloseKey(aKey)
        except:
            pass
    if available_versions:
        return sorted(available_versions)[-1][1]   # path to the latest version
    else:
        return None


def find_ps_to_pdf_converter():
    ''' Returns the path of a PostScript-to-PDF converter, or '' if there is none.
        Windows keeps ghostscript in the registry; elsewhere it is an executable
        on PATH or in one of the usual package-manager prefixes. macOS shipped
        /usr/bin/pstopdf up to Ventura and can still use it as a last resort.
    '''
    if wx.Platform == "__WXMSW__":
        return get_ghostscript_path() or ''

    try:
        path = subprocess.check_output(["which", "gs"]).decode().strip()
        if path:
            return path
    except Exception:
        pass

    for path in gs_search_paths:
        if os.path.exists(path):
            return path

    if wx.Platform == "__WXMAC__" and os.path.exists('/usr/bin/pstopdf'):
        return '/usr/bin/pstopdf'

    return ''


def add_abcm2ps_options(cmd, extra_params, abcm2ps_format_path):
    ''' appends the user's extra abcm2ps parameters and format file to an abcm2ps command line '''
    if extra_params:
        # split extra_params on spaces, but treat quoted strings as one element even if they contain spaces
        cmd = cmd + [x or y for (x, y) in re.findall(r'"(.+?)"|(\S+)', extra_params)]
    if abcm2ps_format_path and not '-F' in cmd:
        # strip .fmt file ending
        if abcm2ps_format_path.lower().endswith('.fmt'):
            abcm2ps_format_path = abcm2ps_format_path[:-4]
        cmd = cmd + ['-F', abcm2ps_format_path]
    return cmd


def AbcToPS(abc_code, cache_dir, extra_params='', abcm2ps_path=None, abcm2ps_format_path=None):
    ''' converts from abc to postscript. Returns the path of the postscript file, or None if the creation was not successful '''
    # hash_code = get_hash_code(abc_code, read_text_if_file_exists(abcm2ps_format_path))
    ps_file = os.path.abspath(os.path.join(cache_dir, 'temp.ps'))

    # determine parameters
    cmd1 = [abcm2ps_path, '-', '-O', '%s' % ps_file]
    cmd1 = add_abcm2ps_options(cmd1, extra_params, abcm2ps_format_path)

    if os.path.exists(ps_file):
        os.remove(ps_file)

    input_abc = abc_code + os.linesep * 2
    ABCM2PS.run(cmd1, input=input_abc, encoding=abcm2ps_default_encoding)
    if not os.path.exists(ps_file):
        return None
    return ps_file


def GetSvgFileList(first_page_file_path):
    ''' given 'file001.svg' this function will return all existing files in the series, eg. ['file001.svg', 'file002.svg'] '''
    result = []
    for i in range(1, 1000):
        fn = first_page_file_path.replace('001.svg', '%.3d.svg' % i)
        if os.path.exists(fn):
            result.append(fn)
        else:
            break
    return result


def abc_to_svg(abc_code, cache_dir, settings, target_file_name=None, with_annotations=True, one_file_per_page=True):
    """ converts from abc to svg. Returns (svg_files, severity) tuple, where svg_files is an empty list if the creation was not successful and severity is the Severity of the abcm2ps run """
    # 1.3.6.3 [SS] 2015-05-01
    abcm2ps_path = settings.get('abcm2ps_path', '')
    abcm2ps_format_path = settings.get('abcm2ps_format_path', '')
    extra_params = settings.get('abcm2ps_extra_params', '')
    # 1.3.6.3 [SS] 2015-05-01
    app_state.visible_abc_code = abc_code

    if target_file_name:
        svg_file = target_file_name
    else:
        #grab svg file from cache if it exists
        #svg_file = os.path.abspath(os.path.join(cache_dir, 'temp_%s.svg' % hash)) # 1.3.6 [SS] 2014-11-13
        svg_file = os.path.abspath(os.path.join(cache_dir, 'temp.svg')) # 1.3.6 [SS] 2014-11-13

        #if os.path.exists(svg_file_first):  p09 disable cache
            #return (GetSvgFileList(svg_file_first), '')

    svg_file_first = svg_file.replace('.svg', '001.svg')

    # determine parameters
    cmd1 = [abcm2ps_path, '-', '-O', '%s' % os.path.basename(svg_file)]
    if one_file_per_page:
        cmd1 = cmd1 + ['-v']
    else:
        cmd1 = cmd1 + ['-g']

    if with_annotations:
        cmd1 = cmd1 + ['-A']

    cmd1 = add_abcm2ps_options(cmd1, extra_params, abcm2ps_format_path)

    # 1.3.6 [SS] 2014-11-16
    # clear out all 001.svg, 002.svg and etc. so pages of a longer earlier
    # tune do not pass for pages of this one
    for f in GetSvgFileList(svg_file_first):
        os.remove(f)

    #fse = sys.getfilesystemencoding()
    #cmd1 = [arg.encode(fse) if isinstance(arg,unicode) else arg for arg in cmd1]

    # clear app_state.messages any time the music panel is refreshed
    app_state.messages = u''
    input_abc = abc_code + os.linesep * 2
    run = ABCM2PS.run(cmd1, input=input_abc, encoding=abcm2ps_default_encoding, bufsize=-1, cwd=os.path.dirname(svg_file))

    if run.returncode < 0:
        raise Abcm2psException('Unknown error - abcm2ps may have crashed')
    return GetSvgFileList(svg_file_first), run.severity


def AbcToSvg(abc_code, header, cache_dir, settings, target_file_name=None, with_annotations=True, minimal_processing=False, landscape=False, one_file_per_page=True):
    """ preprocesses abc_code and converts it to svg. Returns the (svg_files, severity) tuple of abc_to_svg unchanged """
    # 1.3.6 [SS] 2014-12-17
    abc_code = process_abc_code(settings, abc_code, header, minimal_processing=minimal_processing, landscape=landscape)
    #hash = get_hash_code(abc_code, read_text_if_file_exists(abcm2ps_format_path), str(with_annotations)) # 1.3.6 [SS] 2014-11-13
    return abc_to_svg(abc_code, cache_dir, settings, target_file_name, with_annotations, one_file_per_page)


def AbcToAbc(abc_code, cache_dir, params, abc2abc_path=None):
    ' converts from abc to abc. Returns (abc_code, error_message) tuple, where abc_code is None if abc2abc was not successful'

    abc_code = re.sub(r'\\"', '', abc_code)  # remove escaped quote characters, since abc2abc cannot handle them

    # determine parameters
    cmd1 = [abc2abc_path, '-', '-r', '-b', '-e'] + params

    input_abc = abc_code + os.linesep * 2
    run = ABC2ABC.run(cmd1, bufsize=-1, input=input_abc, encoding=abcm2ps_default_encoding)

    stderr_value = run.stderr.strip()
    if run.returncode == 0:
        return run.stdout, stderr_value
    else:
        return None, stderr_value


def MidiToMftext(midi2abc_path, midifile):
    ' dissasemble midi file to text using midi2abc'
    cmd1 = [midi2abc_path, midifile, '-mftext']

    if os.path.exists(midi2abc_path):
        run = MIDI2ABC.run(cmd1, bufsize=-1)
        midiframe = MyMidiTextTree(_('Disassembled Midi File'))
        midiframe.Show(True)
        midi_lines = run.stdout.splitlines()
        midiframe.LoadMidiData(midi_lines)
    else:
        wx.MessageBox(_("Cannot find the executable midi2abc. Be sure it is in your bin folder and its path is defined in ABC Setup/File Settings."), _("Error"), wx.ICON_ERROR | wx.OK)


def get_midi_structure_as_text(midi2abc_path, midi_file):
    result = u''
    if os.path.exists(midi2abc_path):
        cmd = [midi2abc_path, midi_file, '-mftext']
        result, stderr_value, returncode = get_output_from_process(cmd, bufsize=-1)
    return result


def AbcToPDF(settings, abc_code, header, cache_dir, extra_params='', abcm2ps_path=None, gs_path=None, abcm2ps_format_path=None):
    pdf_file = os.path.abspath(os.path.join(cache_dir, 'temp.pdf'))
    # 1.3.6 [SS] 2014-12-17
    abc_code = process_abc_code(settings, abc_code, header, minimal_processing=True)
    ps_file = AbcToPS(abc_code, cache_dir, extra_params, abcm2ps_path, abcm2ps_format_path)
    if not ps_file:
        return None

    gs_path = ensure_unicode(gs_path)

    # convert ps to pdf
    # p09 we already checked for gs_path in restore_settings() 2014-10-14
    cmd2 = [gs_path, '-sDEVICE=pdfwrite', '-sOutputFile=%s' % pdf_file, '-dBATCH', '-dNOPAUSE', ps_file]
    #FAU:PDF:Manage the case where one put ps2pdf from ghostscript instead of gs directly
    if 'ps2pdf' in gs_path:
        cmd2 = [gs_path, ps_file, pdf_file]
    elif gs_path == '/usr/bin/pstopdf':
        cmd2 = [gs_path, ps_file, '-o', pdf_file]
    if os.path.exists(pdf_file):
        os.remove(pdf_file)

    GHOSTSCRIPT.run(cmd2)
    if os.path.exists(pdf_file):
        return pdf_file


def NWCToXml(filepath, cache_dir, nwc2xml_path):
    nwc_file_path = os.path.join(cache_dir, 'temp_nwc.nwc')
    xml_file_path = os.path.join(cache_dir, 'temp_nwc.xml')
    if os.path.exists(xml_file_path):
        os.remove(xml_file_path)
    shutil.copy(filepath, nwc_file_path)

    if not nwc2xml_path:
        if wx.Platform == "__WXMSW__":
            nwc2xml_path = os.path.join(cwd, 'bin', 'nwc2xml.exe')
        elif wx.Platform == "__WXMAC__":
            nwc2xml_path = os.path.join(cwd, 'bin', 'nwc2xml')
        else:
            nwc2xml_path = 'nwc2xml'

    #cmd = [nwc2xml_path, '--charset=ISO-8859-1', nwc_file_path]
    cmd = [nwc2xml_path, nwc_file_path]
    run = NWC2XML.run(cmd)

    if not os.path.exists(xml_file_path) or run.returncode != 0:
        stderr_value = run.stderr.replace(os.path.dirname(nwc_file_path) + os.sep, '')  # simply any reference to the file path in the error message
        raise NWCConversionException(_('Error during conversion of %(filename)s: %(error)s' % {'filename': os.path.basename(filepath), 'error': stderr_value}))
    return xml_file_path
