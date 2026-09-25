'''
The ABC decorations understood by the checker in abc_parser and the MusicXML converter in abc2xml.

Every table maps an abc decoration name (without its ! or + delimiters) to what abc2xml
writes for it. The checker needs only the classification: which decorations it accepts,
and which of those apply to the staff rather than to the next note.
'''
from enum import Enum
from types import MappingProxyType
from typing import NamedTuple


class OctaveShift (NamedTuple):
    type: str           # MusicXML octave-shift type
    placement: str


class JumpSound (NamedTuple):   # the <sound> attribute that makes playback follow a navigation mark
    attr: str
    value: str


class NavigationWords (NamedTuple):
    text: str
    sound: JumpSound


DYNAMICS = frozenset (['p', 'pp', 'ppp', 'pppp', 'f', 'ff', 'fff', 'ffff', 'mp', 'mf', 'sfz'])
WEDGES = MappingProxyType ({        # decoration -> MusicXML wedge type
    '<(': 'crescendo', 'crescendo(': 'crescendo', '<)': 'stop', 'crescendo)': 'stop',
    '>(': 'diminuendo', 'diminuendo(': 'diminuendo', '>)': 'stop', 'diminuendo)': 'stop'})
OCTAVE_SHIFTS = MappingProxyType ({
    '8va(': OctaveShift ('down', 'above'), '8va)': OctaveShift ('stop', 'above'),
    '8vb(': OctaveShift ('up', 'below'), '8vb)': OctaveShift ('stop', 'below')})
PEDALS = MappingProxyType ({'ped': 'start', 'ped-up': 'stop'})

# A navigation symbol is written as the MusicXML element of the same name.
NAVIGATION_SYMBOLS = MappingProxyType ({
    'coda': JumpSound ('coda', 'coda'),
    'segno': JumpSound ('segno', 'segno')})
NAVIGATION_WORDS = MappingProxyType ({
    'fine': NavigationWords ('Fine', JumpSound ('fine', 'yes')),
    'D.S.': NavigationWords ('D.S.', JumpSound ('dalsegno', 'segno')),
    'D.C.': NavigationWords ('D.C.', JumpSound ('dacapo', 'yes')),
    'dacapo': NavigationWords ('D.C.', JumpSound ('dacapo', 'yes')),
    'dacoda': NavigationWords ('To Coda', JumpSound ('tocoda', 'coda')),
    'D.C.alfine': NavigationWords ('D.C. al Fine', JumpSound ('dacapo', 'yes')),
    'D.C.alcoda': NavigationWords ('D.C. al Coda', JumpSound ('dacapo', 'yes')),
    'D.S.alfine': NavigationWords ('D.S. al Fine', JumpSound ('dalsegno', 'segno')),
    'D.S.alcoda': NavigationWords ('D.S. al Coda', JumpSound ('dalsegno', 'segno'))})

SLUR_STARTS = frozenset (['(', '.(', '(,', "('", '.(,', ".('"])
TREMOLO_PAIRS = MappingProxyType ({'/-': 1, '//-': 2, '///-': 3, '////-': 4})     # decoration -> number of bars
TREMOLO_SINGLES = MappingProxyType ({'/': 1, '//': 2, '///': 3})                   # decoration -> number of bars
VOLTA_ENDS = MappingProxyType ({'rbend': 'stop', 'rbstop': 'discontinue'})    # abcm2ps draws the end line of the bracket only for rbend

FERMATA = 'fermata'
ARPEGGIO = 'arpeggio'
GLISSANDOS = MappingProxyType ({'~(': 'start', '~)': 'stop'})
SLIDES = MappingProxyType ({'-(': 'start', '-)': 'stop'})
ARTICULATIONS = MappingProxyType ({
    '.': 'staccato', '>': 'accent', 'accent': 'accent', 'wedge': 'staccatissimo', 'tenuto': 'tenuto',
    'breath': 'breath-mark', 'marcato': 'strong-accent', '^': 'strong-accent', 'slide': 'scoop',
    'fall': 'falloff'})     # non-standard, accepted for the jazz falloff
ORNAMENTS = MappingProxyType ({
    'trill': 'trill-mark', 'T': 'trill-mark', 'turn': 'turn', 'uppermordent': 'inverted-mordent', 'lowermordent': 'mordent',
    'pralltriller': 'inverted-mordent', 'mordent': 'mordent', 'invertedturn': 'inverted-turn'})
TRILL_LINES = MappingProxyType ({'trill(': 'start', 'trill)': 'stop'})
TECHNICAL = MappingProxyType ({
    'upbow': 'up-bow', 'downbow': 'down-bow', 'plus': 'stopped', 'open': 'open-string', 'snap': 'snap-pizzicato',
    'thumb': 'thumb-position'})
