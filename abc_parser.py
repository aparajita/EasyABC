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
from pyparsing import Word, OneOrMore, Optional, Literal, NotAny, MatchFirst
from pyparsing import Group, one_of, Suppress, ZeroOrMore, Combine, FollowedBy
from pyparsing import srange, CharsNotIn, StringEnd, LineEnd, White, Regex
from pyparsing import nums, alphas, alphanums, ParseException, Forward
import re


class Severity (Enum):
    ERROR = 'error'
    WARNING = 'warning'


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


class SrcText:      # text paired with the 1-based source line every character came from
    # splitHeaderVoices rewrites the tune (comments stripped, fields folded to [X:...],
    # continuations joined, voices concatenated), so one rewritten row mixes characters
    # from several source lines. Carrying the line per character keeps every string
    # operation on the rewrite exact, so a node's offset always maps to its own line.
    __slots__ = ('text', 'lines')

    def __init__ (s, text='', lines=()):
        s.text, s.lines = text, list (lines)

    @classmethod
    def fromLine (cls, text, line):     # every character of text comes from source line 'line'
        return cls (text, [line] * len (text))

    def __add__ (s, o):
        return SrcText (s.text + o.text, s.lines + o.lines)

    def __bool__ (s):
        return bool (s.text)

    def slice (s, start, end):
        return SrcText (s.text [start:end], s.lines [start:end])

    def splitOn (s, regex):     # mirrors re.split with one capturing group: [between, match, between, ...]
        parts, pos = [], 0
        for m in regex.finditer (s.text):
            parts.append (s.slice (pos, m.start ()))
            parts.append (s.slice (m.start (), m.end ()))
            pos = m.end ()
        parts.append (s.slice (pos, len (s.text)))
        return parts

    def extract (s, regex):     # (all matches concatenated, the text with the matches removed)
        matches, rest, pos = SrcText (), SrcText (), 0
        for m in regex.finditer (s.text):
            rest = rest + s.slice (pos, m.start ())
            matches = matches + s.slice (m.start (), m.end ())
            pos = m.end ()
        return matches, rest + s.slice (pos, len (s.text))

def concatSrc (parts):
    out = SrcText ()
    for p in parts: out = out + p
    return out

def joinRows (rows):    # mirrors '\n'.join; the newline takes the line of the row it ends
    out = SrcText ()
    for i, row in enumerate (rows):
        if i:
            nl_line = out.lines [-1] if out.lines else (row.lines [0] if row.lines else 1)
            out = out + SrcText.fromLine ('\n', nl_line)
        out = out + row
    return out


@dataclass (frozen=True)
class ParsedVoice:
    id: str
    voicedef: object        # the leading V: inline pObj of the voice, or ''
    measures: list          # list of measures, each a list of pObj elements
    source: SrcText         # the rewritten voice text the grammar parsed (node.loc indexes into it)


