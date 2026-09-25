#!/usr/bin/env python
# coding=latin-1
'''
The ABC front end shared by the checker in abc_parser and the MusicXML converter in abc2xml:
the tune text split into a header and voices, the grammar, and the parse tree it builds.

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
from typing import NamedTuple
from pyparsing import Word, OneOrMore, Optional, Literal, MatchFirst
from pyparsing import Group, one_of, Suppress, ZeroOrMore, Combine, FollowedBy
from pyparsing import srange, CharsNotIn, StringEnd, Regex
from pyparsing import nums, alphanums, ParseException, Forward
import copy, re
from abc_notation import VoiceDefinition

#-------------------------------------------------------------
# source text: every character paired with its source line
#-------------------------------------------------------------

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

def leadLine (src, fallback):   # the source line a synthetic prefix to src is attributed to
    return src.lines [0] if src.lines else fallback

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

LYRIC_FIELD_RE = re.compile (r'\[w:(.*?)\]')        # one folded [w:...] field inside an excerpt

def lyricContext (source, loc):     # srcContext narrowed to the text of the [w:...] field that loc falls in
    line, excerpt, column = srcContext (source, loc)
    for m in LYRIC_FIELD_RE.finditer (excerpt):
        if m.start (1) <= column <= m.end ():
            return line, m.group (1), max (0, min (column - m.start (1), len (m.group (1))))
    return line, excerpt, column

#-------------------------------------------------------------
# a tune split into its header and its voices
#-------------------------------------------------------------

class TuneText (NamedTuple):
    header: SrcText     # all header fields folded into one string of [X:...] fields
    voices: list        # [(voice id, SrcText)] in document order
    words: list         # the text of every W: field, in document order

slur_move = re.compile (r'(?<![!+])([}><][<>]?)(\)+)')  # (?<!...) means: not preceeded by ...
mm_rest = re.compile (r'([XZ])(\d+)')
bar_space = re.compile (r'([:|][ |\[\]]+[:|])')         # barlines with spaces
headerFieldRE = re.compile (r'\[[^]]*\]')   # one folded [X:...] field in the header string
keyFieldRE = re.compile (r'(\[K:[^]]*\])')
voiceFieldRE = re.compile (r'(\[V:[^]]*\])')
partMarkRE = re.compile (r'\[P:.\]')

def fixSlurs (x):   # repair slurs when after broken sign or grace-close
    def f (mo):     # replace a multi-measure rest by single measure rests
        n = int (mo.group (2))
        return (n * (mo.group (1) + '|')) [:-1]
    def g (mo):     # squash spaces in barline expressions
        return mo.group (1).replace (' ','')
    x = mm_rest.sub (f, x)
    x = bar_space.sub (g, x)
    return slur_move.sub (r'\2\1', x)

def escField (fld):     # fold a field into inline form, escaping every ']' (hope nobody uses %5d in a field)
    out = SrcText.fromLine ('[', fld.lines [0])
    for ch, line in zip (fld.text, fld.lines):
        out = out + SrcText.fromLine ('%5d' if ch == ']' else ch, line)
    return out + SrcText.fromLine (']', fld.lines [-1])

def splitHeaderVoices (abctext):
    r1 = re.compile (r'%.*$')           # comments
    r2 = re.compile (r'^([A-Zw]:.*$)|\[[A-Zw]:[^]]*]$')     # information field, including lyrics
    r3 = re.compile (r'^%%(?=[^%])')    # directive: ^%% folowed by not a %
    xs, nx, mcont, fcont = [], 0, 0, 0  # result rows, X-encountered, music continuation, field continuation
    words = []                          # W: field texts
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
        if x2[:2] == 'W:':              # W: lyrics are not music
            words.append (x2 [2:].strip ())
            continue
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
    if not xs: return TuneText (SrcText (), [], words)  # nothing but comments and blank lines

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
    return TuneText (header, [(id, concatSrc (vmap [id])) for i, id in ixs], words)

inlineFieldRE = re.compile (r'\[[wA-Z]:[^]]*\]')
newlineRE = re.compile ('\n')

def lineBreaksAtEol (source):   # every row that holds music ends with a $ line break
    out = SrcText ()
    for i, row in enumerate (source.splitOn (newlineRE)):
        isRow = i % 2 == 0      # splitOn alternates rows and the newlines between them
        if isRow and inlineFieldRE.sub ('', row.text).strip ():
            row = row.slice (0, len (row.text.rstrip ('$!'))) + SrcText.fromLine ('$', row.lines [-1])
        out = out + row
    return out

#-------------------------------------------------------------
# the parse tree
#-------------------------------------------------------------

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

def errorWarn (line, loc, t):   # misplaced symbols become error nodes, for the consumer to report
    if not t[0]: return []      # only an error if catched string not empty
    return stampedPobj ('error', line, loc, t)

def caughtSymbols (fld):    # the error nodes of the misplaced characters the U: grammar caught inside a field
    caught = getattr (fld, 'error', [])
    return caught if type (caught) == list else [caught]    # pObj makes a list only of two or more

#-------------------------------------------------------------
# transformations of a measure (called by the measure parse action)
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

def convertChord (t, ordered):  # convert chord to sequence of notes in musicXml-style, highest note first when ordered
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
            nss = sorted (x.objs, key = ptc2midi, reverse=1) if ordered else x.objs
            for nt in nss:      # all chord elements (note | decorations | rest | grace note | error)
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

def measureAction (orderedChords):  # parse action for a measure; orderedChords as for convertChord
    def action (t):             # t is a Group() result -> the measure is in t[0]
        convertBroken (t[0])    # remove all broken rhythms and convert to normal durations; 'error' nodes are neither note nor broken, so they stay
        convertChord (t[0], orderedChords)  # replace chords by note sequences in musicXML style
    return action

def graceAction (orderedChords):    # parse action for a grace sequence; orderedChords as for convertChord
    def action (t):             # t is a Group() result -> the grace sequence is in t[0]
        convertChord (t[0], orderedChords)  # a grace sequence may have chords
        for nt in t[0]:         # flag all notes within the grace sequence; other names ('error' included) are left as they are
            if nt.name == 'note': nt.grace = 1  # set grace attribute
        return t[0]             # ungroup the parse result
    return action

#-------------------------------------------------------------
# the grammar
#-------------------------------------------------------------

def abc_grammar (orderedChords):    # header, voice and lyrics grammar for ABC; orderedChords as for convertChord
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
    grace_notes.set_parse_action (graceAction (orderedChords))
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
    broken.set_parse_action (posPobj ('broken'))  # positioned: an orphan broken symbol stays in the tree for the consumer to report
    tuplet_start.set_parse_action (lambda t: pObj ('tup', t))
    linebreak.set_parse_action (lambda t: pObj ('linebrk', t))
    measure.set_parse_action (measureAction (orderedChords))
    noBarMeasure.set_parse_action (measureAction (orderedChords))
    b1.set_parse_action (errorWarn)
    b2.set_parse_action (errorWarn)
    b3.set_parse_action (errorWarn)
    errors.set_parse_action (errorWarn)

    return abc_header, abc_voice, abc_scoredef, abc_percmap

#-------------------------------------------------------------
# lyrics
#-------------------------------------------------------------

gracewordRE = re.compile (r'graceword\b\s*(\S*)')
def gracewordSetting (directive, current):  # the setting after an I: directive (the text after I:)
    m = gracewordRE.match (directive)
    if not m: return current
    return m.group (1)[:1] in ('', '1', 't', 'T', 'y', 'Y')  # the logical values abcm2ps accepts as true

def headerGraceword (header):   # the %%graceword setting of a header of [I:...] fields, off when absent
    graceword = False
    for directive in re.findall (r'\[I:([^\]]*)\]', header): graceword = gracewordSetting (directive, graceword)
    return graceword

graceSplitRE = re.compile (r'((?:[^\\/=]|\\.|=(?!/))*)(=?)/(.*)$')  # grace part, its dash marker (=), principal part
def splitGraceSyllable (syl):   # 'O=/All-' -> (O with dash, All with dash), None when the text has no unescaped slash
    m = graceSplitRE.match (syl.t[0])
    if not m: return None
    def part (text, dash):      # an empty part puts no syllable on its note
        if not text: return None
        p = copy.copy (syl)     # keeps the source position for error reports
        p.t = [text, '-'] if dash else [text]
        return p
    grace, mark, principal = m.groups ()
    return part (grace, mark), part (principal, len (syl.t) == 2)

def nextLyricBar (lyr, i):  # index of the first '|' in lyr at or after i, or None
    for j in range (i, len (lyr)):
        if lyr[j].name == 'sbar': return j
    return None

class LyricAligner:     # distributes the syllables of the lyric blocks of one voice over its notes
    # Every note in a syllable slot gets exactly one object per verse, so the index of a lyric object in a
    # note's objs is its verse. A '|' in a verse resynchronises the verse to the next bar line of the music.
    empty_el = pObj ('leeg', '*')

    def __init__ (s, graceword):
        s.graceword = graceword # with %%graceword a grace group shares the syllable of the note it precedes

    def alignVoice (s, measures):   # pairs every lyric block with the notes since the previous block
        notes = []
        for m in measures:
            for e in m:
                if e.name == 'lyr_blk':
                    s.align (notes, e)
                    notes = []
                else:
                    notes.append (e)

    def align (s, vce, blk):
        # a principal note without a syllable gets a filler and is recorded in blk.bareNotes, a syllable
        # without a note is recorded in blk.surplus, both as (verse index, node)
        blk.bareNotes, blk.surplus = [], []
        graceword = s.graceword
        for k, lyr in enumerate ([line.objs for line in blk.objs]):     # lyr = one verse
            graceword = s.graceword # each verse is aligned from the setting at the start of the block
            i = 0               # syl counter
            group = []          # grace notes preceding the next principal note
            for elem in vce:    # only notes and rbars consume syllables, an 'error' element consumes none
                if elem.name == 'inline' and elem.t[0] == 'I':
                    graceword = gracewordSetting (' '.join (elem.t[1:]), graceword)
                elif elem.name == 'note' and hasattr (elem, 'grace'):
                    if graceword and not hasattr (elem, 'chord'): group.append (elem)
                elif elem.name == 'note' and not hasattr (elem, 'chord'):
                    if i < len (lyr) and lyr[i].name != 'sbar':
                        lr = lyr [i]
                        lr.t[0] = lr.t[0].replace ('%5d',']')
                        i += 1
                    else:
                        lr = s.empty_el
                        blk.bareNotes.append ((k, elem))
                    if group: s.alignGraceSlot (group, elem, lr)
                    else: elem.objs.append (lr)
                    group = []
                elif elem.name in ('rest', 'rbar', 'lbar'): group = []  # a grace group only takes a syllable before a note
                if elem.name == 'rbar':
                    j = nextLyricBar (lyr, i)
                    if j is not None:
                        blk.surplus.extend ((k, x) for x in lyr [i:j])
                        i = j + 1
            blk.surplus.extend ((k, x) for x in lyr [i:] if x.name != 'sbar')
        s.graceword = graceword

    def alignGraceSlot (s, group, principal, lr):   # the syllable goes on the first grace note, a melisma covers the rest
        melisma = pObj ('ext', ['_'])
        split = splitGraceSyllable (lr) if lr.name == 'syl' else None
        if split:
            grace, main = split
            first = grace or s.empty_el
            tail = melisma if grace else s.empty_el
        elif lr.name == 'syl':
            first, tail, main = lr, melisma, melisma
        else:                   # a filler, an extend or a skip covers the whole slot
            first = tail = main = lr
        group [0].objs.append (first)
        for nt in group [1:]: nt.objs.append (tail)
        principal.objs.append (main or s.empty_el)

#-------------------------------------------------------------
# parsing a tune
#-------------------------------------------------------------

abc_header, abc_voice, abc_scoredef, abc_percmap = abc_grammar (False)  # compute grammars only once
abc_voice_ordered = abc_grammar (True) [1]  # the voice grammar that orders chord notes from high to low

def isScoreDirective (text):    # an I:score or I:staves directive (the text after I:), which maps the voices to staves
    return text.startswith (('score', 'staves'))

@dataclass (frozen=True)
class ParsedVoice:
    id: str
    voicedef: object        # the leading V: inline pObj of the voice, None when the voice has none
    definition: VoiceDefinition     # what voicedef says; the empty definition when there is none
    measures: list          # list of measures, each a list of pObj elements
    source: SrcText         # the rewritten voice text the grammar parsed (node.loc indexes into it)

    @property
    def id_problem (s):     # the message for a V: field whose id differs from the id the voice was split by, else None
        if s.voicedef is None or s.voicedef.t[1] == s.id: return None
        return 'voice ids unequal: %s (reg-ex) != %s (grammar)' % (s.id, s.voicedef.t[1])

    def score_directives (s):   # the inline I:score and I:staves nodes of the voice, with the directive text of each
        return [(x.t[1].replace ('%5d', ']'), x) for measure in s.measures for x in measure
                if x.name == 'inline' and isScoreDirective (x.t[1])]

@dataclass (frozen=True)
class ParsedTune:
    header: SrcText         # the header fields folded into one string of [X:...] fields
    fields: list            # the 'field' pObj of every header field, in order
    voices: list            # [ParsedVoice] in document order
    words: list             # the text of every W: field, in document order

class AbcSyntaxError (Exception):   # the grammar rejected the header or a voice
    def __init__ (s, message, source, loc, voice):
        super ().__init__ (message)
        s.message = message
        s.source, s.loc = source, loc   # the SrcText the grammar rejected, and the offset into it
        s.voice = voice                 # the id of the rejected voice, None for the header

    def context (s):    # (line, excerpt, column) of the offending character
        return srcContext (s.source, s.loc)

def syntaxErrorMessage (err):
    xs = err.line[err.col-1:]
    if   re.search (r'\[U:', xs):
        return 'illegal user defined symbol: %s' % xs[1:]
    elif re.search (r'\[[OAPZNGHRBDFSXTCIU]:', xs):
        return 'header-only field %s appears after K:' % xs[1:]
    return 'Syntax error at column %d' % err.col

def parseSource (grammar, source, voice):
    try:
        return grammar.parse_string (source.text).as_list ()
    except ParseException as err:
        raise AbcSyntaxError (syntaxErrorMessage (err), source, err.loc, voice) from err

explicitLineBreaksRE = re.compile (r'I:linebreak\s*([!$]|none)|I:continueall\s*(1|true)')
TAB_CLEF_PROBE = 200    # a voice is a tab voice when its first this many characters name the tab clef

def isTabVoice (fields, source):
    return 'tab' in source.text [:TAB_CLEF_PROBE] or any (f.t[0] == 'K' and 'tab' in f.t[1] for f in fields)

def parse_tune (abc_text, eol_linebreaks=False, order_tab_chords=False):
    '''Split one ABC tune into its header and voices and parse them.

    - abc_text is one tune, optionally preceded by file-header lines (%% directives and fields).
    - eol_linebreaks ends every row of music with a $ line break, unless the header sets
      I:linebreak to !, $ or none, or sets I:continueall.
    - order_tab_chords orders the notes of every chord from high to low in a voice with a tab clef
      (named in its first TAB_CLEF_PROBE characters or in a header K:); otherwise chord notes stay
      in the order they are written.
    - Every note, rest, decoration, inline field, broken rhythm symbol, lyric element and error node
      carries loc, an offset into the source of its ParsedVoice; srcContext turns it into a position.
      A misplaced symbol is an 'error' node and a broken rhythm symbol without a note on both sides
      stays as a 'broken' node, for the consumer to report.
    - The lyric blocks of every voice are aligned with its notes (see LyricAligner).
    - Raises AbcSyntaxError when the grammar rejects the header or a voice; nothing after it is parsed.
    - The grammars are built once at module level; parse_tune writes no module-level state, so it is
      safe to call from any thread.
    '''
    tune = splitHeaderVoices (abc_text)
    fields = list (parseSource (abc_header, tune.header, None)) if tune.header else []
    lineBreaks = eol_linebreaks and not explicitLineBreaksRE.search (tune.header.text)
    graceword = headerGraceword (tune.header.text)
    voices = []
    for id, source in tune.voices:
        if lineBreaks: source = lineBreaksAtEol (source)
        ordered = order_tab_chords and isTabVoice (fields, source)
        measures = parseSource (abc_voice_ordered if ordered else abc_voice, source, id)
        LyricAligner (graceword).alignVoice (measures)
        if not measures:        # empty voice, insert an inline field that will be rejected
            measures = [[pObj ('inline', ['I', 'empty voice'])]]
        if len (measures) > 1 and measures [-1] and measures [-1][-1].name == 'lbar':
            del measures [-1]   # a measure holding only the left bar that ends the voice starts nothing
        first = measures [0][0] # the first element of the first measure
        if first.name == 'inline' and first.t[0] == 'V':    # is a voice definition
            voicedef = first
            del measures [0][0] # do not read voicedef twice
        else:
            voicedef = None
        definition = VoiceDefinition.parse (voicedef.t[2] if voicedef else '')
        voices.append (ParsedVoice (id, voicedef, definition, measures, source))
    return ParsedTune (tune.header, fields, voices, tune.words)
