'''
The I: directives, read once for both the checker in abc_parser and the MusicXML converter in abc2xml.

parse_info_directive turns the text after I: into one record per kind of directive. A tool acts on a
directive through a DirectiveHandler, which declares an abstract method for every kind. A new kind
adds its method there, and each tool's handler then fails at instantiation until it implements it,
so the two tools cannot drift apart.
'''
import re
from abc import ABC, abstractmethod
from enum import Enum
from typing import NamedTuple, Optional
from pyparsing import ParseException
from abc_notation import drumSoundMidi
from abc_syntax import abc_percmap, gracewordRE, isScoreDirective

PAGE_FORMAT_RE = re.compile (r'[^.\d]*([\d.]+)\s*(cm|in|pt)?')     # a number, then an optional unit
MM_PER_UNIT = {'cm': 10., 'in': 25.4, 'pt': 25.4 / 72, None: 1.}   # a page format value without a unit is in mm
STAFF_REDIRECTION_RE = re.compile (r'staff *([+-]?)(\d)')
MIDI_PROGRAM_RE = re.compile (r'program *(\d*) +(\d+)')             # optional channel, program
MIDI_CHANNEL_RE = re.compile (r'channel *(\d+)')
MIDI_CONTROL_RE = re.compile (r'control *(\d+) +(\d+)')             # controller number, controller value
MIDI_DRUMMAP_RE = re.compile (r"drummap\s+([_=^]*)([A-Ga-g])([,']*)\s+(\d+)")
MIDI_TRANSPOSE_RE = re.compile (r'transpose[^-\d]*(-?\d+)')
VOLUME_CONTROLLER, PAN_CONTROLLER = '7', '10'
PERCMAP_HEAD_RE = re.compile (r'(.)-([^x])')                        # abc note head names use - where MusicXML uses a space

SEMITONES_PER_OCTAVE = 12
STEP_SEMITONES = dict (zip ('CDEFGAB', (0, 2, 4, 5, 7, 9, 11)))
ACCIDENTAL_SEMITONES = {'^': 1, '_': -1, '=': 0}
UPPER_CASE_OCTAVE, LOWER_CASE_OCTAVE = 4, 5     # the octave of the abc notes C and c
MIDI_OCTAVE_OFFSET = 1                          # MIDI note 0 is the C of octave -1

def syntaxErrorMessage (text, err):     # text is the directive after I:, err the ParseException its grammar raised
    return 'syntax error in I:%s at column %d' % (text, err.col)

def noteMidi (accidental, step, octave):    # the MIDI note number of an abc note; octave counts ' as +1 and , as -1
    octave += UPPER_CASE_OCTAVE if step.isupper () else LOWER_CASE_OCTAVE
    return ((octave + MIDI_OCTAVE_OFFSET) * SEMITONES_PER_OCTAVE + STEP_SEMITONES [step.upper ()]
            + ACCIDENTAL_SEMITONES.get (accidental, 0))


class DirectiveHandler (ABC):   # what a tool does with each kind of I: directive
    @abstractmethod
    def on_score (s, directive): pass
    @abstractmethod
    def on_staff_redirection (s, directive): pass
    @abstractmethod
    def on_page_format (s, directive): pass
    @abstractmethod
    def on_midi (s, directive): pass
    @abstractmethod
    def on_percussion_mapping (s, directive): pass
    @abstractmethod
    def on_graceword (s, directive): pass
    @abstractmethod
    def on_skipped (s, directive): pass
    @abstractmethod
    def on_invalid (s, directive): pass
    @abstractmethod
    def on_malformed (s, directive): pass


class ScoreDirective (NamedTuple):  # I:score or I:staves
    text: str
    def accept (s, handler): return handler.on_score (s)


class StaffReference (Enum):
    ABSOLUTE = 'absolute'   # the abc staff with this number
    RELATIVE = 'relative'   # this many staves below (positive) or above (negative) the current one


class StaffRedirection (NamedTuple):    # I:staff n, I:staff +n, I:staff -n
    number: int             # signed when the reference is RELATIVE
    reference: StaffReference
    text: str               # the part of the directive that names the staff
    def accept (s, handler): return handler.on_staff_redirection (s)


class PageSetting (Enum):
    SCALE = 'scale'
    PAGE_HEIGHT = 'pageheight'
    PAGE_WIDTH = 'pagewidth'
    LEFT_MARGIN = 'leftmargin'
    RIGHT_MARGIN = 'rightmargin'
    TOP_MARGIN = 'topmargin'
    BOTTOM_MARGIN = 'botmargin'


class PageFormat (NamedTuple):  # I:scale, I:pagewidth, ...
    setting: PageSetting
    value: float            # in mm, the scale a plain number
    def accept (s, handler): return handler.on_page_format (s)


class MidiInstrument (NamedTuple):  # each field is the digits the directive gives, '' when it leaves it as it was
    channel: str
    program: str
    volume: str
    pan: str


