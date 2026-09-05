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

class AppState(object):
    """Process-wide mutable state shared by the frame, the converters and the worker threads."""
    def __init__(self):
        self.messages = u''          # accumulated stdout/stderr of external tools, shown in MyInfoFrame
        self.visible_abc_code = u''  # the ABC last handed to abcm2ps or abc2midi, shown in MyAbcFrame
        self.running = True          # False once the main loop has exited; worker threads poll it

app_state = AppState()
