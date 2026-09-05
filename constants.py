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

import sys
import os
import codecs
import re
import wx
from utils import get_application_path

program_version = '1.3.8.7'
program_name = 'EasyABC ' + program_version

abcm2ps_default_encoding = 'utf-8'  ## 'latin-1'
utf8_byte_order_mark = codecs.BOM_UTF8  # chr(0xef) + chr(0xbb) + chr(0xbf) #'\xef\xbb\xbf'

max_int = sys.maxsize

WX4 = wx.version().startswith('4')

application_path = get_application_path()

cwd = os.getenv('EASYABCDIR')
if not cwd:
    cwd = application_path

sys.path.append(cwd)

control_margin = 6

default_midi_volume = 96
default_midi_pan = 64
default_midi_instrument = 0

line_end_re = re.compile('\r\n|\r|\n')
tune_index_re = re.compile(r'^X:\s*(\d+)')
