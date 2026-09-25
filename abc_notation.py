'''
ABC notation tables and values shared by the checker in abc_parser and the MusicXML converter in abc2xml.
'''
import re
from types import MappingProxyType
from typing import NamedTuple, Optional

# MusicXML note type, keyed by the denominator of a note's duration in whole notes scaled by 1/4.
# The keys are also the legal denominators of an L: unit length.
NOTE_TYPES = MappingProxyType ({1: 'long', 2: 'breve', 4: 'whole', 8: 'half', 16: 'quarter', 32: 'eighth',
                                64: '16th', 128: '32nd', 256: '64th'})

# The clef whose middle staff line carries this note, for K: and V: middle=
CLEF_BY_MIDDLE_NOTE = MappingProxyType ({'B': 'treble', 'G': 'alto1', 'E': 'alto2', 'C': 'alto', 'A': 'tenor',
                                         'F': 'bass3', 'D': 'bass'})

# The General MIDI channel 10 drum sounds, name -> MIDI note number, in note number order
GM_DRUM_SOUNDS = MappingProxyType (dict (x.split (',') for x in (
    'acoustic-bass-drum,35;bass-drum-1,36;side-stick,37;acoustic-snare,38;hand-clap,39;electric-snare,40;'
    'low-floor-tom,41;closed-hi-hat,42;high-floor-tom,43;pedal-hi-hat,44;low-tom,45;open-hi-hat,46;low-mid-tom,47;'
    'hi-mid-tom,48;crash-cymbal-1,49;high-tom,50;ride-cymbal-1,51;chinese-cymbal,52;ride-bell,53;tambourine,54;'
    'splash-cymbal,55;cowbell,56;crash-cymbal-2,57;vibraslap,58;ride-cymbal-2,59;hi-bongo,60;low-bongo,61;'
    'mute-hi-conga,62;open-hi-conga,63;low-conga,64;high-timbale,65;low-timbale,66;high-agogo,67;low-agogo,68;'
    'cabasa,69;maracas,70;short-whistle,71;long-whistle,72;short-guiro,73;long-guiro,74;claves,75;hi-wood-block,76;'
    'low-wood-block,77;mute-cuica,78;open-cuica,79;mute-triangle,80;open-triangle,81').split (';')))

def drumSoundMidi (name):   # the MIDI note number of the GM drum sound name abbreviates, None when none matches
    # every '-' separated part of name must occur in the part at the same place of the GM name; the first
    # GM name left wins, so 'ride' is ride-cymbal-1 and 'open-hi' is open-hi-hat, while 'hi-hat' matches none
    matches = list (GM_DRUM_SOUNDS)
    for i, part in enumerate (name.split ('-')):
        matches = [gm for gm in matches if i < len (gm.split ('-')) and part in gm.split ('-') [i]]
        if len (matches) <= 1: break
    return GM_DRUM_SOUNDS [matches [0]] if matches else None

PERCUSSION_SWITCH_RE = re.compile (r'(perc|map)\s*=\s*(\S*)')
PERCUSSION_ON = ('on', 'true', 'perc')
CLEF_NAME_RE = re.compile (r'alto1|alto2|alto4|alto|tenor|bass3|bass|treble|perc|none|tab')
MIDDLE_NOTE_RE = re.compile (r"(?:^m=| m=|middle=)([A-Ga-g])([,']*)")
OCTAVE_RE = re.compile (r'octave=([-+]?\d)')
CLEF_OCTAVE_RE = re.compile (r'([-+^_])(8|15)')     # + and - also transpose the pitches, ^ and _ only print
TWO_OCTAVES = '15'
MIDDLE_OCTAVE_UPPER, MIDDLE_OCTAVE_LOWER = 4, 5     # the octave of an upper and a lower case middle= note
UNSHIFTED_OCTAVE_LOW, UNSHIFTED_OCTAVE_HIGH = 3, 4  # the octave of the middle line in the clef the note names

VOICE_NAME_RE = re.compile (r'\b(?:name|nm)="([^"]*)"')              # \b: not the tail of subname= or snm=
VOICE_SUBNAME_RE = re.compile (r'\b(?:subname|snm|sname)="([^"]*)"')

class VoiceDefinition (NamedTuple): # what the V: field opening a voice says about its part
    name: str               # the part name, '' when the field gives none
    subname: str            # the abbreviated part name, '' when the field gives none
    text: str               # the field after V:id, both names blanked so they cannot match a clef keyword

    @classmethod
    def parse (cls, text):  # text is the field after V:id
        name, subname = [m.group (1) if m else '' for m in (VOICE_NAME_RE.search (text), VOICE_SUBNAME_RE.search (text))]
        return cls (name, subname, text.replace ('"%s"' % name, '""').replace ('"%s"' % subname, '""'))

class ClefField (NamedTuple):   # what a K: or V: field says about the clef and the octave of its pitches
    percussion: Optional[bool]  # perc= or map= switched a percussion voice on or off; None when the field has neither
    clef: str                   # the abc clef name, '' when the field names none (middle= names one)
    octave_change: int          # octaves the +8, -8, ^8 or _15 suffix moves the printed clef
    octave_change_sounds: bool  # the suffix is + or -, which also moves the pitches
    middle_shift: int           # octaves the middle= note moves the pitches
    octave: Optional[int]       # octave=, None when absent

    @classmethod
    def parse (cls, field):
        percussion = None
        if re.search (r'perc|map', field):
            r = PERCUSSION_SWITCH_RE.search (field)
            percussion = not (r and r.group (2) not in PERCUSSION_ON)
            field = PERCUSSION_SWITCH_RE.sub ('', field)    # a perc= value must not match as a clef name
        clefn = CLEF_NAME_RE.search (field)
        clef = clefn.group () if clefn else ''
        middle_shift = 0
        clefm = MIDDLE_NOTE_RE.search (field)
        if clefm:
            note, octstr = clefm.groups ()
            nUp = note.upper ()
            octnum = (MIDDLE_OCTAVE_UPPER if nUp == note else MIDDLE_OCTAVE_LOWER) + (len (octstr) if "'" in octstr else -len (octstr))
            middle_shift = (UNSHIFTED_OCTAVE_LOW if nUp in 'AFD' else UNSHIFTED_OCTAVE_HIGH) - octnum
            if clef not in ['perc', 'none']: clef = CLEF_BY_MIDDLE_NOTE [nUp]
        octave_change, octave_change_sounds = 0, False
        suffix = CLEF_OCTAVE_RE.search (field)
        if suffix:
            octave_change = (-1 if suffix.group (1) in '-_' else 1) * (2 if suffix.group (2) == TWO_OCTAVES else 1)
            octave_change_sounds = suffix.group (1) in '+-'
        octave = OCTAVE_RE.search (field)
        return cls (percussion, clef, octave_change, octave_change_sounds, middle_shift,
                    int (octave.group (1)) if octave else None)

    def transposition (s):  # the octave shift of the pitches after this field, None when the field leaves it as it was
        shift = None
        if s.clef:
            shift = s.middle_shift
            if s.clef == 'none': return shift   # the clef without a sign ends the field's effect here
            if s.octave_change_sounds: shift += s.octave_change
        if s.octave is not None: shift = s.middle_shift + s.octave
        return shift
