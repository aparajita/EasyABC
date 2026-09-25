'''
How the I:score (or I:staves) directive of a tune distributes its voices over staves, grand staves and
parts, shared by the checker in abc_parser and the MusicXML converter in abc2xml.
'''
from pyparsing import ParseException
from abc_directives import StaffReference, syntaxErrorMessage
from abc_syntax import pObj, abc_scoredef

DROPPED_SCORE_MESSAGE = '%%%%%s dropped, multiple stave mappings not supported'
UNKNOWN_VOICE_MESSAGE = 'score partname %s does not exist'

def firstVoice (x):             # a merged voice group stands for its first voice
    return x.objs[0] if x.name == 'voicegr' else x

def asStaffList (x):            # a single voice id becomes a one-voice staff
    return [x] if isinstance (x, str) else x


class StaffLayout:
    '''The staves, grand staves and parts of a tune, and the staff each voice is on.

    - part_names = {vid: (name, subname)}: the first voice of a voice group or accepted grand staff
      carries the first non-empty name of its group, which names the merged part.
    - part_ids = {vid: part id}: the first voice of its grand staff, the voice itself when it has none.
    - staves = [[vid, ...] per staff]: a voice group merges into one staff.
    - grands = [[vid, ...] per grand staff]: the first voice of each of its staves.
    - groups: the part ids with the '[' ']' and '{' '}' brackets and braces around them, in score order.
    A voice outside a grand staff of several staves is on staff 0 of a grand staff of 0 staves.
    '''

    def __init__ (s, voice_names, score=None):  # score = the parsed I:score tree, None when the tune has none
        s.part_names = dict (voice_names)
        s.part_ids = {vid: vid for vid in voice_names}
        s.staves, s.grands, s.groups = [], [], []
        s._staff, s._count = {}, {}     # vid -> staff number within its grand staff, number of staves of it
        accepted = set ()               # the grand staff nodes of the score that became a part
        if score is not None:
            s.staves = [asStaffList (x) for x in s._collectStaves (score)]
            s.grands = [asStaffList (x) for x in s._collectGrands (score, accepted)]
            s.groups = s._collectGroups (score, accepted)
        merged = {vgr[0]: vgr for vgr in s.staves if len (vgr) > 1}     # first voice of a voice group -> all its voices
        for gstaff in s.grands:
            for vid in [v for stf in gstaff for v in merged.get (stf, [stf])]: s.part_ids [vid] = gstaff [0]
            if len (gstaff) == 1: continue
            for num, stf in enumerate (gstaff, 1):
                for vid in merged.get (stf, [stf]):
                    s._staff [vid] = num
                    s._count [vid] = len (gstaff)
        s._original = dict (s._staff)   # I:staff n counts the staves of the score, not the redirected ones

    @classmethod
    def from_directives (cls, directives, voices, warn, error):
        '''The layout of the ParsedVoice voices by the first of directives = [(I:score text, position)].

        directives are in encounter order. warn (message, position) reports each later directive, which
        is ignored. error (message, position) reports a first directive the grammar rejects; the layout
        then keeps each voice on its own part.
        '''
        voice_names = {voice.id: (voice.definition.name, voice.definition.subname) for voice in voices}
        for text, position in directives [1:]: warn (DROPPED_SCORE_MESSAGE % text, position)
        if not directives: return cls (voice_names)
        text, position = directives [0]
        try: score = abc_scoredef.parse_string (text) [0]
        except ParseException as err:
            error (syntaxErrorMessage (text, err), position)
            return cls (voice_names)
        return cls (voice_names, score)

    def staff_of (s, vid):      # the staff number of vid within its grand staff
        return s._staff.get (vid, 0)

    def staff_count (s, vid):   # the number of staves of the grand staff of vid
        return s._count.get (vid, 0)

    def redirect (s, vid, redirection):
        '''Move vid to the staff an I:staff redirection names; returns the problems, empty when it moved.'''
        problems = []
        current = s.staff_of (vid)
        if redirection.reference is StaffReference.RELATIVE:
            target = current + redirection.number
        elif 1 <= redirection.number <= len (s.staves):
            target = s._original.get (s.staves [redirection.number - 1][0], 0)
        else:
            target = 0
            problems.append ('abc staff %s does not exist' % redirection.number)
        if current and 0 < target <= s.staff_count (vid): s._staff [vid] = target
        else: problems.append ('could not relocate to staff: %s' % redirection.text)
        return problems

    def unknown_voices (s, vids):   # the voice ids the score names that are not in vids, in the order the parts merge
        unknown = []
        for staves in (s.staves, s.grands):
            if not staves: continue
            merged = []
            for voice_ids in staves:
                found = [vid for vid in voice_ids if vid in vids]
                unknown += [vid for vid in voice_ids if vid not in vids]
                if found: merged.append (found [0])
            vids = merged
        return unknown

    def _nameAfterGroup (s, vids):  # the first voice of a group takes the first non-empty name in the group
        vids = [vid for vid in vids if vid in s.part_names]
        named = [s.part_names [vid] for vid in vids if s.part_names [vid][0]]
        if named: s.part_names [vids [0]] = named [0]

    def _collectStaves (s, p):      # [vid | [vid, ...]] per staff
        xs = []
        for x in p.objs:
            if type (x) == pObj:
                us = s._collectStaves (x)
                if x.name == 'voicegr':
                    xs.append (us)
                    s._nameAfterGroup (us)
                else: xs.extend (us)
            elif p.t[0] not in '{*': xs.append (p.t[0])     # '{' and '{*' are grand staff markers, not voice ids
        return xs

    def _collectGrands (s, p, accepted):    # [[vid, ...] | vid] with an entry per accepted grand staff
        xs = []
        for x in p.objs:
            if type (x) == pObj:
                x = firstVoice (x)
                us = s._collectGrands (x, accepted)
                if x.name == 'grand':
                    vids = [firstVoice (y).objs[0] for y in x.objs[1:]]
                    named = sum (1 for vid in vids if vid in s.part_names and s.part_names [vid][0])
                    if named == 1 or us[0] == '{*':         # exactly one named voice, or forced with {*
                        xs.append (us[1:])                  # discard the '{' or '{*' marker
                        s._nameAfterGroup (vids)
                        accepted.add (id (x))
                    else: xs.extend (us[1:])                # rejected: its voices stay separate parts
                else: xs.extend (us)
            else: xs.append (p.t[0])
        return xs

    def _collectGroups (s, p, accepted):    # an accepted grand staff is one part, a rejected one a brace
        xs = []
        for x in p.objs:
            if type (x) == pObj:
                x = firstVoice (x)
                if id (x) in accepted: x = firstVoice (x.objs[1])
                if x.name == 'vid': xs.extend (s._collectGroups (x, accepted))
                elif x.name == 'bracketgr': xs.extend (['['] + s._collectGroups (x, accepted) + [']'])
                elif x.name == 'bracegr':   xs.extend (['{'] + s._collectGroups (x, accepted) + ['}'])
                else: xs.extend (s._collectGroups (x, accepted) + ['}'])   # rejected grand staff: its '{' leads
            else: xs.append (p.t[0])
        return xs