STRING_NUMBERS = frozenset ('0123456')  # 0 asks abc2xml to choose the string on a tablature staff

# The initial U: table of every tune. Read-only: each tune copies it, then adds its own definitions.
DEFAULT_USER_SYMBOLS = MappingProxyType ({
    '~': 'roll', 'H': 'fermata', 'L': '>', 'M': 'lowermordent', 'O': 'coda',
    'P': 'uppermordent', 'S': 'segno', 'T': 'trill', 'u': 'upbow', 'v': 'downbow'})


class DecorationKind (Enum):
    DYNAMIC = 'dynamic'
    WEDGE = 'wedge'
    OCTAVE_SHIFT = 'octave shift'
    PEDAL = 'pedal'
    NAVIGATION_SYMBOL = 'navigation symbol'
    NAVIGATION_WORDS = 'navigation words'
    SLUR_START = 'slur start'
    TREMOLO_PAIR = 'tremolo pair'
    TREMOLO_SINGLE = 'tremolo single'
    VOLTA_END = 'volta end'
    FERMATA = 'fermata'
    ARPEGGIO = 'arpeggio'
    GLISSANDO = 'glissando'
    SLIDE = 'slide'
    ARTICULATION = 'articulation'
    ORNAMENT = 'ornament'
    TRILL_LINE = 'trill line'
    TECHNICAL = 'technical'
    STRING_NUMBER = 'string number'
    UNKNOWN = 'unknown'

    @property
    def applies_to_staff (s):   # consumed where it stands in the music; every other kind waits for the next note
        return s in _STAFF_KINDS

    @property
    def applies_to_note (s):    # written as a notation of the note it is attached to
        return s in _NOTE_KINDS


# A slur start is the one kind in both: it opens its slur on the next note either way.
_STAFF_KINDS = frozenset ([
    DecorationKind.DYNAMIC, DecorationKind.WEDGE, DecorationKind.OCTAVE_SHIFT, DecorationKind.PEDAL,
    DecorationKind.NAVIGATION_SYMBOL, DecorationKind.NAVIGATION_WORDS, DecorationKind.SLUR_START,
    DecorationKind.TREMOLO_PAIR, DecorationKind.TREMOLO_SINGLE, DecorationKind.VOLTA_END])
_NOTE_KINDS = frozenset ([
    DecorationKind.SLUR_START, DecorationKind.FERMATA, DecorationKind.ARPEGGIO, DecorationKind.GLISSANDO,
    DecorationKind.SLIDE, DecorationKind.ARTICULATION, DecorationKind.ORNAMENT, DecorationKind.TRILL_LINE,
    DecorationKind.TECHNICAL, DecorationKind.STRING_NUMBER])


def _kind_by_name ():
    kinds = {}
    for names, kind in [
            (DYNAMICS, DecorationKind.DYNAMIC), (WEDGES, DecorationKind.WEDGE),
            (OCTAVE_SHIFTS, DecorationKind.OCTAVE_SHIFT), (PEDALS, DecorationKind.PEDAL),
            (NAVIGATION_SYMBOLS, DecorationKind.NAVIGATION_SYMBOL), (NAVIGATION_WORDS, DecorationKind.NAVIGATION_WORDS),
            (SLUR_STARTS, DecorationKind.SLUR_START), (TREMOLO_PAIRS, DecorationKind.TREMOLO_PAIR),
            (TREMOLO_SINGLES, DecorationKind.TREMOLO_SINGLE), (VOLTA_ENDS, DecorationKind.VOLTA_END),
            ([FERMATA], DecorationKind.FERMATA), ([ARPEGGIO], DecorationKind.ARPEGGIO),
            (GLISSANDOS, DecorationKind.GLISSANDO), (SLIDES, DecorationKind.SLIDE),
            (ARTICULATIONS, DecorationKind.ARTICULATION), (ORNAMENTS, DecorationKind.ORNAMENT),
            (TRILL_LINES, DecorationKind.TRILL_LINE), (TECHNICAL, DecorationKind.TECHNICAL),
            (STRING_NUMBERS, DecorationKind.STRING_NUMBER)]:
        for name in names:
            if name in kinds: raise ValueError ('decoration %s is both %s and %s' % (name, kinds [name].value, kind.value))
            kinds [name] = kind
    return MappingProxyType (kinds)

_KIND_BY_NAME = _kind_by_name ()


def classify (name):    # name is a decoration without its ! or + delimiters, after U: substitution
    return _KIND_BY_NAME.get (name, DecorationKind.UNKNOWN)
