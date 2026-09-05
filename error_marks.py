"""Squiggle marks in the ABC editor for the diagnostics abc_parser.parse_abc() reports,
and the tooltip that explains the one under the mouse."""

import wx
import wx.stc as stc

from abc_parser import Severity
from appearance import current_appearance, ERROR_ICON, WARNING_ICON, ICON_GLYPH

# The indicator numbers the editor uses for parser diagnostics, one per severity
# so errors and warnings can carry different squiggle colours.
ERROR_INDICATOR = stc.STC_INDIC_CONTAINER
WARNING_INDICATOR = stc.STC_INDIC_CONTAINER + 1

SEVERITY_INDICATOR = {
    Severity.ERROR: ERROR_INDICATOR,
    Severity.WARNING: WARNING_INDICATOR,
}

# How long the mouse must rest over a mark before its explanation appears.
HOVER_DELAY_MS = 500

# The tooltip title and icon colour for each severity.
SEVERITY_PRESENTATION = {
    Severity.ERROR: ('Error', ERROR_ICON),
    Severity.WARNING: ('Warning', WARNING_ICON),
}

# Tooltip geometry, in pixels.
TIP_PADDING = 10
TIP_CORNER_RADIUS = 6
TIP_GAP = 4         # between the marked text and the tooltip
ICON_SIZE = 18
ICON_GAP = 8        # between the icon and the text
TITLE_GAP = 2       # between the title and the message

# Tooltip text is the system UI font scaled up by this factor.
TIP_FONT_SCALE = 1.25

# The exclamation mark inside a severity icon.
ICON_GLYPH_TEXT = '!'
GLYPH_FONT_SCALE = 0.9
GLYPH_TRIANGLE_DROP = 2     # pixels the glyph moves down to sit in the triangle's wide part


def diagnostic_span(line_text, position):
    """ Returns (offset_in_line, length) of the span in line_text that a SourcePosition marks.

    The excerpt is the rewritten row the parser saw; when it is found in the line the
    span starts at position.column inside it and covers the run of non-whitespace
    characters from there (at least one character). When it is not found, the whole
    line minus its line ending is marked.
    """
    excerpt_start = line_text.find(position.excerpt)
    if excerpt_start < 0:
        return 0, len(line_text.rstrip('\r\n'))
    start = excerpt_start + position.column
    end = start
    while end < len(line_text) and not line_text[end].isspace():
        end += 1
    return start, max(end - start, 1)


def span_at(spans, position):
    """ Returns the (start, end, diagnostic) span that holds the editor position, else None.

    The end is exclusive, matching the range IndicatorFillRange marks.
    """
    for span in spans:
        start, end, diagnostic = span
        if start <= position < end:
            return span
    return None


class ErrorMarks(object):
    """ Owns the squiggle indicator that shows parser diagnostics in the editor,
    and the tooltip that explains the mark under a resting mouse """
    def __init__(self, editor):
        self.editor = editor
        self.spans = []
        self.tip = DiagnosticTip(editor)
        editor.SetMouseDwellTime(HOVER_DELAY_MS)
        editor.Bind(stc.EVT_STC_DWELLSTART, self.on_dwell_start)
        editor.Bind(stc.EVT_STC_DWELLEND, self.on_dwell_end)

    def set_colors(self, error_color, warning_color):
        for indicator, color in ((ERROR_INDICATOR, error_color), (WARNING_INDICATOR, warning_color)):
            self.editor.IndicatorSetStyle(indicator, stc.STC_INDIC_SQUIGGLE)
            self.editor.IndicatorSetForeground(indicator, wx.Colour(color))

    def clear(self):
        editor = self.editor
        for indicator in SEVERITY_INDICATOR.values():
            editor.SetIndicatorCurrent(indicator)
            editor.IndicatorClearRange(0, editor.GetLength())
        self.spans = []
        self.tip.Hide()

    def apply(self, first_editor_line, header_line_count, diagnostics):
        self.clear()
        editor = self.editor
        line_count = editor.GetLineCount()
        for diagnostic in diagnostics:
            position = diagnostic.position
            if position is None:
                continue
            editor_line = first_editor_line + position.line - 1 - header_line_count
            # the tune may have been edited between the parse and this apply
            if not 0 <= editor_line < line_count:
                continue
            offset_in_line, length = diagnostic_span(editor.GetLine(editor_line), position)
            start = editor.PositionFromLine(editor_line) + offset_in_line
            editor.SetIndicatorCurrent(SEVERITY_INDICATOR[diagnostic.severity])
            editor.IndicatorFillRange(start, length)
            self.spans.append((start, start + length, diagnostic))

    def on_dwell_start(self, event):
        position = event.GetPosition()
        # the position is -1 when the mouse rests outside the text
        if position < 0:
            return
        span = span_at(self.spans, position)
        if span is None:
            return
        start, end, diagnostic = span
        editor = self.editor
        line = editor.LineFromPosition(start)
        below_span = editor.PointFromPosition(start)
        below_span.y += editor.TextHeight(line)
        self.tip.show(diagnostic, editor.ClientToScreen(below_span))

    def on_dwell_end(self, event):
        self.tip.Hide()