def abc_grammar ():     # header, voice and lyrics grammar for ABC
    #-----------------------------------------------------------------
    # expressions that catch and skip some syntax errors (see corresponding parse expressions)
    #-----------------------------------------------------------------
    b1 = Word (u"-,'<>\u2019#", exact=1)    # catch misplaced chars in chords
    b2 = Regex ('[^H-Wh-w~=]*')             # same in user defined symbol definition
    b3 = Regex ('[^=]*')                    # same, second part

    #-----------------------------------------------------------------
    # ABC header (field_str elements are matched later with reg. epr's)
    #-----------------------------------------------------------------

    number = Word (nums).set_parse_action (lambda t: int (t[0]))
    field_str = Regex (r'[^]]*')  # match anything until end of field
    field_str.set_parse_action (lambda t: t[0].strip ())  # and strip spacing

    userdef_symbol  = Word (srange ('[H-Wh-w~]'), exact=1)
    fieldId = one_of ('K L M Q P I T C O A Z N G H R B D F S E r Y') # info fields
    X_field = Literal ('X') + Suppress (':') + field_str
    U_field = Literal ('U') + Suppress (':') + b2 + Optional (userdef_symbol, 'H') + b3 + Suppress ('=') + field_str
    V_field = Literal ('V') + Suppress (':') + Word (alphanums + '_') + field_str
    inf_fld = fieldId + Suppress (':') + field_str
    ifield = Suppress ('[') + (X_field | U_field | V_field | inf_fld) + Suppress (']')
    abc_header = OneOrMore (ifield) + StringEnd ()

    #---------------------------------------------------------------------------------
    # I:score with recursive part groups and {* grand staff marker
    #---------------------------------------------------------------------------------

    voiceId = Suppress (Optional ('*')) + Word (alphanums + '_')
    voice_gr = Suppress ('(') + OneOrMore (voiceId | Suppress ('|')) + Suppress (')')
    simple_part = voiceId | voice_gr | Suppress ('|')
    grand_staff = one_of ('{* {') + OneOrMore (simple_part) + Suppress ('}')
    part = Forward ()
    part_seq = OneOrMore (part | Suppress ('|'))
    brace_gr = Suppress ('{') + part_seq + Suppress ('}')
    bracket_gr = Suppress ('[') + part_seq + Suppress (']')
    part <<= MatchFirst (simple_part | grand_staff | brace_gr | bracket_gr | Suppress ('|'))
    abc_scoredef = Suppress (one_of ('staves score')) + OneOrMore (part)

    #----------------------------------------
    # ABC lyric lines (white space sensitive)
    #----------------------------------------

    skip_note   = one_of ('* -')
    extend_note = Literal ('_')
    measure_end = Literal ('|')
    syl_str     = CharsNotIn ('*-_| \t\n\\]')
    syl_chars   = Combine (OneOrMore (syl_str | Regex (r'\\.')))
    white       = Word (' \t')
    syllable    = syl_chars + Optional ('-')
    lyr_elem    = (syllable | skip_note | extend_note | measure_end) + Optional (white).suppress ()
    lyr_line    = Optional (white).suppress () + ZeroOrMore (lyr_elem)

    syllable.set_parse_action (posPobj ('syl'))
    skip_note.set_parse_action (posPobj ('skip'))
    extend_note.set_parse_action (posPobj ('ext'))
    measure_end.set_parse_action (posPobj ('sbar'))
    lyr_line_wsp = lyr_line.leave_whitespace ()   # parse actions must be set before calling leave_whitespace

    #---------------------------------------------------------------------------------
    # ABC voice (not white space sensitive)
    #---------------------------------------------------------------------------------

    inline_field =  Suppress ('[') + (inf_fld | U_field | V_field) + Suppress (']')
    lyr_fld = Suppress ('[') + Suppress ('w') + Suppress (':') + lyr_line_wsp + Suppress (']')  # lyric line
    lyr_blk = OneOrMore (lyr_fld)       # verses
    fld_or_lyr = inline_field | lyr_blk # inline field or block of lyric verses

    note_length = Optional (number, 1) + Group (ZeroOrMore ('/')) + Optional (number, 2)
    octaveHigh = OneOrMore ("'").set_parse_action (lambda t: len(t))
    octaveLow = OneOrMore (',').set_parse_action (lambda t: -len(t))
    octave  = octaveHigh | octaveLow

    basenote = one_of ('C D E F G A B c d e f g a b y')  # includes spacer for parse efficiency
    accidental = one_of ('^^ __ ^ _ =')
    rest_sym  = one_of ('x X z Z')
    slur_beg = one_of ("( (, (' .( .(, .('") + ~Word (nums)    # no tuplet_start
    slur_ends = OneOrMore (one_of (') .)'))

    long_decoration = Combine (one_of ('! +') + CharsNotIn ('!+ \n') + one_of ('! +'))
    staccato        = Literal ('.') + ~Literal ('|')    # avoid dotted barline
    pizzicato       = Literal ('!+!')   # special case: plus sign is old style deco marker
    decoration      = slur_beg | staccato | userdef_symbol | long_decoration | pizzicato
    decorations     = OneOrMore (decoration)

    tie = one_of ('.- -')
    rest = Optional (accidental) + rest_sym + note_length
    pitch = Optional (accidental) + basenote + Optional (octave, 0)
    note = pitch + note_length + Optional (tie) + Optional (slur_ends)
    dec_note = Optional (decorations) + pitch + note_length + Optional (tie) + Optional (slur_ends)
    chord_note = dec_note | rest | b1
    grace_notes = Forward ()
    chord = Suppress ('[') + OneOrMore (chord_note | grace_notes) + Suppress (']') + note_length + Optional (tie) + Optional (slur_ends)
    stem = note | chord | rest

    broken = Combine (OneOrMore ('<') | OneOrMore ('>'))

    tuplet_num   = Suppress ('(') + number
    tuplet_into  = Suppress (':') + Optional (number, 0)
    tuplet_notes = Suppress (':') + Optional (number, 0)
    tuplet_start = tuplet_num + Optional (tuplet_into + Optional (tuplet_notes))

    acciaccatura    = Literal ('/')
    grace_stem      = Optional (decorations) + stem
    grace_notes     <<= Group (Suppress ('{') + Optional (acciaccatura) + OneOrMore (grace_stem) + Suppress ('}'))

    text_expression  = Optional (one_of ('^ _ < > @'), '^') + Optional (CharsNotIn ('"'), "")
    chord_accidental = one_of ('# b =')
    triad            = one_of ('ma Maj maj M mi min m aug dim o + -')
    seventh          = one_of ('7 ma7 Maj7 M7 maj7 mi7 min7 m7 dim7 o7 -7 aug7 +7 m7b5 mi7b5')
    sixth            = one_of ('6 ma6 M6 mi6 min6 m6')
    ninth            = one_of ('9 ma9 M9 maj9 Maj9 mi9 min9 m9')
    elevn            = one_of ('11 ma11 M11 maj11 Maj11 mi11 min11 m11')
    thirt            = one_of ('13 ma13 M13 maj13 Maj13 mi13 min13 m13')
    suspended        = one_of ('sus sus2 sus4')
    chord_degree     = Combine (Optional (chord_accidental) + one_of ('2 4 5 6 7 9 11 13'))
    chord_kind       = Optional (seventh | sixth | ninth | elevn | thirt | triad) + Optional (suspended)
    chord_root       = one_of ('C D E F G A B') + Optional (chord_accidental)
    chord_bass       = one_of ('C D E F G A B') + Optional (chord_accidental) # needs a different parse action
    chordsym         = chord_root + chord_kind + ZeroOrMore (chord_degree) + Optional (Suppress ('/') + chord_bass)
    chord_sym        = chordsym + Optional (Literal ('(') + CharsNotIn (')') + Literal (')')).suppress ()
    chord_or_text    = Suppress ('"') + (chord_sym ^ text_expression) + Suppress ('"')

    volta_nums = Optional ('[').suppress () + Combine (Word (nums) + ZeroOrMore (one_of (', -') + Word (nums)))
    volta_text = Literal ('[').suppress () + Regex (r'"[^"]+"')
    volta = volta_nums | volta_text
    invisible_barline = one_of ('[|] []')
    dashed_barline = one_of (': .|')
    double_rep = Literal (':') + FollowedBy (':')   # otherwise ambiguity with dashed barline
    voice_overlay = Combine (OneOrMore ('&'))
    bare_volta = FollowedBy (Literal ('[') + Word (nums))   # no barline, but volta follows (volta is parsed in next measure)
    bar_left = (one_of ('[|: |: [: :') + Optional (volta)) | Optional ('|').suppress () + volta | one_of ('| [|')
    bars = ZeroOrMore (':') + ZeroOrMore ('[') + OneOrMore (one_of ('| ]'))
    bar_right = invisible_barline | double_rep | Combine (bars) | dashed_barline | voice_overlay | bare_volta

    errors =  ~bar_right + Optional (Word (' \n')) + CharsNotIn (':&|', exact=1)
    linebreak = Literal ('$') | ~decorations + Literal ('!')    # no need for I:linebreak !!!
    element = fld_or_lyr | broken | decorations | stem | chord_or_text | grace_notes | tuplet_start | linebreak | errors
    measure      = Group (ZeroOrMore (inline_field) + Optional (bar_left) + ZeroOrMore (element) + bar_right + Optional (linebreak) + Optional (lyr_blk))
    noBarMeasure = Group (ZeroOrMore (inline_field) + Optional (bar_left) + OneOrMore (element) + Optional (linebreak) + Optional (lyr_blk))
    abc_voice = ZeroOrMore (measure) + Optional (noBarMeasure | Group (bar_left)) + ZeroOrMore (inline_field).suppress () + StringEnd ()

    #----------------------------------------
    # I:percmap note [step] [midi] [note-head]
    #----------------------------------------

    white2 = (white | StringEnd ()).suppress ()
    w3 = Optional (white2)
    percid = Word (alphanums + '-')
    step = basenote + Optional (octave, 0)
    pitchg = Group (Optional (accidental, '') + step + FollowedBy (white2))
    stepg = Group (step + FollowedBy (white2)) | Literal ('*')
    midi = (Literal ('*') | number | pitchg | percid)
    nhd = Optional (Combine (percid + Optional ('+')), '')
    perc_wsp = Literal ('percmap') + w3 + pitchg + w3 + Optional (stepg, '*') + w3 + Optional (midi, '*') + w3 + nhd
    abc_percmap = perc_wsp.leave_whitespace ()

    #----------------------------------------------------------------
    # Parse actions to convert all relevant results into an abstract
    # syntax tree where all tree nodes are instances of pObj
    #----------------------------------------------------------------

    ifield.set_parse_action (lambda t: pObj ('field', t))
    grand_staff.set_parse_action (lambda t: pObj ('grand', t, 1)) # 1 = keep ordered list of results
    brace_gr.set_parse_action (lambda t: pObj ('bracegr', t, 1))
    bracket_gr.set_parse_action (lambda t: pObj ('bracketgr', t, 1))
    voice_gr.set_parse_action (lambda t: pObj ('voicegr', t, 1))
    voiceId.set_parse_action (lambda t: pObj ('vid', t, 1))
    abc_scoredef.set_parse_action (lambda t: pObj ('score', t, 1))
    note_length.set_parse_action (lambda t: pObj ('dur', (t[0], (t[2] << len (t[1])) >> 1)))
    chordsym.set_parse_action (lambda t: pObj ('chordsym', t))
    chord_root.set_parse_action (lambda t: pObj ('root', t))
    chord_kind.set_parse_action (lambda t: pObj ('kind', t))
    chord_degree.set_parse_action (lambda t: pObj ('degree', t))
    chord_bass.set_parse_action (lambda t: pObj ('bass', t))
    text_expression.set_parse_action (lambda t: pObj ('text', t))
    inline_field.set_parse_action (posPobj ('inline'))    # positioned: field checks in the body report at the field
    lyr_fld.set_parse_action (lambda t: pObj ('lyr_fld', t, 1))
    lyr_blk.set_parse_action (lambda t: pObj ('lyr_blk', t, 1)) # 1 = keep ordered list of lyric lines
    grace_notes.set_parse_action (doGrace)
    acciaccatura.set_parse_action (lambda t: pObj ('accia', t))
    note.set_parse_action (noteActn)
    rest.set_parse_action (restActn)
    decorations.set_parse_action (posPobj ('deco'))
    pizzicato.set_parse_action (lambda t: ['!plus!']) # translate !+!
    slur_ends.set_parse_action (lambda t: pObj ('slurs', t))
    chord.set_parse_action (lambda t: pObj ('chord', t, 1))
    dec_note.set_parse_action (noteActn)
    tie.set_parse_action (lambda t: pObj ('tie', t))
    pitch.set_parse_action (lambda t: pObj ('pitch', t))
    bare_volta.set_parse_action (lambda t: ['|']) # return barline that user forgot
    dashed_barline.set_parse_action (lambda t: ['.|'])
    bar_right.set_parse_action (lambda t: pObj ('rbar', t))
    bar_left.set_parse_action (lambda t: pObj ('lbar', t))
    broken.set_parse_action (posPobj ('broken'))  # positioned: an orphan broken symbol stays in the tree for the validator
    tuplet_start.set_parse_action (lambda t: pObj ('tup', t))
    linebreak.set_parse_action (lambda t: pObj ('linebrk', t))
    measure.set_parse_action (doMaat)
    noBarMeasure.set_parse_action (doMaat)
    b1.set_parse_action (errorWarn)
    b2.set_parse_action (errorWarn)
    b3.set_parse_action (errorWarn)
    errors.set_parse_action (errorWarn)

    return abc_header, abc_voice, abc_scoredef, abc_percmap


