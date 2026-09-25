#!/usr/bin/env python
# coding=latin-1
'''
ABC parser producing diagnostics for the editor.

The grammar and the tree transformations derive from abc2xml:

Copyright (C) 2012-2018: Willem G. Vree
Contributions: Nils Liberg, Nicolas Froment, Norman Schmidt, Reinier Maliepaard, Martin Tarenskeen,
               Paul Villiger, Alexander Scheutzow, Herbert Schneider, David Randolph, Michael Strasser

This program is free software; you can redistribute it and/or modify it under the terms of the
Lesser GNU General Public License as published by the Free Software Foundation;

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the Lesser GNU General Public License for more details. <http://www.gnu.org/licenses/lgpl.html>.
'''

from dataclasses import dataclass
from enum import Enum
from typing import Optional as Opt
import re
import abc_decorations
from abc_decorations import DecorationKind
from abc_directives import DirectiveHandler, dispatch_info_directive
from abc_notation import NOTE_TYPES, ClefField
from abc_staff_layout import StaffLayout, UNKNOWN_VOICE_MESSAGE
from abc_syntax import pObj, srcContext, lyricContext, simplify, headerFieldRE
from abc_syntax import parse_tune, AbcSyntaxError, caughtSymbols


class Severity (Enum):
    ERROR = 'error'
    WARNING = 'warning'
    INFO = 'info'


@dataclass (frozen=True)
class SourcePosition:
    line: int       # 1-based line within the text passed to parse_abc()
    excerpt: str    # the rewritten row the parser saw (comments stripped, fields folded to [X:...], continuations joined)
    column: int     # 0-based offset within excerpt


@dataclass (frozen=True)
class Diagnostic:
    message: str
    severity: Severity
    position: Opt[SourcePosition]   # header-level and whole-tune messages have no location


class ParseRun:     # everything one parse_abc call produces and every position table it needs
    def __init__ (s, header):   # header = the SrcText of the tune's folded header fields
        fields = list (headerFieldRE.finditer (header.text))
        s.header_fields = [m.group () for m in fields]                  # header_fields[i] is the text of the i-th field
        s.header_field_lines = [header.lines [m.start ()] for m in fields]
        s.diagnostics = []

    def report (s, message, severity, position):
        s.diagnostics.append (Diagnostic (message, severity, position))

    def position_of (s, node, source):
        return SourcePosition (*srcContext (source, node.loc))

    def header_position_of (s, field_index):
        return SourcePosition (s.header_field_lines [field_index], s.header_fields [field_index], 0)


MAX_NOTE_DENOMINATOR = 64       # durations finer than 1/64 are rounded up to it
DEFAULT_UNIT_LENGTH = (1, 8)
DEFAULT_MEASURE_DURATION = (4, 4)
DEFAULT_METER = '4/4'           # applied to every voice when the header has no M:
DEFAULT_KEY = 'C treble'        # applied to every voice when the header has no K:
QUARTER_NOTE_SCALE = 4          # the legal duration table is indexed by durations expressed in quarter notes
DEFAULT_TEMPO_UNIT = (1, 4)     # a Q: field with only a text has this beat unit
GRACE_MAX_DENOMINATOR = 16      # a grace note longer than this is shown as 1/32
GRACE_DENOMINATOR = 32
DOTTED_NUMERATOR, DOUBLE_DOTTED_NUMERATOR = 3, 7


