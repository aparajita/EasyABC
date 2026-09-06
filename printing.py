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

import platform

import wx
from wx import GetTranslation as _

from abc_tools import AbcToSvg
from appearance import PRINT_INK
from constants import WX4
from svgrenderer import SvgRenderer
from wxhelper import wx_bitmap

_print_data = None


def _get_print_data():
    global _print_data
    if _print_data is None:
        _print_data = wx.PrintData()
        _print_data.SetPrintMode(wx.PRINT_MODE_PRINTER)
    return _print_data


def OnPageSetup(frame, evt):
    global _print_data
    psdd = wx.PageSetupDialogData(_get_print_data())
    if not WX4:
        psdd.CalculatePaperSizeFromId()
    if platform.system() == 'Windows':
        psdd.EnableMargins(False)

    dlg = wx.PageSetupDialog(frame, psdd)
    try:
        dlg.ShowModal()

        # this makes a copy of the wx.PrintData instead of just saving
        # a reference to the one inside the PrintDialogData that will
        # be destroyed when the dialog is destroyed
        _print_data = wx.PrintData(dlg.GetPageSetupData().GetPrintData())
    finally:
        dlg.Destroy() # 1.3.6.3 [JWDJ] 2015-04-21 always clean up dialog window


def OnPrint(frame, event):
    print_or_preview_svg(frame, only_preview=False)


def OnPrintPreview(frame, event):
    print_or_preview_svg(frame, only_preview=True)


def print_or_preview_svg(frame, only_preview):
    global _print_data
    tunes = frame.tune_list_controller.GetSelectedTunes()
    if len(tunes) == 0:
        return
    # if landscape is set in the ABC code, let that influence the page format
    abc = u''
    header = None
    title = None
    for tune in tunes:
        abc += tune.abc
        if header is None:
            header = tune.header
        if title is None:
            title = tune.title
    fullabc = header + abc
    print_data = _get_print_data()
    if '%%landscape 1' in fullabc or '%%landscape true' in fullabc:
        print_data.SetOrientation(wx.LANDSCAPE)
    if '%%landscape 0' in fullabc or '%%landscape false' in fullabc:
        print_data.SetOrientation(wx.PORTRAIT)
    use_landscape = print_data.GetOrientation() == wx.LANDSCAPE

    # 1.3.6 [SS] 2014-12-02  2014-12-07
    svg_files, error = AbcToSvg(abc, header, frame.cache_dir,
                                frame.settings,
                                minimal_processing=True,
                                landscape=use_landscape)
    frame.update_statusbar_and_messages()
    if svg_files:
        pdd = wx.PrintDialogData(print_data)
        printout = MusicPrintout(svg_files, zoom=10.0, title=title, can_draw_sharps_and_flats=frame.settings['can_draw_sharps_and_flats'])
        if only_preview:
            printout_for_preview = MusicPrintout(svg_files, zoom=1.0, title=title, painted_on_screen=True, can_draw_sharps_and_flats=frame.settings['can_draw_sharps_and_flats'])
            frame.preview = wx.PrintPreview(printout_for_preview, printout, pdd)

            if wx.Platform == "__WXMAC__":
                frame.preview.SetZoom(100)

            if WX4:
                if not frame.preview.IsOk:
                    return
            else:
                if not frame.preview.Ok():
                    return

            pfrm = wx.PreviewFrame(frame.preview, frame, _("EasyABC - print preview"))

            pfrm.Initialize()
            pfrm.SetPosition(frame.GetPosition())
            pfrm.SetSize(frame.GetSize())
            pfrm.Show(True)
        else:
            #pdd.SetToPage(len(svg_files))
            printer = wx.Printer(pdd)
            if printer.Print(frame, printout, True):
                _print_data = wx.PrintData(printer.GetPrintDialogData().GetPrintData())
            else:
                wx.MessageBox(_("There was a problem printing.\nPerhaps your current printer is not set correctly?"), _("Printing"), wx.OK)


class MusicPrintout(wx.Printout):
    def __init__(self, svg_files, zoom=1.0, title=None, painted_on_screen=False, can_draw_sharps_and_flats=True):
        wx.Printout.__init__(self, title=title or _('EasyABC music'))
        self.can_draw_sharps_and_flats = can_draw_sharps_and_flats
        self.svg_files = svg_files
        self.zoom = zoom
        self.painted_on_screen = painted_on_screen

    def HasPage(self, page):
        return page <= len(self.svg_files)

    def GetPageInfo(self):
        minPage = 1
        maxPage = len(self.svg_files)
        fromPage, toPage = minPage, maxPage
        return (minPage, maxPage, fromPage, toPage)

    def OnPrintPage(self, page_no):
        dc = self.GetDC()

        #-------------------------------------------
        # One possible method of setting scaling factors...

        svg = open(self.svg_files[page_no-1], 'rb').read()
        #new versions of abcm2ps adds a suffix 'in' to width and height
        #new versions of abcm2ps adds a suffix 'px' to width and height
        # 1.3.7.3 [JWDJ] use svg renderer to calculate width and height
        renderer = SvgRenderer(self.can_draw_sharps_and_flats, highlight_color=PRINT_INK)
        try:
            page = renderer.svg_to_page(svg)

            width = page.svg_width
            height = page.svg_height

            maxX = width
            maxY = height

            # Let's have at least 0 device units margin
            marginX = 0
            marginY = 0

            # Add the margin to the graphic size
            maxX += 2 * marginX
            maxY += 2 * marginY

            # Get the size of the DC in pixels
            (w, h) = dc.GetSize()

            # Calculate a suitable scaling factor
            scaleX = float(w) / maxX
            scaleY = float(h) / maxY

            # Use x or y scaling factor, whichever fits on the DC
            actualScale = min(scaleX, scaleY)

            # Calculate the position on the DC for centering the graphic
            posX = (w - (width * actualScale)) / 2.0
            #posY = (h - (height * actualScale)) / 2.0
            posY = 0

            # Set the scale and origin
            dc.SetUserScale(actualScale, actualScale)
            dc.SetDeviceOrigin(int(posX), int(posY))

            #-------------------------------------------
            if wx.Platform in ("__WXMSW__", "__WXMAC__") and (not self.painted_on_screen or True):
                # special case for windows since it doesn't support creating a GraphicsContext from a PrinterDC:
                dc.SetUserScale(actualScale/self.zoom, actualScale/self.zoom)
                renderer.zoom = self.zoom
                if self.painted_on_screen:
                    # a PrinterDC that cannot back a GraphicsContext gets the page as a bitmap
                    bitmap = wx_bitmap(int(page.svg_width * self.zoom), int(page.svg_height * self.zoom), 32)
                    renderer.draw(page, wx.MemoryDC(bitmap))
                    dc.DrawBitmap(bitmap, 0, 0)
                else:
                    renderer.draw(page, dc)
            else:
                renderer.zoom = 1.0
                renderer.draw(page, dc)
        finally:
            renderer.destroy()
        return True