class pObj (object):    # every relevant parse result is converted into a pObj
    def __init__ (s, name, t, seq=0):   # t = list of nested parse results
        s.name = name   # name uniqueliy identifies this pObj
        rest = []       # collect parse results that are not a pObj
        attrs = {}      # new attributes
        for x in t:     # nested pObj's become attributes of this pObj
            if type (x) == pObj:
                attrs [x.name] = attrs.get (x.name, []) + [x]
            else:
                rest.append (x)             # collect non-pObj's (mostly literals)
        for name, xs in attrs.items ():
            if len (xs) == 1: xs = xs[0]    # only list if more then one pObj
            setattr (s, name, xs)           # create the new attributes
        s.t = rest      # all nested non-pObj's (mostly literals)
        s.objs = seq and t or []            # for nested ordered (lyric) pObj's

    def __repr__ (s):   # make a nice string representation of a pObj
        r = []
        for nm in dir (s):
            if nm.startswith ('_'): continue # skip build in attributes
            elif nm == 'name': continue     # redundant
            elif nm == 'loc': continue      # source offset, not an ABC token
            else:
                x = getattr (s, nm)
                if not x: continue          # s.t may be empty (list of non-pObj's)
                if type (x) == list:  r.extend (x)
                else:                 r.append (x)
        xs = []
        for x in r:     # recursively call __repr__
            if isinstance (x, str): xs.append (x)          # string -> no recursion
            else:                   xs.append (repr (x))   # pObj -> recursive call
        return '(' + s.name + ' ' +','.join (xs) + ')'


EXCERPT_WINDOW = 80     # rows longer than this are windowed around the offset
EXCERPT_RADIUS = EXCERPT_WINDOW // 2

def srcContext (source, loc):   # 'source' = the SrcText being parsed, 'loc' = char offset into it
    # returns (line, excerpt, column): the excerpt is the run of characters around loc that
    # came from the same source line, so the editor can find it in that line verbatim
    text, lines = source.text, source.lines
    loc = min (loc, len (text) - 1)     # a stamp can land just past the end of the text
    line = lines [loc]
    start = loc
    while start > 0 and lines [start - 1] == line and text [start - 1] != '\n': start -= 1
    end = loc
    while end < len (text) and lines [end] == line and text [end] != '\n': end += 1
    excerpt, column = text [start:end], loc - start
    if len (excerpt) > EXCERPT_WINDOW and column > EXCERPT_RADIUS:  # only window rows too wide to show whole
        cut = column - EXCERPT_RADIUS
        excerpt = excerpt [cut: column + EXCERPT_RADIUS]
        column -= cut
    return line, excerpt, column

def tokenStart (line, loc):     # first non-blank offset at or after loc
    # pyparsing hands an action the offset before whitespace skipping when the expression does not skip
    # whitespace itself (a Combine, or an expression starting with a lookahead), so the stamp moves to the token
    return loc + len (line [loc:]) - len (line [loc:].lstrip ())

def stampedPobj (name, line, loc, t):   # pObj(name, t) stamped with the source offset of its first token
    p = pObj (name, t)
    p.loc = tokenStart (line, loc)
    return p

def posPobj (name):             # parse-action factory for stampedPobj
    return lambda line, loc, t: stampedPobj (name, line, loc, t)

def noteActn (line, loc, t):
    if 'y' in t[0].t: return [] # discard spacer
    return stampedPobj ('note', line, loc, t)

def restActn (line, loc, t):
    return stampedPobj ('rest', line, loc, t)

def errorWarn (line, loc, t):   # misplaced symbols become error nodes; the validator reports them
    if not t[0]: return []      # only an error if catched string not empty
    return stampedPobj ('error', line, loc, t)

#-------------------------------------------------------------
# transformations of a measure (called by parse action doMaat)
#-------------------------------------------------------------

def simplify (a, b):    # divide a and b by their greatest common divisor
    x, y = a, b
    while b: a, b = b, a % b
    return x // a, y // a