class Validator:
    '''Semantic checks over the parse trees; every finding goes through run.report.

    The checks are those of abc2xml's MusicXml class, without the XML it built. Of the
    diagnostics that class emits, these are intentionally absent because their condition
    cannot arise without XML output:

    - 'fret %d out of range' (doArticulations): the fret follows from the string allocation
      table, whose occupancy is kept in XML divisions, and from the XML note's pitch element.
    - the syntax error messages: parse_abc reports the AbcSyntaxError of parse_tune.
    '''

    def __init__ (s, run):
        s.run = run
        s.voice = None          # the ParsedVoice being walked
        s.unitL = DEFAULT_UNIT_LENGTH       # unit length of the header
        s.unitLcur = DEFAULT_UNIT_LENGTH    # unit length of the current voice
        s.headerMeter = DEFAULT_METER    # M: of the header, applied at the start of every voice
        s.headerKey = DEFAULT_KEY        # K: of the header, applied at the start of every voice
        s.mdur = DEFAULT_MEASURE_DURATION   # duration of one measure
        s.overlay = False       # the current measure ends in a voice overlay
        s.ntup = -1             # tuplet: notes remaining (-1 = no tuplet open)
        s.tupnts = 0            # tuplet notes seen since the tuplet started
        s.trem = 0              # number of bars for tremolo
        s.intrem = 0            # inside a tremolo pair (duration doubling)
        s.usrSyms = dict (abc_decorations.DEFAULT_USER_SYMBOLS)     # user defined symbols
        s.nextdecos = []        # decorations pending for the next note
        s.nextdecosNode = None  # the deco node the first pending decoration came from
        s.ties = {}             # {(step, octave): overlay voice number} for all open ties
        s.overlayVnum = 0       # overlay voice number of the current measure
        s.prevLyric = {}        # {verse number: 1} when the previous note carried a lyric in that verse
        s.staveDefs = []        # [(I:score / I:staves text, position)] in encounter order
        s.layout = StaffLayout ({})     # the staves and parts of the tune, set once its voices are known
        s.vid = ''              # current voice id
        s.pid = ''              # current part id
        s.percVoice = 0         # current voice has a percussion clef
        s.percMap = {}          # (part id, accidental + step, octave) -> mapped
        s.pMapFound = 0         # at least one I:percmap was seen
        s.gtrans = 0            # octave transposition of the current clef
        s.elementChecks = {     # node name -> check; a name missing here is not checked
            'note': s.check_note, 'rest': s.check_note, 'inline': s.check_inline_field, 'error': s.check_misplaced_symbol,
            'tup': s.start_tuplet, 'deco': s.check_staff_decorations, 'rbar': s.note_overlay,
            'lbar': s.ignore, 'text': s.ignore, 'accia': s.ignore, 'linebrk': s.ignore, 'chordsym': s.ignore,
            'lyr_blk': s.check_lyric_alignment, 'broken': s.ignore }

    def ignore (s, node): pass

    #---------------- positions ----------------

    def node_position (s, node):    # None for a node the grammar did not stamp (e.g. the synthetic empty-voice field)
        if getattr (node, 'loc', None) is None: return None
        return s.run.position_of (node, s.voice.source)

    def lyric_position (s, node):   # point inside the [w:...] text the lyric node came from
        return SourcePosition (*lyricContext (s.voice.source, node.loc))

    def warn (s, message, position=None): s.run.report (message, Severity.WARNING, position)
    def error (s, message, position=None): s.run.report (message, Severity.ERROR, position)

    #---------------- entry ----------------

    def validate (s, header_fields, voices):
        for i, fld in enumerate (header_fields):
            position = s.run.header_position_of (i)
            if fld.name == 'field': s.check_header_field (fld, position)
            else: s.warn ('unexpected header item: %s' % fld, position)
        s.collect_voice_definitions (voices)
        s.check_stave_definitions (voices)
        for voice in voices: s.check_voice (voice)
        s.check_score_voice_ids ([voice.id for voice in voices])

    #---------------- header ----------------

    def check_caught_symbol (s, fld, position):     # a misplaced character the U: grammar caught inside the field
        for caught in caughtSymbols (fld): s.error ('misplaced symbol: %s' % caught.t[0], position)

    def check_header_field (s, fld, position):
        s.check_caught_symbol (fld, position)
        type, value = fld.t[0], fld.t[1].replace ('%5d',']')    # restore closing brackets (see splitHeaderVoices)
        if not value: return
        if type == 'M':
            if value != 'none': s.headerMeter = value
            s.check_meter (value, position)
        elif type == 'L':
            s.unitL = s.check_header_unit_length (fld.t[1], position)
        elif type == 'K':
            s.headerKey = value
        elif type == 'U':
            s.usrSyms [value] = fld.t[2].strip ('!+')
        elif type == 'I':
            s.check_info_field (value, position)
        elif type == 'Q':
            s.check_tempo (value, position)
        elif type in 'XTCRZNOAGHBDFSP':
            pass                # reference number, titles and meta data
        else:
            s.warn ('skipped header: %s' % fld, position)

    def check_header_unit_length (s, field, position):
        try: unitL = tuple (map (int, field.split ('/')))
        except ValueError:
            s.warn ('illegal unit length:%s, 1/8 assumed' % field, position)
            unitL = DEFAULT_UNIT_LENGTH
        if len (unitL) == 1 or unitL[1] not in NOTE_TYPES:
            s.warn ('L:%s is not allowed, 1/8 assumed' % field, position)
            unitL = DEFAULT_UNIT_LENGTH
        return unitL

    def collect_voice_definitions (s, voices):      # checks each V: id, and collects every I:score in the voices
        for voice in voices:
            s.voice = voice     # node_position reads the source of the current voice
            if voice.id_problem: s.warn (voice.id_problem, s.node_position (voice.voicedef))
            for text, node in voice.score_directives (): s.staveDefs.append ((text, s.node_position (node)))
        s.voice = None

    def check_stave_definitions (s, voices):
        s.layout = StaffLayout.from_directives (s.staveDefs, voices, s.warn, s.error)

    def check_score_voice_ids (s, vids):    # every voice an I:score names must exist
        for vid in s.layout.unknown_voices (vids): s.warn (UNKNOWN_VOICE_MESSAGE % vid)

    #---------------- voices and measures ----------------

    def check_voice (s, voice):
        s.voice = voice
        s.vid = voice.id
        s.pid = s.layout.part_ids [voice.id]
        s.unitLcur = s.unitL
        s.percVoice = 0
        s.gtrans = 0
        s.overlayVnum = 0
        voicedef = voice.definition.text
        if 'perc' not in voicedef: s.apply_clef (s.headerKey)   # a percussion voice ignores the header key
        s.mdur = s.measure_duration (s.headerMeter)[0]          # the header meter was already checked at its field
        if voicedef: s.apply_clef (voicedef)
        overlay = False
        for measure in voice.measures:
            s.overlayVnum = s.overlayVnum + 1 if overlay else 0
            overlay = s.check_measure (measure)
        s.check_leftover_decorations ()
        s.voice = None

    def check_leftover_decorations (s):     # decorations that no note claimed before the voice ended
        if not s.nextdecos: return
        position = s.node_position (s.nextdecosNode)
        for d in s.nextdecos: s.error ('decoration applies to no note: %s' % d, position)
        s.nextdecos = []
        s.nextdecosNode = None

    def check_measure (s, measure):     # returns whether the measure ends in a voice overlay
        s.ntup, s.trem, s.intrem = -1, 0, 0
        s.overlay = False
        for x in measure:
            check = s.elementChecks.get (x.name)
            if check: check (x)
        return s.overlay

    def note_overlay (s, node):
        if node.t[0][0] == '&': s.overlay = True

    def start_tuplet (s, node):
        if   len (node.t) == 3: n, into, nts = node.t
        elif len (node.t) == 2: n, into, nts = node.t + [0]
        else:                   n, into, nts = node.t[0], 0, 0
        if nts == 0: nts = n
        s.ntup, s.tupnts = nts, 0

    def check_misplaced_symbol (s, node):
        s.error ('misplaced symbol: %s' % node.t[0], s.node_position (node))

    def check_staff_decorations (s, node):  # staff-level decorations are consumed here, note decorations wait for the next note
        for d in node.t:
            d = s.usrSyms.get (d, d).strip ('!+')
            kind = abc_decorations.classify (d)
            if kind is DecorationKind.TREMOLO_PAIR:
                s.ntup, s.tupnts, s.trem, s.intrem = 2, 0, abc_decorations.musicxml (d), 1
            elif kind is DecorationKind.TREMOLO_SINGLE: s.trem = - abc_decorations.musicxml (d)
            elif kind.applies_to_staff: continue
            else:
                s.nextdecos.append (d)
                if s.nextdecosNode is None: s.nextdecosNode = node

    #---------------- notes ----------------

    def check_note (s, n):
        isgrace = getattr (n, 'grace', '')
        ischord = getattr (n, 'chord', '')
        isreal = not isgrace and not ischord            # a note with a duration of its own
        if s.ntup >= 0 and isreal:
            s.ntup -= 1                                 # count tuplet notes only on non-chord, non-grace notes
            if s.ntup == -1 and s.trem <= 0: s.intrem = 0
        s.check_note_duration (n, isgrace)
        if n.name == 'rest': acc, step, oct = '', 'C', '0'
        else:
            p = n.pitch.t
            if len (p) == 3: acc, step, oct = p
            else:            acc = ''; step, oct = p
            s.check_percussion_map (n, acc, step, oct)
        ptup = (step, oct)                              # pitch tuple without alteration to check for ties
        tstop = ptup in s.ties and s.ties [ptup] == s.overlayVnum
        tstart = getattr (n, 'tie', 0)
        decos, decosNode = s.note_decorations (n)
        if acc and not tstop and 'courtesy' in decos: decos.remove ('courtesy')
        if 'stemless' in decos: decos.remove ('stemless')
        tupnotation = ''
        if s.ntup >= 0:
            if s.ntup > 0 and not s.tupnts: tupnotation = 'start'
            s.tupnts += 1
            if s.ntup == 0:
                if isreal: tupnotation = 'stop'
                s.tupnts = 0
        s.check_ties (n, ptup, tstop, tstart)
        s.check_note_decorations (n, decos, decosNode, tupnotation, tstop, tstart)
        if n.objs: s.check_lyrics (n)
        elif n.name != 'rest': s.prevLyric = {}         # a note without lyrics ends a melisma; a rest does not

    def check_note_duration (s, n, isgrace):
        nnum, nden = n.dur.t
        if nnum == 0: nnum = 1          # a leading zero (stemless in abcm2ps) is read as 1
        if s.intrem: nnum += nnum       # double duration of tremolo duplets
        if nden == 0: nden = 1          # occurs with illegal ABC like: "A2 1"
        num, den = simplify (nnum * s.unitLcur[0], nden * s.unitLcur[1])
        if den > MAX_NOTE_DENOMINATOR:
            num = int (round (MAX_NOTE_DENOMINATOR * float (num) / den))
            num, den = simplify (max ([num, 1]), MAX_NOTE_DENOMINATOR)
            s.warn ('duration too small: rounded to %d/%d' % (num, den), s.node_position (n))
        if n.name == 'rest' and ('Z' in n.t or 'X' in n.t):
            num, den = s.mdur
        noMsrRest = not (n.name == 'rest' and (num, den) == s.mdur)
        num, den = simplify (num, den * QUARTER_NOTE_SCALE)
        if num == DOTTED_NUMERATOR and noMsrRest: den = den // 2
        if num == DOUBLE_DOTTED_NUMERATOR and noMsrRest: den = den // 4
        if isgrace and den <= GRACE_MAX_DENOMINATOR: den = GRACE_DENOMINATOR
        if den not in NOTE_TYPES:
            s.warn ('illegal duration %d/%d' % (nnum, nden), s.node_position (n))

    def check_percussion_map (s, n, acc, note, oct):    # a percussion voice with I:percmap must map every pitch
        if not s.percVoice: return
        octq = int (oct) + s.gtrans
        key = (s.pid, acc + note, octq)
        if key in s.percMap or ('', acc + note, octq) in s.percMap: return
        if s.pMapFound:
            s.warn ('no I:percmap for: %s%s in part %s, voice %s' % (acc + note, -oct * ',' if oct < 0 else oct * "'", s.pid, s.vid),
                    s.node_position (n))
        s.percMap [key] = 1     # report each unmapped pitch once per part

    def note_decorations (s, n):    # decorations that apply to this note, and the deco node they came from
        decos = s.nextdecos
        ndeco = getattr (n, 'deco', 0)
        if ndeco:
            decos += [s.usrSyms.get (d, d).strip ('!+') for d in ndeco.t]
            decosNode = ndeco
        else:
            decosNode = s.nextdecosNode
        s.nextdecos = []
        s.nextdecosNode = None
        return decos, decosNode

    def check_ties (s, n, ptup, tstop, tstart):
        pts = getattr (n, 'pitches', [])
        if pts:                                     # pitches of the whole chord, kept in its first note
            if type (pts.pitch) == pObj: pts = [tuple (pts.pitch.t[-2:])]
            else: pts = [tuple (p.t[-2:]) for p in pts.pitch]
        for pt, vnum in sorted (s.ties.items ()):   # an open tie that no later note of the same pitch closes
            if vnum != s.overlayVnum: continue
            if pts and pt in pts: continue
            if getattr (n, 'chord', 0): continue
            if pt == ptup: continue
            if getattr (n, 'grace', 0): continue
            s.warn ('tie between different pitches: %s%s converted to slur' % pt, s.node_position (n))
            del s.ties [pt]
        if tstop: del s.ties [ptup]
        if tstart: s.ties [ptup] = s.overlayVnum

    def check_note_decorations (s, n, decos, decosNode, tupnotation, tstop, tstart):
        if s.trem:          # a tremolo sequence takes notations only at its first or last note
            if s.trem < 0: tupnotation = 'single'; s.trem = -s.trem
            if not tupnotation: return
            if tupnotation == 'stop' or tupnotation == 'single': s.trem = 0
        if not decos: return
        unhandled = [d for d in decos if not abc_decorations.classify (d).applies_to_note]
        if unhandled:
            s.warn ('unhandled note decorations: %s' % unhandled, s.node_position (decosNode))

    def check_lyrics (s, n):    # a lyric extend needs a syllable or extend on the previous note in the same verse
        for i, lyrobj in enumerate (n.objs):
            if lyrobj.name == 'syl': pass
            elif lyrobj.name == 'ext' and i in s.prevLyric: pass
            elif lyrobj.name == 'ext':
                s.warn ('lyric extend error', s.lyric_position (lyrobj))
                continue
            else: continue
            s.prevLyric [i] = 1

    def check_lyric_alignment (s, blk):     # every note pairs with one syllable of each verse, and every syllable with one note
        for verse, note in blk.bareNotes:
            s.error ('note has no lyric in verse %d' % (verse + 1), s.node_position (note))
        for verse, syl in blk.surplus:
            s.error ('lyric has no note in verse %d: %s' % (verse + 1, ''.join (syl.t)), s.lyric_position (syl))

    #---------------- fields ----------------

    def check_inline_field (s, node):
        position = s.node_position (node)
        s.check_caught_symbol (node, position)
        fieldtype, fieldval = node.t[0], ' '.join (node.t[1:])
        s.check_body_field (fieldtype, fieldval, position)

    def check_body_field (s, ftype, field, position):
        if not field: return
        if ftype == 'M':
            s.check_meter (field, position)
        elif ftype == 'K' or ftype == 'V':
            s.apply_clef (field)
        elif ftype == 'L':
            s.check_unit_length (field, position)
        elif ftype == 'I':
            s.check_info_field (field, position)
        elif ftype == 'Q':
            s.check_tempo (field, position)
        elif ftype == 'P':
            pass
        elif ftype in 'TCOAZNGHRBDFSU':
            s.warn ('**illegal header field in body: %s, content: %s' % (ftype, field), position)
        else:
            s.warn ('unhandled field: %s, content: %s' % (ftype, field), position)

    def measure_duration (s, field):    # (measure duration, message or None) for an M: field
        if field == 'C': field = '4/4'
        elif field == 'C|': field = '2/2'
        message = None
        if '/' not in field:
            message = 'M:%s not recognized, 4/4 assumed' % field
            field = '4/4'
        beats, btype = field.split ('/')[:2]
        try: mdur = simplify (eval (beats), int (btype))    # eval allows M:2+3/4
        except Exception:
            message = 'error in M:%s, 4/4 assumed' % field
            mdur = DEFAULT_MEASURE_DURATION
        return mdur, message

    def check_meter (s, field, position):
        if field == 'none': return
        s.mdur, message = s.measure_duration (field)
        if message: s.warn (message, position)

    def check_unit_length (s, field, position):
        try: s.unitLcur = tuple (map (int, field.split ('/')))
        except ValueError: s.unitLcur = DEFAULT_UNIT_LENGTH
        if len (s.unitLcur) == 1 or s.unitLcur[1] not in NOTE_TYPES:
            s.warn ('L:%s is not allowed, 1/8 assumed' % field, position)
            s.unitLcur = DEFAULT_UNIT_LENGTH

    def check_tempo (s, field, position):
        t = re.search (r'(\d)/(\d\d?)\s*=\s*(\d[.\d]*)|(\d[.\d]*)', field)
        rtxt = re.search (r'"([^"]*)"', field)
        if not t and not rtxt: return
        num, den = DEFAULT_TEMPO_UNIT
        if t:
            if t.group (4): num, den, rate = 1, s.unitLcur[1], t.group (4)              # old syntax Q:120
            else:           num, den, rate = int (t.group (1)), int (t.group (2)), t.group (3)
            try: float (rate)   # the regex admits more than one dot, e.g. Q:1/4=1.2.3
            except ValueError:
                s.warn ('conversion error: %s' % field, position)
                return
            num, den = simplify (num, den)
        if num != 1 and num != DOTTED_NUMERATOR: s.warn ('in Q: numerator in %d/%d not supported' % (num, den), position)

    def apply_clef (s, field):  # track the percussion switch and the octave transposition a clef sets
        clef = ClefField.parse (field)
        if clef.percussion is not None: s.percVoice = int (clef.percussion)
        shift = clef.transposition ()
        if shift is not None: s.gtrans = shift

    def check_info_field (s, x, position):
        dispatch_info_directive (x, DirectiveChecker (s, position))


