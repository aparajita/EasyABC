'''
The ABC decorations: every decoration abcm2ps draws, and every one the checker in abc_parser and the
MusicXML converter in abc2xml understand, each declared once in CATALOG.

An entry names the decoration (without its ! or + delimiters), describes it for the editor, places it
in an editor palette, and says what abc2xml writes for it. The checker needs only the classification:
which decorations it accepts, and which of those apply to the staff rather than to the next note.
'''
from enum import Enum
from types import MappingProxyType
from typing import NamedTuple, Optional


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
    UNKNOWN = 'unknown'     # abc2xml writes nothing for it

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


# What abc2xml writes, by kind:
#   WEDGE: the MusicXML wedge type             PEDAL, GLISSANDO, SLIDE, TRILL_LINE: 'start' or 'stop'
#   OCTAVE_SHIFT: an OctaveShift               NAVIGATION_SYMBOL: the JumpSound of the element of the same name
#   NAVIGATION_WORDS: a NavigationWords        TREMOLO_PAIR, TREMOLO_SINGLE: the number of bars
#   VOLTA_END: the MusicXML ending type        ARTICULATION, ORNAMENT, TECHNICAL: the MusicXML element name
#   any other kind: None
class OctaveShift (NamedTuple):
    type: str           # MusicXML octave-shift type
    placement: str


class JumpSound (NamedTuple):   # the <sound> attribute that makes playback follow a navigation mark
    attr: str
    value: str


class NavigationWords (NamedTuple):
    text: str
    sound: JumpSound


class Palette (Enum):   # the editor's decoration palettes
    DYNAMICS = 'Dynamics'
    FINGERING = 'Fingering'
    ORNAMENT = 'Ornament'
    DIRECTION = 'Direction'
    ARTICULATION = 'Articulation'


class Decoration (NamedTuple):
    name: str                       # without its ! or + delimiters
    description: str                # untranslated; the editor translates it where it shows it
    kind: DecorationKind
    musicxml: object = None         # what abc2xml writes for it (see the table by kind above)
    palette: Optional[Palette] = None   # the editor palette that offers it, None when no palette does
    aliases: tuple = ()             # other names of the same decoration
    bare: bool = False              # written without ! delimiters, like the staccato dot and the slur starts

    def notation (s, name):         # how name, the decoration's name or one of its aliases, is written in a tune
        return name if s.bare else '!%s!' % name

    @property
    def notations (s):              # the notation of the name, then of every alias
        return [s.notation (n) for n in (s.name,) + s.aliases]


K = DecorationKind
P = Palette
DAL_SEGNO = JumpSound ('dalsegno', 'segno')
DA_CAPO = JumpSound ('dacapo', 'yes')