def doBroken (prev, brk, x):    # returns whether the durations were changed
    nom1, den1 = prev.dur.t # duration of first note/chord
    nom2, den2 = x.dur.t    # duration of second note/chord
    if  brk == '>':
        nom1, den1  = simplify (3 * nom1, 2 * den1)
        nom2, den2  = simplify (1 * nom2, 2 * den2)
    elif brk == '<':
        nom1, den1  = simplify (1 * nom1, 2 * den1)
        nom2, den2  = simplify (3 * nom2, 2 * den2)
    elif brk == '>>':
        nom1, den1  = simplify (7 * nom1, 4 * den1)
        nom2, den2  = simplify (1 * nom2, 4 * den2)
    elif brk == '<<':
        nom1, den1  = simplify (1 * nom1, 4 * den1)
        nom2, den2  = simplify (7 * nom2, 4 * den2)
    else: return False      # give up
    prev.dur.t = nom1, den1 # change duration of previous note/chord
    x.dur.t = nom2, den2    # and current note/chord
    return True

def convertBroken (t):  # convert broken rhythms to normal note durations
    prev = None # the last note/chord before the broken symbol
    brk = None  # (index, symbol) of the broken symbol awaiting its second note
    remove = [] # indexes to applied broken symbols (to be deleted) in measure
    for i, x in enumerate (t):  # scan all elements in measure
        if x.name == 'note' or x.name == 'chord' or x.name == 'rest':
            if brk:                 # a broken symbol was encountered before
                if prev and doBroken (prev, brk[1], x):     # change duration previous note/chord/rest and current one
                    remove.insert (0, brk[0])               # highest index first
                brk = None          # a broken symbol without a note on both sides stays in the tree
            else:
                prev = x            # remember the last note/chord/rest
        elif x.name == 'broken':
            brk = (i, x.t[0])       # remember the broken symbol
    for i in remove: del t[i]       # delete applied broken symbols from high to low

def ptc2midi (n):       # convert parsed pitch attribute to a midi number
    pt = getattr (n, 'pitch', '')
    if pt:
        p = pt.t
        if len (p) == 3: acc, step, oct = p
        else:       acc = ''; step, oct = p
        nUp = step.upper ()
        oct = (4 if nUp == step else 5) + int (oct)
        midi = oct * 12 + [0,2,4,5,7,9,11]['CDEFGAB'.index (nUp)] + {'^':1,'_':-1}.get (acc, 0) + 12
    else: midi = 130    # all non pitch objects first
    return midi

def convertChord (t):   # convert chord to sequence of notes in musicXml-style
    ins = []
    for i, x in enumerate (t):
        if x.name == 'chord':
            if not hasattr (x, 'note'):         # chords containing only rests, or only misplaced symbols
                elms = [nt for nt in x.objs if nt.name == 'error']  # keep misplaced symbols caught inside the chord
                if hasattr (x, 'rest'):
                    if type (x.rest) == list: x.rest = x.rest[0] # more rests == one rest
                    elms.insert (0, x.rest)     # just output a single rest, no chord
                ins.insert (0, (i, elms))
                continue
            num1, den1 = x.dur.t                # chord duration
            tie = getattr (x, 'tie', None)      # chord tie
            slurs = getattr (x, 'slurs', [])    # slur endings
            if type (x.note) != list: x.note = [x.note]    # when chord has only one note ...
            elms = []; j = 0
            for nt in x.objs:   # all chord elements (note | decorations | rest | grace note | error)
                if nt.name == 'note':
                    num2, den2 = nt.dur.t           # note duration * chord duration
                    nt.dur.t = simplify (num1 * num2, den1 * den2)
                    if tie: nt.tie = tie            # tie on all chord notes
                    if j == 0 and slurs: nt.slurs = slurs   # slur endings only on first chord note
                    if j > 0: nt.chord = pObj ('chord', [1]) # label all but first as chord notes
                    else:                           # remember all pitches of the chord in the first note
                        pitches = [n.pitch for n in x.note] # to implement conversion of erroneous ties to slurs
                        nt.pitches = pObj ('pitches', pitches)
                    j += 1
                if nt.name not in ['dur','tie','slurs','rest']: elms.append (nt)    # 'error' nodes pass through here
            ins.insert (0, (i, elms))           # chord position, [note|decotation|grace note|error]
    for i, notes in ins:                        # insert from high to low
        for nt in reversed (notes):
            t.insert (i+1, nt)                  # insert chord notes after chord
        del t[i]                                # remove chord itself

def doMaat (t):             # t is a Group() result -> the measure is in t[0]
    convertBroken (t[0])    # remove all broken rhythms and convert to normal durations; 'error' nodes are neither note nor broken, so they stay
    convertChord (t[0])     # replace chords by note sequences in musicXML style

def doGrace (t):        # t is a Group() result -> the grace sequence is in t[0]
    convertChord (t[0]) # a grace sequence may have chords
    for nt in t[0]:     # flag all notes within the grace sequence; other names ('error' included) are left as they are
        if nt.name == 'note': nt.grace = 1 # set grace attribute
    return t[0]         # ungroup the parse result

def nextLyricBar (lyr, i):  # index of the first '|' in lyr at or after i, or None
    for j in range (i, len (lyr)):
        if lyr[j].name == 'sbar': return j
    return None

def alignLyr (vce, lyrs, blk):
    # pairs the syllables of every verse in blk with the notes in vce, appending one lyric object per verse to each
    # note; a note without a syllable gets a filler and is recorded in blk.bareNotes, a syllable without a note is
    # recorded in blk.surplus, both as (verse index, node). A '|' in a verse resynchronises to the next bar line.
    empty_el = pObj ('leeg', '*')
    blk.bareNotes = []
    blk.surplus = []
    for k, lyr in enumerate (lyrs): # lyr = one full line of lyrics
        i = 0               # syl counter
        for elem in vce:    # reiterate the voice block for each lyrics line; only notes and rbars consume syllables, an 'error' element consumes none
            if elem.name == 'note' and not (hasattr (elem, 'chord') or hasattr (elem, 'grace')):
                if i < len (lyr) and lyr[i].name != 'sbar':
                    lr = lyr [i]
                    lr.t[0] = lr.t[0].replace ('%5d',']')
                    i += 1
                else:
                    lr = empty_el
                    blk.bareNotes.append ((k, elem))
                elem.objs.append (lr)
            if elem.name == 'rbar':
                j = nextLyricBar (lyr, i)
                if j is not None:
                    blk.surplus.extend ((k, x) for x in lyr [i:j])
                    i = j + 1
        blk.surplus.extend ((k, x) for x in lyr [i:] if x.name != 'sbar')
    return vce

slur_move = re.compile (r'(?<![!+])([}><][<>]?)(\)+)')  # (?<!...) means: not preceeded by ...
mm_rest = re.compile (r'([XZ])(\d+)')
bar_space = re.compile (r'([:|][ |\[\]]+[:|])')         # barlines with spaces
def fixSlurs (x):   # repair slurs when after broken sign or grace-close
    def f (mo):     # replace a multi-measure rest by single measure rests
        n = int (mo.group (2))
        return (n * (mo.group (1) + '|')) [:-1]
    def g (mo):     # squash spaces in barline expressions
        return mo.group (1).replace (' ','')
    x = mm_rest.sub (f, x)
    x = bar_space.sub (g, x)
    return slur_move.sub (r'\2\1', x)

