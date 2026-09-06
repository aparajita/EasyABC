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

"""Emacs-style caret movement and word deletion in the editor on macOS.

Cocoa gives every native text view these bindings, but Scintilla draws and
handles its own text area, so the editor only has them if it implements them.
"""

import wx
import wx.stc as stc

COMMAND = 'command'
CONTROL = 'control'
OPTION = 'option'

# wx reports Command as Meta on macOS, so RawControlDown() and AltDown() are the
# physical Control and Option keys.
_MODIFIER_TESTS = [
    (COMMAND, wx.KeyEvent.CmdDown),
    (CONTROL, wx.KeyEvent.RawControlDown),
    (OPTION, wx.KeyEvent.AltDown),
]

# Option-F stops at the end of the next word and Option-B at the start of the
# previous one, which is where both Emacs and Cocoa put the caret. Each Emacs
# key names the same command as the arrow key it stands in for.
_COMMANDS = {
    (COMMAND, wx.WXK_LEFT): stc.StyledTextCtrl.Home,
    (COMMAND, wx.WXK_RIGHT): stc.StyledTextCtrl.LineEnd,
    (COMMAND, wx.WXK_UP): stc.StyledTextCtrl.DocumentStart,
    (COMMAND, wx.WXK_DOWN): stc.StyledTextCtrl.DocumentEnd,
    (CONTROL, ord('A')): stc.StyledTextCtrl.Home,
    (CONTROL, ord('E')): stc.StyledTextCtrl.LineEnd,
    (CONTROL, ord('P')): stc.StyledTextCtrl.LineUp,
    (CONTROL, ord('N')): stc.StyledTextCtrl.LineDown,
    (CONTROL, ord('F')): stc.StyledTextCtrl.CharRight,
    (CONTROL, ord('B')): stc.StyledTextCtrl.CharLeft,
    (OPTION, ord('F')): stc.StyledTextCtrl.WordRightEnd,
    (OPTION, ord('B')): stc.StyledTextCtrl.WordLeft,
    (OPTION, wx.WXK_BACK): stc.StyledTextCtrl.DelWordLeft,
    (OPTION, wx.WXK_DELETE): stc.StyledTextCtrl.DelWordRightEnd,
}


def bind_editor_keys(editor):
    """Give `editor` the bindings, on the platform whose users expect them."""
    if wx.Platform == '__WXMAC__':
        editor.Bind(wx.EVT_KEY_DOWN, _on_key_down)


def _modifier(evt):
    """The lone modifier held down, or None for any other combination."""
    if evt.ShiftDown():
        return None
    held = [name for name, is_down in _MODIFIER_TESTS if is_down(evt)]
    if len(held) == 1:
        return held[0]
    return None


def _on_key_down(evt):
    command = _COMMANDS.get((_modifier(evt), evt.GetKeyCode()))
    if command is None:
        evt.Skip()
    else:
        # Not skipping keeps Scintilla from also acting on the key, and keeps
        # the character Option produces (ƒ, ∫) from reaching the editor.
        command(evt.GetEventObject())