class DiagnosticTip(wx.PopupWindow):
    """ The popup explaining one diagnostic: a severity icon, a bold title, and the message.

    A plain popup never captures the mouse, so it coexists with the editor's own
    mouse handling; the editor's dwell events show and hide it.
    """
    def __init__(self, parent):
        super().__init__(parent, wx.BORDER_NONE)
        self.diagnostic = None
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self.on_paint)

    def show(self, diagnostic, screen_point):
        self.diagnostic = diagnostic
        title, _ = SEVERITY_PRESENTATION[diagnostic.severity]
        self.SetSize(self.layout_size(title, diagnostic.message))
        self.Position(screen_point, (0, TIP_GAP))
        self.Refresh()
        self.Show()

    def layout_size(self, title, message):
        dc = wx.ClientDC(self)
        dc.SetFont(title_font())
        title_width, title_height = dc.GetTextExtent(title)
        dc.SetFont(message_font())
        message_width, message_height = dc.GetTextExtent(message)
        text_width = max(title_width, message_width)
        width = TIP_PADDING + ICON_SIZE + ICON_GAP + text_width + TIP_PADDING
        height = TIP_PADDING + title_height + TITLE_GAP + message_height + TIP_PADDING
        return wx.Size(width, height)

    def on_paint(self, event):
        appearance = current_appearance()
        title, icon_color = SEVERITY_PRESENTATION[self.diagnostic.severity]
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(self.GetParent().GetBackgroundColour()))
        dc.Clear()
        gc = wx.GraphicsContext.Create(dc)
        width, height = self.GetClientSize()
        gc.SetBrush(wx.Brush(appearance.tooltip_background))
        gc.SetPen(wx.Pen(appearance.tooltip_border))
        # inset by half the pen so the border is not clipped at the window edge
        gc.DrawRoundedRectangle(0.5, 0.5, width - 1, height - 1, TIP_CORNER_RADIUS)
        draw_severity_icon(gc, self.diagnostic.severity, icon_color, TIP_PADDING, TIP_PADDING)
        text_x = TIP_PADDING + ICON_SIZE + ICON_GAP
        gc.SetFont(title_font(), appearance.tooltip_text)
        gc.DrawText(title, text_x, TIP_PADDING)
        _, title_height = gc.GetTextExtent(title)
        gc.SetFont(message_font(), appearance.tooltip_text)
        gc.DrawText(self.diagnostic.message, text_x, TIP_PADDING + title_height + TITLE_GAP)


def draw_severity_icon(gc, severity, color, x, y):
    """ A filled shape with a white exclamation mark: a red circle for an error,
    a yellow triangle for a warning. Drawn rather than taken from the art provider,
    whose warning glyph turns black on a dark appearance. """
    gc.SetPen(wx.TRANSPARENT_PEN)
    gc.SetBrush(wx.Brush(wx.Colour(color)))
    if severity is Severity.ERROR:
        gc.DrawEllipse(x, y, ICON_SIZE, ICON_SIZE)
    else:
        triangle = gc.CreatePath()
        triangle.MoveToPoint(x + ICON_SIZE / 2, y)
        triangle.AddLineToPoint(x + ICON_SIZE, y + ICON_SIZE)
        triangle.AddLineToPoint(x, y + ICON_SIZE)
        triangle.CloseSubpath()
        gc.FillPath(triangle)
    gc.SetFont(glyph_font(), wx.Colour(ICON_GLYPH))
    glyph_width, glyph_height = gc.GetTextExtent(ICON_GLYPH_TEXT)
    # the exclamation mark sits in the lower, wider part of the triangle
    glyph_y = y + (ICON_SIZE - glyph_height) / 2 + (0 if severity is Severity.ERROR else GLYPH_TRIANGLE_DROP)
    gc.DrawText(ICON_GLYPH_TEXT, x + (ICON_SIZE - glyph_width) / 2, glyph_y)


def message_font():
    return wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT).Scaled(TIP_FONT_SCALE)


def title_font():
    return message_font().Bold()


def glyph_font():
    return wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT).Bold().Scaled(GLYPH_FONT_SCALE)
