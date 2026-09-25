'''
ABC notation tables shared by the checker in abc_parser and the MusicXML converter in abc2xml.
'''
from types import MappingProxyType

# MusicXML note type, keyed by the denominator of a note's duration in whole notes scaled by 1/4.
# The keys are also the legal denominators of an L: unit length.
NOTE_TYPES = MappingProxyType ({1: 'long', 2: 'breve', 4: 'whole', 8: 'half', 16: 'quarter', 32: 'eighth',
                                64: '16th', 128: '32nd', 256: '64th'})

# The clef whose middle staff line carries this note, for K: and V: middle=
CLEF_BY_MIDDLE_NOTE = MappingProxyType ({'B': 'treble', 'G': 'alto1', 'E': 'alto2', 'C': 'alto', 'A': 'tenor',
                                         'F': 'bass3', 'D': 'bass'})
