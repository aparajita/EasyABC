"""Single source of every colour the application draws with.

Colours follow the system appearance, so nothing outside this module names a
hex value or asks ``wx.SystemSettings`` for a colour.
"""

import wx


WHITE = '#FFFFFF'
BLACK = '#000000'

SCORE_COLOR = '#FFFDF0'

# Printing and export ignore the user's paper colour: paper output is always
# black ink on white.
PRINT_PAPER = WHITE
PRINT_INK = BLACK

# Diagnostic tooltip icons keep their colour on both appearances.
ERROR_ICON = '#E5484D'
WARNING_ICON = '#F5C518'
ICON_GLYPH = WHITE

DEFAULT_NOTE_HIGHLIGHT = '#FF7F3F'
DEFAULT_NOTE_HIGHLIGHT_FOLLOW = '#CC00FF'

# The mouse drag rectangle in the score pane is filled before the score is
# drawn over it, so a pale fill keeps the score readable while marking the
# area on any paper colour.
SCORE_DRAG_RECT_FILL = '#FFFBC6'
SCORE_DRAG_RECT_BORDER = BLACK

# Token colours are Night Owl (Sarah Drasner), mapped by ABC role to the
# theme's TextMate scopes: fields are keywords, field values and quoted
# strings are strings, bars are operators, the X: index is a heading.
LIGHT_STYLE_PALETTE = {
    'style_default_color': '#403F53',
    'style_chord_color': '#4876D6',
    'style_comment_color': '#989FB1',
    'style_specialcomment_color': '#4876D6',
    'style_bar_color': '#0C969B',
    'style_field_color': '#994CC3',
    'style_fieldvalue_color': '#4876D6',
    'style_embeddedfield_color': '#994CC3',
    'style_embeddedfieldvalue_color': '#4876D6',
    'style_fieldindex_color': '#4876D6',
    'style_string_color': '#4876D6',
    'style_lyrics_color': '#697098',
    'style_grace_color': '#AA0982',
    'style_ornament_color': '#4876D6',
    'style_ornamentplus_color': '#4876D6',
    'style_ornamentexcl_color': '#4876D6',
    'style_error_color': '#DE3D3B',
    'style_warning_color': '#B36A00',
    'style_selection_color': '#2E78DB',
    'score_paper': SCORE_COLOR,
}

DARK_STYLE_PALETTE = {
    'style_default_color': '#D6DEEB',
    'style_chord_color': '#C5E478',
    'style_comment_color': '#637777',
    'style_specialcomment_color': '#82AAFF',
    'style_bar_color': '#7FDBCA',
    'style_field_color': '#C792EA',
    'style_fieldvalue_color': '#ECC48D',
    'style_embeddedfield_color': '#C792EA',
    'style_embeddedfieldvalue_color': '#ECC48D',
    'style_fieldindex_color': '#82B1FF',
    'style_string_color': '#ECC48D',
    'style_lyrics_color': '#A8A8A8',
    'style_grace_color': '#F78C6C',
    'style_ornament_color': '#C5E478',
    'style_ornamentplus_color': '#82AAFF',
    'style_ornamentexcl_color': '#82AAFF',
    'style_error_color': '#EF5350',
    'style_warning_color': '#E5A100',
    'style_selection_color': '#2E78DB',
    'score_paper': SCORE_COLOR,
}

# User-customised colours are stored per appearance. The light set keeps the
# bare palette keys so settings saved before dark mode existed stay in force.
DARK_SETTINGS_KEY_PREFIX = 'dark_'


class Appearance:
    def __init__(self):
        self.is_dark = wx.SystemSettings.GetAppearance().IsDark()
        self.window_background = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW)
        self.text = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT)
        self.editor_background = self.window_background
        self.tooltip_background = wx.SystemSettings.GetColour(wx.SYS_COLOUR_INFOBK)
        self.tooltip_text = wx.SystemSettings.GetColour(wx.SYS_COLOUR_INFOTEXT)
        self.tooltip_border = wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT)
        if self.is_dark:
            self.style_palette = DARK_STYLE_PALETTE
            self._settings_key_prefix = DARK_SETTINGS_KEY_PREFIX
        else:
            self.style_palette = LIGHT_STYLE_PALETTE
            self._settings_key_prefix = ''

    def style_settings_key(self, palette_key):
        """The settings key holding the user's colour for ``palette_key`` under this appearance."""
        return self._settings_key_prefix + palette_key

    def style_color(self, settings, palette_key):
        """The user's colour for ``palette_key``, or the palette default when none is stored."""
        return settings.get(self.style_settings_key(palette_key), self.style_palette[palette_key])

    @staticmethod
    def html(colour):
        """The ``#RRGGBB`` form HTML attributes accept.

        System colours can carry an alpha channel, which HTML does not understand,
        so the colour is rebuilt without it.
        """
        opaque = wx.Colour(colour.Red(), colour.Green(), colour.Blue())
        return opaque.GetAsString(wx.C2S_HTML_SYNTAX)


_current = None


def current_appearance():
    global _current
    if _current is None:
        _current = Appearance()
    return _current


def rebuild_appearance():
    """Re-read the system colours; call after ``wx.EVT_SYS_COLOUR_CHANGED``."""
    global _current
    _current = Appearance()
    return _current