headerFieldRE = re.compile (r'\[[^]]*\]')   # one folded [X:...] field in the header string
keyFieldRE = re.compile (r'(\[K:[^]]*\])')
voiceFieldRE = re.compile (r'(\[V:[^]]*\])')
partMarkRE = re.compile (r'\[P:.\]')

def escField (fld):     # fold a field into inline form, escaping every ']' (hope nobody uses %5d in a field)
    out = SrcText.fromLine ('[', fld.lines [0])
    for ch, line in zip (fld.text, fld.lines):
        out = out + SrcText.fromLine ('%5d' if ch == ']' else ch, line)
    return out + SrcText.fromLine (']', fld.lines [-1])

def leadLine (src, fallback):   # the source line a synthetic prefix to src is attributed to
    return src.lines [0] if src.lines else fallback

def splitHeaderVoices (abctext):
    # returns (header, voices):
    #   header - SrcText: all header fields folded into one string of [X:...] fields
    #   voices - [(voice id, SrcText)] in document order
    r1 = re.compile (r'%.*$')           # comments
    r2 = re.compile (r'^([A-Zw]:.*$)|\[[A-Zw]:[^]]*]$')     # information field, including lyrics
    r3 = re.compile (r'^%%(?=[^%])')    # directive: ^%% folowed by not a %
    xs, nx, mcont, fcont = [], 0, 0, 0  # result rows, X-encountered, music continuation, field continuation
    mln = fln = SrcText ()              # music line, field line
    def foldField ():
        nonlocal mln
        mln = mln + escField (fln)
    def emitRow ():
        nonlocal mln
        xs.append (mln); mln = SrcText ()
    for curLine, x in enumerate (abctext.splitlines (), 1):
        x = x.strip ()
        if not x and nx == 1: break     # end of tune (empty line)
        if x.startswith ('X:'):
            if nx == 1: break           # second tune starts without an empty line !!
            nx = 1                      # start first tune
        x = r3.sub ('I:', x)            # replace %% -> I:
        x2 = r1.sub ('', x)             # remove comment
        while x2.endswith ('*') and not (x2.startswith ('w:') or x2.startswith ('+:') or 'percmap' in x2):
            x2 = x2[:-1]                # remove old syntax for right adjusting
        if not x2: continue             # empty line
        if x2[:2] == 'W:': continue     # skip W: lyrics
        if x2[:2] == '+:':              # field continuation
            fln = fln + SrcText.fromLine (x2[2:], curLine)
            continue
        ro = r2.match (x2)              # single field on a line
        if ro:                          # field -> inline_field, escape all ']'
            if fcont:                   # old style \-info-continuation active
                fcont = x2 [-1] == '\\' # possible further \-info-continuation
                fln = fln + SrcText.fromLine (re.sub (r'^.:(.*?)\\*$', r'\1', x2), curLine)  # add continuation, remove .: and \
                continue
            if fln: foldField ()
            if x2.startswith ('['): x2 = x2.strip ('[]')
            fcont = x2 [-1] == '\\'     # first encounter of old style \-info-continuation
            fln = SrcText.fromLine (x2.rstrip ('\\'), curLine)    # remove continuation from field and inline brackets
            continue
        if nx == 1:                     # x2 is a new music line
            fcont = 0                   # stop \-continuations (-> only adjacent \-info-continuations are joined)
            if fln:
                foldField ()
                fln = SrcText ()
            # fixSlurs runs per source line: it changes the text's length, and only here is every
            # character of the text it rewrites still from one line
            music = SrcText.fromLine (fixSlurs (x2.rstrip ('\\')), curLine)
            if mcont:
                mcont = x2 [-1] == '\\'
                mln = mln + music
            else:
                if mln: emitRow ()
                mcont = x2 [-1] == '\\'
                mln = music
            if not mcont: emitRow ()
    if fln: foldField ()
    if mln: emitRow ()
    if not xs: return SrcText (), []    # nothing but comments and blank lines

    hs = xs [0].splitOn (keyFieldRE)            # look for end of header K:
    if len (hs) == 1: header = hs[0]; xs [0] = SrcText ()          # no K: present
    else: header = hs [0] + hs [1]; xs [0] = concatSrc (hs[2:])    # h[1] is the first K:
    body = joinRows (xs)                        # the rest is body text
    hfs, vfs = SrcText (), SrcText ()
    for m in headerFieldRE.finditer (header.text):
        x = m.group ()[1:-1]
        if not x: continue
        fld = header.slice (m.start (), m.end ())
        if x[0] == 'V': vfs = vfs + fld         # filter voice- and midi-definitions
        elif x[:6] == 'I:MIDI': vfs = vfs + fld # from the header to vfs
        elif x[:9] == 'I:percmap': vfs = vfs + fld  # and also percmap
        else: hfs = hfs + fld                   # all other fields stay in header
    header = hfs
    body = vfs + body                           # prepend voice/midi from header before the body

    firstVoiceDef = SrcText.fromLine ('[V:1]', leadLine (body, leadLine (header, 1)))
    xs = body.text.split ('[V:')
    if len (xs) == 1: body = firstVoiceDef + body   # abc has no voice defs at all
    elif re.sub (r'\[[A-Z]:[^]]*\]', '', xs[0]).strip ():   # remove inline fields from starting text, if any
        body = firstVoiceDef + body     # abc with voices has no V: at start

    r1 = re.compile (r'\[V:\s*(\S*)[ \]]') # get voice id from V: field (skip spaces betwee V: and ID)
    vmap = {}                           # {voice id -> [voice abc SrcText]}
    vorder = {}                         # mark document order of voices
    xs = body.splitOn (voiceFieldRE)    # split on every V-field (V-fields included in split result list)
    pm, preVoice = xs[0].extract (partMarkRE)   # all P:-marks after K: but before first V:
    if pm: xs[2] = pm + xs[2]           # prepend P:-marks to the text of the first voice
    header = header + preVoice          # text between K: and first V: goes to the header
    i = 1
    while i < len (xs):             # xs = ['', V-field, voice abc, V-field, voice abc, ...]
        vce, abc = xs[i:i+2]
        id = r1.search (vce.text).group (1)             # get voice ID from V-field
        if not id: id, vce = '1', SrcText.fromLine ('[V:1]', leadLine (vce, 1))    # voice def has no ID
        vmap[id] = vmap.get (id, []) + [vce, abc]       # collect abc-text for each voice id (include V-fields)
        if id not in vorder: vorder [id] = i            # store document order of first occurrence of voice id
        i += 2
    ixs = sorted ([(i, id) for id, i in vorder.items ()])   # restore document order of voices
    return header, [(id, concatSrc (vmap [id])) for i, id in ixs]

def decodeInput (data_string):
    try:        unicode_string = data_string.decode ('utf-8')
    except:
        try:    unicode_string = data_string.decode ('latin-1')
        except: raise ValueError ('data not encoded in utf-8 nor in latin-1')
    return unicode_string