# In palette order within each palette.
CATALOG = (
    Decoration ('ffff', 'fortissimo possibile', K.DYNAMIC, palette=P.DYNAMICS),
    Decoration ('fff', 'fortississimo', K.DYNAMIC, palette=P.DYNAMICS),
    Decoration ('ff', 'fortissimo', K.DYNAMIC, palette=P.DYNAMICS),
    Decoration ('f', 'forte', K.DYNAMIC, palette=P.DYNAMICS),
    Decoration ('mf', 'mezzoforte', K.DYNAMIC, palette=P.DYNAMICS),
    Decoration ('mp', 'mezzopiano', K.DYNAMIC, palette=P.DYNAMICS),
    Decoration ('p', 'piano', K.DYNAMIC, palette=P.DYNAMICS),
    Decoration ('pp', 'pianissimo', K.DYNAMIC, palette=P.DYNAMICS),
    Decoration ('ppp', 'pianississimo', K.DYNAMIC, palette=P.DYNAMICS),
    Decoration ('pppp', 'pianissimo possibile', K.DYNAMIC, palette=P.DYNAMICS),
    Decoration ('sfz', 'sforzando', K.DYNAMIC, palette=P.DYNAMICS),
    Decoration ('crescendo(', 'start of a < crescendo mark', K.WEDGE, 'crescendo', P.DYNAMICS, ('<(',)),
    Decoration ('crescendo)', 'end of a < crescendo mark', K.WEDGE, 'stop', P.DYNAMICS, ('<)',)),
    Decoration ('diminuendo(', 'start of a > diminuendo mark', K.WEDGE, 'diminuendo', P.DYNAMICS, ('>(',)),
    Decoration ('diminuendo)', 'end of a > diminuendo mark', K.WEDGE, 'stop', P.DYNAMICS, ('>)',)),

    Decoration ('0', 'no finger', K.STRING_NUMBER, palette=P.FINGERING),   # abc2xml: 0 chooses the string on a tablature staff
    Decoration ('1', 'thumb', K.STRING_NUMBER, palette=P.FINGERING),
    Decoration ('2', 'index finger', K.STRING_NUMBER, palette=P.FINGERING),
    Decoration ('3', 'middle finger', K.STRING_NUMBER, palette=P.FINGERING),
    Decoration ('4', 'ring finger', K.STRING_NUMBER, palette=P.FINGERING),
    Decoration ('5', 'little finger', K.STRING_NUMBER, palette=P.FINGERING),
    Decoration ('6', 'string 6 on a tablature staff', K.STRING_NUMBER),

    Decoration ('trill', 'trill', K.ORNAMENT, 'trill-mark', P.ORNAMENT),
    Decoration ('trill(', 'start of an extended trill', K.TRILL_LINE, 'start', P.ORNAMENT),
    Decoration ('trill)', 'end of an extended trill', K.TRILL_LINE, 'stop', P.ORNAMENT),
    Decoration ('mordent', 'mordent', K.ORNAMENT, 'mordent', P.ORNAMENT),
    Decoration ('pralltriller', 'pralltriller', K.ORNAMENT, 'inverted-mordent', P.ORNAMENT),
    Decoration ('roll', 'Irish roll', K.UNKNOWN, palette=P.ORNAMENT),
    Decoration ('turn', 'turn or gruppetto', K.ORNAMENT, 'turn', P.ORNAMENT),
    Decoration ('turnx', 'a turn mark with a line through it', K.UNKNOWN, palette=P.ORNAMENT),
    Decoration ('invertedturn', 'an inverted turn mark', K.ORNAMENT, 'inverted-turn', P.ORNAMENT),
    Decoration ('invertedturnx', 'an inverted turn mark with a line through it', K.UNKNOWN, palette=P.ORNAMENT),
    Decoration ('arpeggio', 'arpeggio', K.ARPEGGIO, palette=P.ORNAMENT),
    Decoration ('T', 'trill', K.ORNAMENT, 'trill-mark'),     # abc2xml also accepts the U: letter of the trill as !T!
    Decoration ('lowermordent', 'lower mordent', K.ORNAMENT, 'mordent'),
    Decoration ('uppermordent', 'upper mordent', K.ORNAMENT, 'inverted-mordent'),

    Decoration ('segno', 'segno', K.NAVIGATION_SYMBOL, JumpSound ('segno', 'segno'), P.DIRECTION),
    Decoration ('coda', 'coda', K.NAVIGATION_SYMBOL, JumpSound ('coda', 'coda'), P.DIRECTION),
    Decoration ('D.S.', 'the letters D.S. (=Da Segno)', K.NAVIGATION_WORDS, NavigationWords ('D.S.', DAL_SEGNO), P.DIRECTION),
    Decoration ('D.C.', 'the letters D.C. (=either Da Coda or Da Capo)', K.NAVIGATION_WORDS, NavigationWords ('D.C.', DA_CAPO), P.DIRECTION),
    Decoration ('dacoda', 'the word "Da" followed by a Coda sign', K.NAVIGATION_WORDS,
                NavigationWords ('To Coda', JumpSound ('tocoda', 'coda')), P.DIRECTION),
    Decoration ('dacapo', 'the words "Da Capo"', K.NAVIGATION_WORDS, NavigationWords ('D.C.', DA_CAPO), P.DIRECTION),
    Decoration ('D.C.alcoda', 'the words "D.C. al Coda"', K.NAVIGATION_WORDS, NavigationWords ('D.C. al Coda', DA_CAPO), P.DIRECTION),
    Decoration ('D.C.alfine', 'the words "D.C. al Fine"', K.NAVIGATION_WORDS, NavigationWords ('D.C. al Fine', DA_CAPO), P.DIRECTION),
    Decoration ('D.S.alcoda', 'the words "D.S. al Coda"', K.NAVIGATION_WORDS, NavigationWords ('D.S. al Coda', DAL_SEGNO), P.DIRECTION),
    Decoration ('D.S.alfine', 'the words "D.S. al Fine"', K.NAVIGATION_WORDS, NavigationWords ('D.S. al Fine', DAL_SEGNO), P.DIRECTION),
    Decoration ('fine', 'the word "fine"', K.NAVIGATION_WORDS, NavigationWords ('Fine', JumpSound ('fine', 'yes')), P.DIRECTION),

    Decoration ('.', 'staccato mark', K.ARTICULATION, 'staccato', P.ARTICULATION, bare=True),
    Decoration ('tenuto', 'tenuto', K.ARTICULATION, 'tenuto', P.ARTICULATION),
    Decoration ('accent', 'accent or emphasis', K.ARTICULATION, 'accent', P.ARTICULATION, ('>', 'emphasis')),
    Decoration ('marcato', 'marcato', K.ARTICULATION, 'strong-accent', P.ARTICULATION, ('^',)),
    Decoration ('wedge', 'staccatissimo or spiccato', K.ARTICULATION, 'staccatissimo', P.ARTICULATION),
    Decoration ('invertedfermata', 'upside down fermata', K.UNKNOWN, palette=P.ARTICULATION),
    Decoration ('fermata', 'fermata or hold', K.FERMATA, palette=P.ARTICULATION),
    Decoration ('plus', 'left-hand pizzicato', K.TECHNICAL, 'stopped', P.ARTICULATION, ('+',)),
    Decoration ('snap', 'snap-pizzicato', K.TECHNICAL, 'snap-pizzicato', P.ARTICULATION),
    Decoration ('slide', 'slide up to a note', K.ARTICULATION, 'scoop', P.ARTICULATION),
    Decoration ('upbow', 'up-bow', K.TECHNICAL, 'up-bow', P.ARTICULATION),
    Decoration ('downbow', 'down-bow', K.TECHNICAL, 'down-bow', P.ARTICULATION),
    Decoration ('open', 'open string or harmonic', K.TECHNICAL, 'open-string', P.ARTICULATION),
    Decoration ('thumb', 'cello thumb symbol', K.TECHNICAL, 'thumb-position', P.ARTICULATION),
    Decoration ('breath', 'breath mark', K.ARTICULATION, 'breath-mark', P.ARTICULATION),
    Decoration ('ped', 'sustain pedal down', K.PEDAL, 'start', P.ARTICULATION),
    Decoration ('ped-up', 'sustain pedal up', K.PEDAL, 'stop', P.ARTICULATION),

    Decoration ('fall', 'Adds a fall-off slide after the note it decorates.', K.ARTICULATION, 'falloff'),   # non-standard, accepted for the jazz falloff
    Decoration ('-(', 'Marks a portamento between the note after this decoration and the following note. Must be '
                'followed by a single note, then !-)!, then the note to which the portamento connects.', K.SLIDE, 'start'),
    Decoration ('-)', 'Marks the note to which a portamento connects. Must be preceded by the note from which the '
                'portamento begins, decorated with !-(!.', K.SLIDE, 'stop'),
    Decoration ('~(', 'Marks a chromatic glissando between the note after this decoration and the following note. Must '
                'be followed by a single note, then !~)!, then the note to which the glissando connects.', K.GLISSANDO, 'start'),
    Decoration ('~)', 'Marks the note to which a chromatic glissando connects. Must be preceded by the note from which '
                'the glissando begins, decorated with !~(!.', K.GLISSANDO, 'stop'),
    Decoration ('8va(', 'start of a passage played an octave higher', K.OCTAVE_SHIFT, OctaveShift ('down', 'above')),
    Decoration ('8va)', 'end of a passage played an octave higher', K.OCTAVE_SHIFT, OctaveShift ('stop', 'above')),
    Decoration ('8vb(', 'start of a passage played an octave lower', K.OCTAVE_SHIFT, OctaveShift ('up', 'below')),
    Decoration ('8vb)', 'end of a passage played an octave lower', K.OCTAVE_SHIFT, OctaveShift ('stop', 'below')),
    Decoration ('/', 'single-note tremolo with one bar', K.TREMOLO_SINGLE, 1),
    Decoration ('//', 'single-note tremolo with two bars', K.TREMOLO_SINGLE, 2),
    Decoration ('///', 'single-note tremolo with three bars', K.TREMOLO_SINGLE, 3),
    Decoration ('/-', 'tremolo between two notes with one bar', K.TREMOLO_PAIR, 1),
    Decoration ('//-', 'tremolo between two notes with two bars', K.TREMOLO_PAIR, 2),
    Decoration ('///-', 'tremolo between two notes with three bars', K.TREMOLO_PAIR, 3),
    Decoration ('////-', 'tremolo between two notes with four bars', K.TREMOLO_PAIR, 4),
    Decoration ('rbend', 'end of a repeat bracket, drawn with a vertical end line', K.VOLTA_END, 'stop'),
    Decoration ('rbstop', 'end of a repeat bracket, drawn without a vertical end line', K.VOLTA_END, 'discontinue'),
    Decoration ('shortphrase', 'vertical line on the upper part of the staff', K.UNKNOWN),
    Decoration ('mediumphrase', 'vertical line on the upper part of the staff, extending down to the centre line', K.UNKNOWN),
    Decoration ('longphrase', 'vertical line on the upper part of the staff, extending 3/4 of the way down', K.UNKNOWN),
    Decoration ('editorial', 'editorial accidental above note', K.UNKNOWN),
    Decoration ('courtesy', 'courtesy accidental between parentheses', K.UNKNOWN),
    Decoration ('(', 'start of a slur', K.SLUR_START, bare=True),
    Decoration ('.(', 'start of a dotted slur', K.SLUR_START, bare=True),
    Decoration ('(,', 'start of a slur below the notes', K.SLUR_START, bare=True),
    Decoration ("('", 'start of a slur above the notes', K.SLUR_START, bare=True),
    Decoration ('.(,', 'start of a dotted slur below the notes', K.SLUR_START, bare=True),
    Decoration (".('", 'start of a dotted slur above the notes', K.SLUR_START, bare=True),
)
del K, P

