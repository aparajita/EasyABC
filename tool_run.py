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
"""Running the external programs EasyABC depends on and reading what they print.

Every external tool is an `ExternalTool` constant defined at the bottom of this
module. `ExternalTool.run` logs the command and its output to `app_state.messages`
and returns a `ToolRun`, whose `severity` grades the run for the status bar.
"""
import re
import subprocess
from dataclasses import dataclass
from enum import Enum
from functools import cached_property
from typing import Callable, List

import wx
from wx import GetTranslation as _

from abc_parser import Severity
from app_state import app_state

if wx.Platform == "__WXMSW__":
    import win32process


class Diagnostics(Enum):
    """Which of a tool's output streams carry diagnostics EasyABC logs.

    - `BOTH_STREAMS`: the tool writes its result to a file named on its command
      line, so everything it prints is diagnostics.
    - `STDERR_ONLY`: the tool writes its result to stdout, so stdout must never
      reach `app_state.messages`.
    - `NONE`: the tool's printed output is progress chatter rather than
      diagnostics, so only its exit code is read and nothing it prints is logged.
    """
    BOTH_STREAMS = 'both_streams'
    STDERR_ONLY = 'stderr_only'
    NONE = 'none'


def get_output_from_process(cmd, input=None, creationflags=None, cwd=None, bufsize=0, encoding='utf-8', errors='strict', output_encoding=None):
    stdin_pipe = None
    if input is not None:
        stdin_pipe = subprocess.PIPE
        if isinstance(input, str):
            input = input.encode(encoding, errors)

    if creationflags is None:
        if wx.Platform == "__WXMSW__":
            creationflags = win32process.CREATE_NO_WINDOW
        else:
            creationflags = 0

    process = subprocess.Popen(cmd, stdin=stdin_pipe, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creationflags, cwd=cwd, bufsize=bufsize)
    stdout_value, stderr_value = process.communicate(input)
    returncode = process.returncode

    if output_encoding is None:
        output_encoding = encoding
    stdout_value, stderr_value = stdout_value.decode(output_encoding, errors), stderr_value.decode(output_encoding, errors)
    return stdout_value, stderr_value, returncode


def abnormal_exit_message(program, returncode):
    """The message for a process killed by a signal, not for a tool that exited non-zero because it found a fault in the tune."""
    return _('%(program)s exited abnormally (errorcode %(error)#8x)') % {'program': program, 'error': returncode & 0xffffffff}


def status_text_for(tool, severity):
    """The status bar line for a run of `tool` that reached `severity`.

    `''` for `Severity.INFO`, so a clean run leaves the status bar blank.
    """
    if severity is Severity.WARNING:
        return _('{0} reported some warnings').format(tool.name)
    if severity is Severity.ERROR:
        return _('{0} reported some errors').format(tool.name)
    return ''


def _highest_severity(severities):
    """The most severe member of `severities`; `Severity.INFO` when it is empty.

    `Severity` is a plain `Enum` with no ordering, so this compares by identity
    rather than using `max`.
    """
    highest = Severity.INFO
    for severity in severities:
        if severity is Severity.ERROR:
            return Severity.ERROR
        if severity is Severity.WARNING:
            highest = Severity.WARNING
    return highest


def no_line_diagnostics(line):
    """For a tool whose printed lines nothing grades: every line is INFO, so such a run's severity reflects only its exit status."""
    return Severity.INFO


@dataclass(frozen=True)
class ExternalTool:
    """An external program EasyABC runs, plus what is needed to read what it prints.

    `name` is the user-facing program name, written into `app_state.messages`
    and the status bar. `diagnostics` says which of its output streams carry
    diagnostics. `severity_of_line` maps one printed line to a `Severity`; a
    tool that names none has nothing grading its lines, so its runs take their
    severity from the exit code alone.

    Instances are the module-level constants at the bottom of this module; no
    other instance should be constructed.
    """
    name: str
    diagnostics: Diagnostics
    severity_of_line: Callable[[str], Severity] = no_line_diagnostics

    def run(self, cmd, **kwargs):
        """Run the tool and log the run to `app_state.messages`.

        Preconditions: `cmd` is the argument list, executable first; `**kwargs`
        are passed through to `get_output_from_process` unchanged.

        Appends to `app_state.messages`, in this order:

        1. `'\\n' + self.name + '\\n' + ' '.join(cmd)`, before the process starts;
        2. `'\\n' + run.diagnostic_text`, the diagnostic lines the tool printed,
           which is empty for a `Diagnostics.NONE` tool;
        3. `'\\n' + abnormal_exit_message(self.name, returncode)`, only when
           `returncode < 0`, that is, when the process was killed by a signal.
           A tool that exits non-zero because it found a fault in the tune has
           already said so in its diagnostic lines.

        Appends but never clears `app_state.messages`; a caller that wants a
        fresh log assigns `app_state.messages = u''` itself before calling.

        Never raises for a non-zero return code: the return code reaches the
        caller through the `ToolRun` it returns, whose `severity` is
        `Severity.ERROR` for any non-zero code.
        """
        app_state.messages += '\n' + self.name + '\n' + " ".join(cmd)
        stdout_value, stderr_value, returncode = get_output_from_process(cmd, **kwargs)
        run = ToolRun(self, stdout_value, stderr_value, returncode)
        app_state.messages += '\n' + run.diagnostic_text
        if returncode < 0:
            app_state.messages += '\n' + abnormal_exit_message(self.name, returncode)
        return run