class DirectiveChecker (DirectiveHandler):  # checks an I: directive, reporting at its position
    def __init__ (s, validator, position):
        s.v, s.position = validator, position

    def on_score (s, d): s.v.staveDefs.append ((d.text, s.position))

    def on_staff_redirection (s, d):
        for problem in s.v.layout.redirect (s.v.vid, d): s.v.warn (problem, s.position)

    def on_page_format (s, d): pass

    def on_midi (s, d):
        if d.drum: s.v.percMap [(s.v.pid, d.drum.accidental + d.drum.step, d.drum.octave)] = 1

    def on_percussion_mapping (s, d):
        if d.problem: s.v.warn (d.problem, s.position)
        s.v.percMap [(s.v.pid, d.accidental + d.step, d.octave)] = 1
        s.v.pMapFound = 1

    def on_graceword (s, d): pass   # applied when the lyrics are aligned (LyricAligner)
    def on_skipped (s, d): s.v.warn (d.message, s.position)
    def on_invalid (s, d): s.v.warn (d.message, s.position)
    def on_malformed (s, d): s.v.error (d.message, s.position)


def parse_abc (abc_text):
    '''Parse one ABC tune and return its diagnostics.

    - abc_text is one tune, optionally preceded by file-header lines (%% directives and fields).
      It is never modified.
    - The result holds every diagnostic the parse and the semantic walk produce, in encounter
      order. An unparseable tune yields at least one ERROR diagnostic; parse_abc never raises.
    - SourcePosition.line counts from 1 at the first line of abc_text, including any file-header
      lines the caller prepended. The caller subtracts its own header line count.
    - The grammar is built once at module level; parse_abc is safe to call from any thread
      because no module-level state is written during a call.
    - Messages the source converter stamps warn=0 carry Severity.ERROR; messages stamped
      warn=1 or with no flag carry Severity.WARNING.
    '''
    try:
        tune = parse_tune (abc_text)
    except AbcSyntaxError as err:   # only a syntax error in a voice is located
        position = None if err.voice is None else SourcePosition (*err.context ())
        return [Diagnostic (err.message, Severity.ERROR, position)]
    run = ParseRun (tune.header)
    Validator (run).validate (tune.fields, tune.voices)
    return run.diagnostics
