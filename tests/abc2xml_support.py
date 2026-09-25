"""Runs abc2xml in process for the tests of its MusicXML output."""
import warnings

with warnings.catch_warnings():
    warnings.simplefilter('ignore')     # pyparsing deprecation warnings from abc2xml's grammar
    import abc2xml


def parse_score(abc):
    """Converts one tune and returns the MusicXML score element."""
    if not hasattr(abc2xml, 'abc_header'):
        abc2xml.abc_header, abc2xml.abc_voice, abc2xml.abc_scoredef, abc2xml.abc_percmap = abc2xml.abc_grammar()
        abc2xml.mxm = abc2xml.MusicXml()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return abc2xml.mxm.parse(abc)