@dataclass(frozen=True)
class ToolRun:
    """What one run of an `ExternalTool` printed and how it exited.

    `stdout` and `stderr` are the complete decoded streams; which of them are
    diagnostics is decided by `tool.diagnostics`, and `diagnostic_lines`,
    `diagnostic_text` and `severity` are derived from that.
    """
    tool: ExternalTool
    stdout: str
    stderr: str
    returncode: int

    @cached_property
    def diagnostic_lines(self) -> List[str]:
        """The non-empty lines the tool printed as diagnostics.

        stdout then stderr when `tool.diagnostics is Diagnostics.BOTH_STREAMS`,
        stderr only when it is `Diagnostics.STDERR_ONLY`, and empty when it is
        `Diagnostics.NONE`.
        """
        if self.tool.diagnostics is Diagnostics.BOTH_STREAMS:
            text = self.stdout + self.stderr
        elif self.tool.diagnostics is Diagnostics.STDERR_ONLY:
            text = self.stderr
        else:
            text = ''
        return [line for line in text.splitlines() if line.strip()]

    @property
    def diagnostic_text(self) -> str:
        """`diagnostic_lines` rejoined, as written to `app_state.messages`."""
        return '\n'.join(self.diagnostic_lines)

    @property
    def severity(self) -> Severity:
        """The severity of the run as a whole.

        The highest of `tool.severity_of_line(line)` over `diagnostic_lines`,
        and `Severity.ERROR` when `returncode != 0` regardless of what the lines
        say. This is total: there is no "no severity" case, and `Severity.INFO`
        is what a clean run — no diagnostic lines, return code 0 — reports, so
        no caller needs a `None` check.
        """
        if self.returncode != 0:
            return Severity.ERROR
        return _highest_severity(self.tool.severity_of_line(line) for line in self.diagnostic_lines)


# The prefixes abc2midi writes in front of a diagnostic, as in
# 'Error in line-char 3-0 : ...' and 'Warning in line-char 7-1 : ...'.
ABC2MIDI_ERROR_PREFIX = 'Error'
ABC2MIDI_WARNING_PREFIX = 'Warning'

# 'Warning in line-char 7-1 : instruction !fall! ignored'
IGNORED_INSTRUCTION_RE = re.compile(r'instruction\s+!.*?!\s+ignored')

# 'stdin:8:11: error: Bad length divisor', 'stdin:6:16: warning: Line underfull (365pt of 682pt)'
ABCM2PS_DIAGNOSTIC_RE = re.compile(r'^.*?:\d+:\d+: (?P<severity>error|warning): ')


def abc2midi_line_severity(line):
    """The severity of one line abc2midi printed.

    - A line reporting an ignored instruction (`instruction !X! ignored`) is
      INFO for every X. abc2midi acts on 20 decorations and ignores the rest;
      that a decoration has no playback meaning in this binary is not a fault
      in the tune.
    - A line starting with `Error` is ERROR.
    - A line starting with `Warning` is WARNING.
    - Anything else — the version banner, `writing MIDI file ...` — is INFO.
    """
    if IGNORED_INSTRUCTION_RE.search(line):
        return Severity.INFO
    if line.startswith(ABC2MIDI_ERROR_PREFIX):
        return Severity.ERROR
    if line.startswith(ABC2MIDI_WARNING_PREFIX):
        return Severity.WARNING
    return Severity.INFO


def abcm2ps_line_severity(line):
    """The severity of one line abcm2ps printed.

    A line of the form `<file>:<line>:<col>: error: ...` is ERROR and
    `<file>:<line>:<col>: warning: ...` is WARNING. Every line that does not
    match — the version banner, `File stdin`, `Output written on ...`, and the
    source-excerpt and caret continuation lines that follow an error — is INFO.
    """
    match = ABCM2PS_DIAGNOSTIC_RE.match(line)
    if match is None:
        return Severity.INFO
    if match.group('severity') == 'error':
        return Severity.ERROR
    return Severity.WARNING


ABCM2PS     = ExternalTool('Abcm2ps',     Diagnostics.BOTH_STREAMS, abcm2ps_line_severity)
ABC2MIDI    = ExternalTool('Abc2midi',    Diagnostics.BOTH_STREAMS, abc2midi_line_severity)
ABC2ABC     = ExternalTool('Abc2abc',     Diagnostics.STDERR_ONLY)
MIDI2ABC    = ExternalTool('Midi2abc',    Diagnostics.STDERR_ONLY)
NWC2XML     = ExternalTool('Nwc2xml',     Diagnostics.BOTH_STREAMS)
GHOSTSCRIPT = ExternalTool('Ghostscript', Diagnostics.BOTH_STREAMS)
FFMPEG      = ExternalTool('Ffmpeg',      Diagnostics.NONE)