def expand_abc_include (abctxt):
    ys = []
    for x in abctxt.splitlines ():
        if x.startswith ('%%abc-include') or x.startswith ('I:abc-include'):
            try:
                with open (x[13:].strip (), 'rb') as fobj: x = decodeInput (fobj.read ())
            except Exception: x = None  # an unreadable include contributes nothing
        if x != None: ys.append (x)
    return '\n'.join (ys)


class ParseRun:     # everything one parse_abc call produces and every position table it needs
    def __init__ (s, abc_text):
        s.header, s.voices = splitHeaderVoices (abc_text)
        fields = list (headerFieldRE.finditer (s.header.text))
        s.header_fields = [m.group () for m in fields]                  # header_fields[i] is the text of the i-th field
        s.header_field_lines = [s.header.lines [m.start ()] for m in fields]
        s.diagnostics = []

    def report (s, message, severity, position):
        s.diagnostics.append (Diagnostic (message, severity, position))

    def position_of (s, node, source):
        return SourcePosition (*srcContext (source, node.loc))

    def header_position_of (s, field_index):
        return SourcePosition (s.header_field_lines [field_index], s.header_fields [field_index], 0)


#-------------------------------------------------------------
# I:score / I:staves tree -> voice id lists (used by the validator)
#-------------------------------------------------------------

def firstVoice (x):             # a merged voice group stands for its first voice
    return x.objs[0] if x.name == 'voicegr' else x

def staffGroups (p):            # [vid | [vid, ...]] per staff: a voice group merges into one staff
    xs = []
    for x in p.objs:
        if type (x) == pObj:
            us = staffGroups (x)
            if x.name == 'voicegr': xs.append (us)
            else: xs.extend (us)
        elif p.t[0] not in '{*': xs.append (p.t[0])     # '{' and '{*' are grand staff markers, not voice ids
    return xs

def grandStaves (p, names):     # [[vid, ...] | vid] with an entry per accepted grand staff; names = {vid: part name}
    xs = []
    for x in p.objs:
        if type (x) == pObj:
            x = firstVoice (x)
            us = grandStaves (x, names)
            if x.name == 'grand':
                vids = [firstVoice (y).objs[0] for y in x.objs[1:]]     # the voice ids in the grand staff
                accept = sum (1 for u in vids if names.get (u, '')) == 1   # a grand staff when exactly one voice is named
                if accept or us[0] == '{*': xs.append (us[1:])          # discard the '{' or '{*' marker
                else: xs.extend (us[1:])                                # rejected: its voices stay separate
            else: xs.extend (us)
        else: xs.append (p.t[0])
    return xs

def asStaffList (x):            # a single voice id becomes a one-voice staff
    return [x] if isinstance (x, str) else x