# The initial U: table of every tune. Read-only: each tune copies it, then adds its own definitions.
DEFAULT_USER_SYMBOLS = MappingProxyType ({
    '~': 'roll', 'H': 'fermata', 'L': '>', 'M': 'lowermordent', 'O': 'coda',
    'P': 'uppermordent', 'S': 'segno', 'T': 'trill', 'u': 'upbow', 'v': 'downbow'})


def _by_name ():    # every name and alias -> its Decoration
    decorations = {}
    for d in CATALOG:
        for name in (d.name,) + d.aliases:
            if name in decorations: raise ValueError ('decoration %s is declared twice' % name)
            decorations [name] = d
    return MappingProxyType (decorations)

_BY_NAME = _by_name ()


def lookup (name):      # the Decoration of a name or alias, None when the name is no decoration
    return _BY_NAME.get (name)


def classify (name):    # name is a decoration without its ! or + delimiters, after U: substitution
    d = _BY_NAME.get (name)
    return d.kind if d else DecorationKind.UNKNOWN


def musicxml (name):    # what abc2xml writes for name, whose kind is not UNKNOWN
    return _BY_NAME [name].musicxml


def palette (p):        # the notations the editor offers in palette p, in palette order
    return [notation for d in CATALOG if d.palette is p for notation in d.notations]