class DrumMapping (NamedTuple):     # I:MIDI drummap note midi
    accidental: str
    step: str
    octave: int             # counts ' as +1 and , as -1
    midi: str

    @property
    def notehead (s):
        return {'^': 'x', '_': 'circle-x'}.get (s.accidental, 'normal')


class MidiDirective (NamedTuple):   # I:MIDI or I:midi
    instrument: Optional[MidiInstrument]    # None when the directive sets no program, channel or controller
    drum: Optional[DrumMapping]
    transpose: Optional[str]        # signed semitones, None when absent
    def accept (s, handler): return handler.on_midi (s)


class PercussionMapping (NamedTuple):   # I:percmap note [step] [midi] [note-head]
    accidental: str
    step: str
    octave: int
    display_step: str       # where the note is drawn on the staff
    display_octave: int
    midi: Optional[str]     # None when sound names no GM drum sound
    sound: Optional[str]    # the drum sound name the directive gives, None when it gives a note or a number
    notehead: str           # MusicXML notehead name
    def accept (s, handler): return handler.on_percussion_mapping (s)

    @property
    def problem (s):        # the message for a sound name that matches no GM drum sound, None when midi is known
        return None if s.midi is not None else 'drum sound: %s not found' % s.sound


class GracewordDirective (NamedTuple):  # applied when the lyrics are aligned (LyricAligner)
    text: str
    def accept (s, handler): return handler.on_graceword (s)


class SkippedDirective (NamedTuple):    # a directive neither tool acts on
    text: str
    def accept (s, handler): return handler.on_skipped (s)

    @property
    def message (s): return 'skipped I-field: %s' % s.text


class InvalidDirective (NamedTuple):    # a known directive whose value cannot be read
    message: str
    def accept (s, handler): return handler.on_invalid (s)


class MalformedDirective (NamedTuple):  # a directive its grammar rejects
    message: str
    def accept (s, handler): return handler.on_malformed (s)


def dispatch_info_directive (text, handler):    # text is the directive after I:
    return parse_info_directive (text).accept (handler)

def parse_info_directive (text):
    if isScoreDirective (text): return ScoreDirective (text)
    if text.startswith ('staffwidth'): return SkippedDirective (text)
    if text.startswith ('staff'): return parseStaffRedirection (text)
    for setting in PageSetting:
        if text.startswith (setting.value): return parsePageFormat (text, setting)
    if text.startswith (('MIDI', 'midi')): return parseMidi (text)
    if text.startswith ('percmap'): return parsePercussionMapping (text)
    if gracewordRE.match (text): return GracewordDirective (text)
    return SkippedDirective (text)

def parseStaffRedirection (text):
    m = STAFF_REDIRECTION_RE.search (text)
    if not m: return InvalidDirective ('not a valid staff redirection: %s' % text)
    sign, digits = m.groups ()
    if not sign: return StaffRedirection (int (digits), StaffReference.ABSOLUTE, m.group ())
    return StaffRedirection (int (sign + digits), StaffReference.RELATIVE, m.group ())

def parsePageFormat (text, setting):
    m = PAGE_FORMAT_RE.search (text)
    try: value = float (m.group (1)) if m else None
    except ValueError: value = None     # the pattern admits more than one dot
    if value is None: return InvalidDirective ('error in page format: %s' % text)
    return PageFormat (setting, value * MM_PER_UNIT [m.group (2)])

def parseMidi (text):
    program = MIDI_PROGRAM_RE.search (text)
    channel = MIDI_CHANNEL_RE.search (text)
    control = MIDI_CONTROL_RE.search (text)
    instrument = None
    if program or channel or control:
        chan, prog = program.groups () if program else ('', '')
        if channel: chan = channel.group (1)
        cnum, cval = control.groups () if control else ('', '')
        instrument = MidiInstrument (chan, prog, cval if cnum == VOLUME_CONTROLLER else '',
                                     cval if cnum == PAN_CONTROLLER else '')
    drum = None
    m = MIDI_DRUMMAP_RE.search (text)
    if m:
        acc, step, octs, midi = m.groups ()
        drum = DrumMapping (acc, step, -len (octs) if ',' in text else len (octs), midi)
    transpose = MIDI_TRANSPOSE_RE.search (text)
    return MidiDirective (instrument, drum, transpose.group (1) if transpose else None)

def parsePercussionMapping (text):
    try: _, note, display, sound, head = abc_percmap.parse_string (text).as_list ()
    except ParseException as err: return MalformedDirective (syntaxErrorMessage (text, err))
    acc, step, octave = note
    display_step, display_octave = (step, octave) if display == '*' else display
    name = None
    if sound == '*':                midi = str (noteMidi (acc, step, octave))
    elif isinstance (sound, list):  midi = str (noteMidi (*sound))
    elif isinstance (sound, int):   midi = str (sound)
    else:
        name = sound.lower ()
        midi = drumSoundMidi (name)
    return PercussionMapping (acc, step, octave, display_step, display_octave, midi, name,
                              PERCMAP_HEAD_RE.sub (r'\1 \2', head))
