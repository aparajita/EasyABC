"""Runs abc2xml in process for the tests of its MusicXML output."""
import abc2xml


def parse_score(abc):
    """Converts one tune and returns the MusicXML score element."""
    return abc2xml.mxm.parse(abc)