LYRIC_FIELD_RE = re.compile (r'\[w:(.*?)\]')        # one folded [w:...] field inside an excerpt
PERC_SOUNDS = 'acoustic-bass-drum,35;bass-drum-1,36;side-stick,37;acoustic-snare,38;hand-clap,39;electric-snare,40;low-floor-tom,41;closed-hi-hat,42;high-floor-tom,43;pedal-hi-hat,44;low-tom,45;open-hi-hat,46;low-mid-tom,47;hi-mid-tom,48;crash-cymbal-1,49;high-tom,50;ride-cymbal-1,51;chinese-cymbal,52;ride-bell,53;tambourine,54;splash-cymbal,55;cowbell,56;crash-cymbal-2,57;vibraslap,58;ride-cymbal-2,59;hi-bongo,60;low-bongo,61;mute-hi-conga,62;open-hi-conga,63;low-conga,64;high-timbale,65;low-timbale,66;high-agogo,67;low-agogo,68;cabasa,69;maracas,70;short-whistle,71;long-whistle,72;short-guiro,73;long-guiro,74;claves,75;hi-wood-block,76;low-wood-block,77;mute-cuica,78;open-cuica,79;mute-triangle,80;open-triangle,81'
PERC_SOUND_NAMES = [x.split (',')[0] for x in PERC_SOUNDS.split (';')]  # general midi channel 10 sound names

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
    - the ParseException messages in MusicXml.parse: reported by reportParseException.
    '''
    typeMap = {1:'long', 2:'breve', 4:'whole', 8:'half', 16:'quarter', 32:'eighth', 64:'16th', 128:'32nd', 256:'64th'}
    dynaMap = {'p':1,'pp':1,'ppp':1,'pppp':1,'f':1,'ff':1,'fff':1,'ffff':1,'mp':1,'mf':1,'sfz':1}
    wedgeMap = {'>(':1, '>)':1, '<(':1,'<)':1,'crescendo(':1,'crescendo)':1,'diminuendo(':1,'diminuendo)':1}
    artMap = {'.':'staccato','>':'accent','accent':'accent','wedge':'staccatissimo','tenuto':'tenuto',
              'breath':'breath-mark','marcato':'strong-accent','^':'strong-accent','slide':'scoop'}
    ornMap = {'trill':'trill-mark','T':'trill-mark','turn':'turn','uppermordent':'inverted-mordent','lowermordent':'mordent',
              'pralltriller':'inverted-mordent','mordent':'mordent','invertedturn':'inverted-turn'}
    tecMap = {'upbow':'up-bow', 'downbow':'down-bow', 'plus':'stopped','open':'open-string','snap':'snap-pizzicato',
              'thumb':'thumb-position'}
    capoMap = {'fine':1, 'D.S.':1, 'D.C.':1, 'dacapo':1, 'dacoda':1, 'coda':1, 'segno':1}
    slurMap = {'(':1, '.(':1, '(,':1, "('":1, '.(,':1, ".('":1}
    clefLineMap = {'B':'treble', 'G':'alto1', 'E':'alto2', 'C':'alto', 'A':'tenor', 'F':'bass3', 'D':'bass'}
    uSyms = {'~':'roll', 'H':'fermata','L':'>','M':'lowermordent','O':'coda',
             'P':'uppermordent','S':'segno','T':'trill','u':'upbow','v':'downbow'}
    tremoloPairs = ['/-','//-','///-','////-']
    tremoloSingles = ['/','//','///']
    stringDecos = '0123456'     # string numbers are handled as technical notations

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
        s.usrSyms = dict (s.uSyms)      # user defined symbols
        s.nextdecos = []        # decorations pending for the next note
        s.nextdecosNode = None  # the deco node the first pending decoration came from
        s.ties = {}             # {(step, octave): overlay voice number} for all open ties
        s.overlayVnum = 0       # overlay voice number of the current measure
        s.prevLyric = {}        # {verse number: 1} when the previous note carried a lyric in that verse
        s.voiceDefs = {}        # {vid: (part name, abbreviation, voice definition text)}
        s.staveDefs = []        # [(I:score / I:staves text, position)] in encounter order
        s.staves = []           # [[vid, ...] per staff]
        s.grands = []           # [[vid, ...] per grand staff]
        s.gStaffNums = {}       # vid -> staff number within its grand staff
        s.gStaffNumsOrg = {}    # the allocation before any I:staff redirection
        s.gNstaves = {}         # vid -> number of staves of its grand staff
        s.vcepid = {}           # vid -> part id (the first voice of its grand staff)
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
        line, excerpt, column = srcContext (s.voice.source, node.loc)
        for m in LYRIC_FIELD_RE.finditer (excerpt):
            if m.start (1) <= column <= m.end ():
                excerpt = m.group (1)
                column = max (0, min (column - m.start (1), len (excerpt)))
                break
        return SourcePosition (line, excerpt, column)

    def warn (s, message, position=None): s.run.report (message, Severity.WARNING, position)
    def error (s, message, position=None): s.run.report (message, Severity.ERROR, position)

    #---------------- entry ----------------

    def validate (s, header_fields, voices):
        for i, fld in enumerate (header_fields):
            position = s.run.header_position_of (i)
            if fld.name == 'field': s.check_header_field (fld, position)
            else: s.warn ('unexpected header item: %s' % fld, position)
        s.collect_voice_definitions (voices)
        s.check_stave_definitions ()
        for voice in voices: s.check_voice (voice)
        s.check_score_voice_ids ([voice.id for voice in voices])

    #---------------- header ----------------

    def check_caught_symbol (s, fld, position):     # a misplaced character the U: grammar caught inside the field
        caught = getattr (fld, 'error', None)
        if caught: s.error ('misplaced symbol: %s' % caught.t[0], position)

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
        if len (unitL) == 1 or unitL[1] not in s.typeMap:
            s.warn ('L:%s is not allowed, 1/8 assumed' % field, position)
            unitL = DEFAULT_UNIT_LENGTH
        return unitL

    def collect_voice_definitions (s, voices):      # voice names, and every I:score in the voices
        for voice in voices:
            s.voice = voice
            pname, psubnm = '', ''
            vcedef = voice.voicedef
            if not vcedef:      # simple abc without voice definitions
                s.voiceDefs [voice.id] = pname, psubnm, ''
            else:
                if voice.id != vcedef.t[1]:
                    s.warn ('voice ids unequal: %s (reg-ex) != %s (grammar)' % (voice.id, vcedef.t[1]), s.node_position (vcedef))
                rn = re.search (r'(?:name|nm)="([^"]*)"', vcedef.t[2])
                if rn: pname = rn.group (1)
                rn = re.search (r'(?:subname|snm|sname)="([^"]*)"', vcedef.t[2])
                if rn: psubnm = rn.group (1)
                text = vcedef.t[2].replace ('"%s"' % pname, '""').replace ('"%s"' % psubnm, '""')  # names must not match clef keywords
                s.voiceDefs [voice.id] = pname, psubnm, text
            for measure in voice.measures:
                for x in measure:
                    if x.name != 'inline': continue
                    text = x.t[1]
                    if text.startswith ('score') or text.startswith ('staves'):
                        s.staveDefs.append ((text.replace ('%5d',']'), s.node_position (x)))
        s.voice = None

    def check_stave_definitions (s):
        for vid in s.voiceDefs: s.vcepid [vid] = vid            # default: each voice is its own part
        if not s.staveDefs: return
        for x, position in s.staveDefs [1:]: s.warn ('%%%%%s dropped, multiple stave mappings not supported' % x, position)
        x, position = s.staveDefs [0]                           # only the first I:score is honoured
        try: score = abc_scoredef.parse_string (x) [0]
        except ParseException as err:
            s.error ('syntax error in I:%s at column %d' % (x, err.col), position)
            return
        names = dict ((vid, pname) for vid, (pname, _, _) in s.voiceDefs.items ())
        s.staves = [asStaffList (x) for x in staffGroups (score)]
        s.grands = [asStaffList (x) for x in grandStaves (score, names)]
        merged = {}                                             # first voice of a merged staff -> all its voices
        for vgr in s.staves:
            if len (vgr) > 1: merged [vgr[0]] = vgr
        for gstaff in s.grands:
            if len (gstaff) == 1: continue
            for v, stf_num in zip (gstaff, range (1, len (gstaff) + 1)):
                for vx in merged.get (v, [v]):
                    s.gStaffNums [vx] = stf_num
                    s.gNstaves [vx] = len (gstaff)
        s.gStaffNumsOrg = s.gStaffNums.copy ()
        for xmlpart in s.grands:
            pid = xmlpart [0]
            for stf in xmlpart:
                for v in merged.get (stf, [stf]): s.vcepid [v] = pid

    def check_score_voice_ids (s, vids):    # every voice an I:score names must exist
        for staves in (s.staves, s.grands):
            if not staves: continue
            vidsnew = []
            for voice_ids in staves:
                found = [vid for vid in voice_ids if vid in vids]
                for vid in voice_ids:
                    if vid not in vids: s.warn ('score partname %s does not exist' % vid)
                if found: vidsnew.append (found [0])
            vids = vidsnew

    #---------------- voices and measures ----------------

    def check_voice (s, voice):
        s.voice = voice
        s.vid = voice.id
        s.pid = s.vcepid.get (voice.id, voice.id)
        s.unitLcur = s.unitL
        s.percVoice = 0
        s.gtrans = 0
        s.overlayVnum = 0
        voicedef = s.voiceDefs.get (voice.id, ('', '', ''))[2]
        if 'perc' not in voicedef: s.apply_clef (s.headerKey)   # a percussion voice ignores the header key
        s.mdur = s.measure_duration (s.headerMeter)[0]          # the header meter was already checked at its field
        if voicedef: s.apply_clef (voicedef)
        overlay = False
        for measure in voice.measures:
            s.overlayVnum = s.overlayVnum + 1 if overlay else 0
            overlay = s.check_measure (measure)
        s.voice = None

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
            if d in s.dynaMap or d in s.wedgeMap or d.startswith ('8v') or d in ['ped', 'ped-up'] or d in s.capoMap: continue
            elif d == '(' or d == '.(': continue
            elif d in s.tremoloPairs:
                s.ntup, s.tupnts, s.trem, s.intrem = 2, 0, len (d) - 1, 1
            elif d in s.tremoloSingles: s.trem = - len (d)
            elif d == 'rbstop': continue
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
        if den not in s.typeMap:
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
        unhandled = []
        for d in decos:
            if d in s.slurMap or d == 'fermata' or d == 'H' or d == 'arpeggio': continue
            if d in ['~(', '~)', '-(', '-)']: continue      # glissando and slide
            if d in s.artMap or d in s.ornMap or d in ['trill(', 'trill)'] or d in s.tecMap or d in s.stringDecos: continue
            unhandled.append (d)
        if unhandled:
            position = s.node_position (decosNode) if decosNode is not None else None
            s.warn ('unhandled note decorations: %s' % unhandled, position)

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
        if len (s.unitLcur) == 1 or s.unitLcur[1] not in s.typeMap:
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
        if re.search (r'perc|map', field):
            r = re.search (r'(perc|map)\s*=\s*(\S*)', field)
            s.percVoice = 0 if r and r.group (2) not in ['on','true','perc'] else 1
            field = re.sub (r'(perc|map)\s*=\s*(\S*)', '', field)
        clef, gtrans = 0, 0
        clefn = re.search (r'alto1|alto2|alto4|alto|tenor|bass3|bass|treble|perc|none|tab', field)
        clefm = re.search (r"(?:^m=| m=|middle=)([A-Ga-g])([,']*)", field)
        trans_oct2 = re.search (r'octave=([-+]?\d)', field)
        trans_oct = re.search (r'([+-^_])(8|15)', field)
        if clefn: clef = clefn.group ()
        if clefm:
            note, octstr = clefm.groups ()
            nUp = note.upper ()
            octnum = (4 if nUp == note else 5) + (len (octstr) if "'" in octstr else -len (octstr))
            gtrans = (3 if nUp in 'AFD' else 4) - octnum
            if clef not in ['perc', 'none']: clef = s.clefLineMap [nUp]
        if clef:
            s.gtrans = gtrans
            if clef == 'none': return       # the clef without a sign ends the field's effect here
            if trans_oct:
                n = trans_oct.group (1) in '-_' and -1 or 1
                if trans_oct.group (2) == '15': n *= 2
                if trans_oct.group (1) in '+-': s.gtrans += n
        if trans_oct2: s.gtrans = gtrans + int (trans_oct2.group (1))

    def check_info_field (s, x, position):
        if x.startswith ('score') or x.startswith ('staves'):
            s.staveDefs.append ((x, position))
        elif x.startswith ('staffwidth'): s.warn ('skipped I-field: %s' % x, position)
        elif x.startswith ('staff'): s.check_staff_redirection (x, position)
        elif x.startswith (('scale', 'pageheight', 'pagewidth', 'leftmargin', 'rightmargin', 'topmargin', 'botmargin')):
            if not re.search (r'[^.\d]*([\d.]+)\s*(cm|in|pt)?', x): s.warn ('error in page format: %s' % x, position)
        elif x.startswith ('MIDI') or x.startswith ('midi'):
            r3 = re.search (r"drummap\s+([_=^]*)([A-Ga-g])([,']*)\s+(\d+)", x)
            if r3:
                acc, step, oct, midi = r3.groups ()
                oct = -len (oct) if ',' in x else len (oct)
                s.percMap [(s.pid, acc + step, oct)] = 1
        elif x.startswith ('percmap'):
            s.check_percussion_mapping (x, position)
            s.pMapFound = 1
        else: s.warn ('skipped I-field: %s' % x, position)

    def check_staff_redirection (s, x, position):
        r1 = re.search (r'staff *([+-]?)(\d)', x)
        if not r1:
            s.warn ('not a valid staff redirection: %s' % x, position)
            return
        sign = r1.group (1)
        num = int (r1.group (2))
        gstaff = s.gStaffNums.get (s.vid, 0)
        if sign:
            num = (sign == '-') and gstaff - num or gstaff + num
        else:
            try: vabc = s.staves [num - 1][0]
            except IndexError: vabc = 0; s.warn ('abc staff %s does not exist' % num, position)
            num = s.gStaffNumsOrg.get (vabc, 0)
        if gstaff and num > 0 and num <= s.gNstaves [s.vid]:
            s.gStaffNums [s.vid] = num
        else: s.warn ('could not relocate to staff: %s' % r1.group (), position)

    def check_percussion_mapping (s, x, position):   # I:percmap note [step] [midi] [note-head]
        try: _, p1, _, p3, _ = abc_percmap.parse_string (x).as_list ()    # percmap, abc-note, display-step, midi, note-head
        except ParseException as err:
            s.error ('syntax error in I:%s at column %d' % (x, err.col), position)
            return
        acc, astep, aoct = p1
        if isinstance (p3, str) and p3 != '*': s.check_drum_sound (p3.lower (), position)
        s.percMap [(s.pid, acc + astep, aoct)] = 1

    def check_drum_sound (s, sndnm, position):  # every part of a sound name must match a general midi drum sound
        pnms = sndnm.split ('-')
        names = PERC_SOUND_NAMES [:]
        _f = lambda ip, xs, pnm: ip < len (xs) and xs[ip].find (pnm) > -1
        for ip, pnm in enumerate (pnms):
            names = [nm for nm in names if _f (ip, nm.split ('-'), pnm)]
            if len (names) <= 1: break
        if not names: s.warn ('drum sound: %s not found' % sndnm, position)


def reportParseException (run, err, position):
    xs = err.line[err.col-1:]
    if   re.search (r'\[U:', xs):
        message = 'illegal user defined symbol: %s' % xs[1:]
    elif re.search (r'\[[OAPZNGHRBDFSXTCIU]:', xs):
        message = 'header-only field %s appears after K:' % xs[1:]
    else:
        message = 'Syntax error at column %d' % err.col
    run.report (message, Severity.ERROR, position)


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
    run = ParseRun (abc_text)
    try:
        hs = abc_header.parse_string (run.header.text) if run.header else []
    except ParseException as err:
        reportParseException (run, err, None)
        return run.diagnostics
    parsed = []
    prevLeftBar = None      # previous voice ended with a left-bar symbol (double repeat)
    for id, voice in run.voices:
        try:
            vce = abc_voice.parse_string (voice.text).as_list ()
        except ParseException as err:
            reportParseException (run, err, SourcePosition (*srcContext (voice, err.loc)))
            return run.diagnostics
        lyr_notes = []          # remember notes between lyric blocks
        for m in vce:           # all measures
            for e in m:         # all abc-elements
                if e.name == 'lyr_blk':         # -> e.objs is list of lyric lines
                    lyr = [line.objs for line in e.objs]    # line.objs is listof syllables
                    alignLyr (lyr_notes, lyr, e)    # put all syllables into corresponding notes
                    lyr_notes = []
                else:
                    lyr_notes.append (e)
        if not vce:             # empty voice, insert an inline field that will be rejected
            vce = [[pObj ('inline', ['I', 'empty voice'])]]
        if prevLeftBar:
            vce[0].insert (0, prevLeftBar)  # insert at begin of first measure
            prevLeftBar = None
        if vce[-1] and vce[-1][-1].name == 'lbar':  # last measure ends with an lbar
            prevLeftBar = vce[-1][-1]
            if len (vce) > 1:   # vce should not become empty
                del vce[-1]     # lbar was the only element in measure vce[-1]
        elem1 = vce [0][0]      # the first element of the first measure
        if  elem1.name == 'inline' and elem1.t[0] == 'V':   # is a voice definition
            voicedef = elem1
            del vce [0][0]      # do not read voicedef twice
        else:
            voicedef = ''
        parsed.append (ParsedVoice (id, voicedef, vce, voice))
    Validator (run).validate (list (hs), parsed)
    return run.diagnostics


abc_header, abc_voice, abc_scoredef, abc_percmap = abc_grammar ()   # compute grammars only once
