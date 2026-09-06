# Copyright (C) 2011-2014 Nils Liberg (mail: kotorinl at yahoo.co.uk)
# Copyright (C) 2015-2024 Seymour Shlien (mail: fy733@ncf.ca), Jan Wybren de Jong (jw_de_jong at yahoo dot com)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

import re
import traceback
from datetime import datetime

import wx

from abc_transform import get_notes_from_abc, process_abc_code
from abc_tune import AbcTune
from background_threads import MusicUpdateThread
from tune_model import text_to_lines, AbcTunes


# The zoom slider works in per-mille of the physical score size.
ZOOM_PER_MILLE = 1000.0
MIN_ZOOM = 500
MAX_ZOOM = 3000
DEFAULT_ZOOM = 1000
WHEEL_ZOOM_STEP = 50
MENU_ZOOM_STEP = 100

# abcm2ps sizes its SVG output in CSS pixels, which are 96 to the inch.
SVG_PIXELS_PER_INCH = 96.0


def parse_desc(desc):
    parts = desc.split()
    row, col = list(map(int, parts[1].split(':')))
    return (row, col)


class ScoreView(object):
    """The rendered score: which tune and page it shows, the notes selected on it, and keeping it in step with the editor."""

    def __init__(self, frame):
        self.frame = frame
        self.svg_tunes = AbcTunes()
        self.current_svg_tune = None # 1.3.6.2 [JWdJ] 2015-02
        self.selected_note_descs = []
        self.selected_note_indices = []
        self.zoom_factor = 1.0
        self.zoom_at_gesture_start = DEFAULT_ZOOM
        self.last_line_number_selected = -1
        self.queue_number_movement = 0
        self.queue_number_refresh_music = 0
        self.music_update_thread = None
        self.score_is_maximized = False

    def start_music_update_thread(self):
        frame = self.frame
        self.music_update_thread = MusicUpdateThread(frame, frame.settings, frame.cache_dir)
        self.music_update_thread.start()

    def get_num_extra_header_lines(self, tune):
        # how many lines are there before the X: line in the processed ABC code?

        # 1.3.6 [SS] 2014-12-17
        settings = self.frame.settings
        lines = text_to_lines(process_abc_code(settings, tune.abc,
                                               tune.header,
                                               minimal_processing=not settings.get('reduced_margins', True)))
        num_header_lines = 0
        first_note_line_index = 0
        for i, line in enumerate(lines):
            if line.startswith('X:'):
                num_header_lines = i
                break
        for i, line in enumerate(lines):
            line = line.strip()
            if line and not re.match(r'[A-Za-z]:', line) and not line.startswith('%'):
                first_note_line_index = i
                break

        num_header_lines += 0  # due to some oddity in newer versions of abcm2ps
        return (num_header_lines, first_note_line_index)

    def OnNoteSelectionChangedDesc(self, selected_note_indices, close_note_index=None):
        frame = self.frame
        frame.Raise()

        self.selected_note_indices = selected_note_indices
        self.selected_note_descs = [frame.music_pane.current_page.notes[i] for i in selected_note_indices]

        editor = frame.editor
        editor.SetFocus()
        tune = frame.tune_list_controller.GetSelectedTune()
        if not tune:
            return
        num_header_lines, first_note_line_index = self.get_num_extra_header_lines(tune)
        if 1==0: #frame.is_really_playing and frame.played_notes_timeline and selected_note_indices and close_note_index is None:
            page_index = frame.music_pane.current_page.index
            note_index = min(selected_note_indices)
            pos_in_ms = next((n.start for n in frame.played_notes_timeline if n.page == page_index and note_index in n.indices), -1)
            if pos_in_ms != -1:
                frame.mc.Seek(pos_in_ms)

        position, end_position = tune.offset_start, tune.offset_end
        tune_start_line = editor.LineFromPosition(position)
        if close_note_index is None:
            row_cols = sorted([(desc[2], desc[3]) for desc in self.selected_note_descs])
        else:
            # 1.3.6.2 [JWdJ] 2015-02
            row_cols = [tuple(frame.music_pane.current_page.notes[close_note_index][2:3+1])]

        #Following workaround is not needed apparently
        # workaround for the fact the abcm2ps returns incorrect row numbers
        # check the row number of the first note and if it doesn't agree with the actual value
        # then pretend that we have more or less extra header lines
        #if frame.music_pane.current_page.notes:
        #    actual_first_row = frame.music_pane.current_page.notes[0][2]-1
        #    num_header_lines += (actual_first_row - first_note_line_index)

        if end_position > position:
            if row_cols:
                row1, col1 = row_cols[0]
                row2, col2 = row_cols[-1]
                row1 += tune_start_line - num_header_lines - 1
                row2 += tune_start_line - num_header_lines - 1
                p1 = editor.PositionFromLine(row1) + col1
                p2 = editor.PositionFromLine(row2) + col2

                # p2 is the start of the last note, now find the end of it
                ##text = editor.GetTextRange(p2, p2+10)
                text = ''.join([editor.GetTextRange(i, i+1) for i in range(p2, p2+10)]) # this way of retrieving the next 10 chars seem more reliable in case one starts on some utf-8 char boundary or something

                notes = get_notes_from_abc(text)
                if notes:
                    p2 += notes[0][1]  # end-offset of first note found
                else:
                    p2 += 1

                # if the selection starts at a [ character and ends before the ] character, then extend it to the latter
                first_char = editor.GetTextRange(p1, p1+1)
                if first_char == '[' and ']' in text and text.index(']') >= p2-p1:
                    p2 = p1 + text.index(']') + 1

                # clip the positions to the start and end of the tune (for safety)
                p1, p2 = [min(max(p, position), end_position) for p in (p1, p2)]

                # scroll whole selection into view (if possible)
                editor.GotoPos(p1)
                editor.GotoPos(p2)
                editor.SetSelection(p1, p2)
            else:
                editor.SetSelectionEnd(editor.GetSelectionStart())

            # if this was not actually a direct click on a note, but rather in between, then place the cursor just before the closest note
            if close_note_index is not None:
                editor.SetSelectionEnd(editor.GetSelectionStart())

    def transpose_selected_note(self, amount):
        # TODO: finish this code
        editor = self.frame.editor
        notes = 'C D E F G A B c d e f g a b'.split()
        note = editor.GetSelectedText()
        i = notes.index(note[0])
        note = notes[i+amount] + note[1:]
        editor.ReplaceSelection(note)

    def OnToggleMusicPaneMaximize(self, evt):
        frame = self.frame
        pane = frame.manager.GetPane('tune preview')
        if pane.IsMaximized():
            pane.Restore()
        else:
            pane.Maximize()
        frame.manager.Update()
        frame.Refresh()

    def set_zoom(self, zoom):
        """Set the score zoom, in per-mille, clamped to the range the zoom slider offers."""
        zoom = max(MIN_ZOOM, min(MAX_ZOOM, int(round(zoom))))
        self.frame.zoom_slider.SetValue(zoom)
        self.apply_zoom()

    def screen_scale(self):
        """The scale at which one SVG pixel covers one 96th of a physical inch on screen."""
        ppi = wx.Display(self.frame.music_pane).GetRawPPI().width
        if ppi <= 0:
            return 1.0
        return ppi / SVG_PIXELS_PER_INCH

    def apply_zoom(self):
        frame = self.frame
        old_factor = self.zoom_factor
        self.zoom_factor = frame.zoom_slider.GetValue() / ZOOM_PER_MILLE * self.screen_scale()
        if self.zoom_factor != old_factor:
            frame.renderer.zoom = self.zoom_factor # 1.3.6.2 [JWdJ] 2015-02
            frame.music_pane.redraw()

    def zoom_by(self, step):
        """Change the score zoom by the given number of per-mille."""
        self.set_zoom(self.frame.zoom_slider.GetValue() + step)

    def OnZoomSlider(self, evt):
        self.apply_zoom()

    def OnZoomIn(self, evt):
        self.zoom_by(MENU_ZOOM_STEP)

    def OnZoomOut(self, evt):
        self.zoom_by(-MENU_ZOOM_STEP)

    def OnActualZoom(self, evt):
        self.set_zoom(DEFAULT_ZOOM)

    def OnZoomSliderClick(self, evt):
        if evt.ControlDown() or evt.ShiftDown():
            self.set_zoom(DEFAULT_ZOOM)
        else:
            evt.Skip()

    def OnMusicPaneMouseWheel(self, evt):
        if evt.ControlDown() or evt.CmdDown():
            if evt.GetWheelRotation() > 0:
                self.zoom_by(WHEEL_ZOOM_STEP)
            else:
                self.zoom_by(-WHEEL_ZOOM_STEP)
        else:
            evt.Skip()

    def OnMusicPaneZoomGesture(self, evt):
        # GetZoomFactor() is relative to the start of the gesture, not to the previous event.
        if evt.IsGestureStart():
            self.zoom_at_gesture_start = self.frame.zoom_slider.GetValue()
        self.set_zoom(self.zoom_at_gesture_start * evt.GetZoomFactor())

    def scroll_to_notes(self, page, indices):
        if not indices:
            return
        x, y, _, _, _ = page.notes[max(indices)]
        self.scroll_music_pane(x, y)

    def OnMusicPaneClick(self, evt):
        if self.score_is_maximized:
            frame = self.frame
            width, height = frame.music_pane.Size
            x, y = evt.Position
            x_threshold = width / 3
            y_threshold = height / 3
            new_page = -1
            tune_list = frame.tune_list
            total_tunes = tune_list.GetItemCount()

            if x < x_threshold:
                # previous page
                new_page = frame.current_page_index - 1
                if new_page < 0:
                    new_page += self.current_svg_tune.page_count
            elif x > (width - x_threshold):
                # next page
                new_page = frame.current_page_index + 1
                if new_page >= self.current_svg_tune.page_count:
                    new_page = 0
            elif y < y_threshold:
                # previous tune
                new_tune = tune_list.GetFirstSelected()
                if new_tune < 0:
                    new_tune = 0
                else:
                    new_tune -= 1
                    if new_tune < 0:
                        new_tune = total_tunes - 1
                tune_list.DeselectAll()
                tune_list.Select(new_tune)
            elif y > (height - y_threshold):
                # next tune
                new_tune = tune_list.GetFirstSelected()
                if new_tune < 0:
                    new_tune = 0
                else:
                    new_tune += 1
                    if new_tune >= total_tunes:
                        new_tune = 0
                tune_list.DeselectAll()
                tune_list.Select(new_tune)

            if 0 <= new_page < self.current_svg_tune.page_count and new_page != frame.current_page_index:
                self.select_page(new_page)
                return

        evt.Skip()

    def OnRightClickMusicPane(self, evt):
        if self.score_is_maximized:
            self.frame.toggle_fullscreen(evt)

    def OnMusicPaneDoubleClick(self, evt):
        self.frame.editor.SetFocus()

    def OnMusicPaneKeyDown(self, evt):
        c = evt.GetKeyCode()
        if c == wx.WXK_LEFT:
            self.frame.music_pane.move_selection(-1)
        elif c == wx.WXK_RIGHT:
            self.frame.music_pane.move_selection(1)
        elif c == wx.WXK_UP and evt.CmdDown():
            self.transpose_selected_note(1)
        elif c == wx.WXK_DOWN and evt.CmdDown():
            self.transpose_selected_note(-1)
        else:
            evt.Skip()

    def OnToolRefresh(self, evt):
        self.refresh_tunes()

    def refresh_tunes(self):
        frame = self.frame
        frame.last_refresh_time = datetime.now()
        frame.tune_list_controller.UpdateTuneListAndReselectTune()
        frame.tune_list_controller.OnTuneSelected(None)

    def closestNoteData(self, page, row_offset, line, col):
        """Find the NoteData of the closest note to cursor position

        Parameters
        ----------
        page : SvgPage
            One page of score of SvgPage
        row_offset : int
            An offset to align line to a line of note
        line : int
            Line where the cursor or selection is in the editor
        col : int
            Col where the cursor or selection is in the editor

        Returns
        -------
        closest_note_data : namedTuple NoteData
            closest NoteData found in the page
        """

        closest_note_data = None
        line -= row_offset
        # Next variables initialised with a value that should be big enough to find closest
        closest_col = -9999
        note_delta = 9999
        bar_start = bar_start_tmp = 0
        bar_end = 9999

        if page.notes_in_row is not None and line in page.notes_in_row:
            for note_data in page.notes_in_row[line]:
                # note_type B is a Bar and first listed
                # need to manage cursor after last bar of the line
                if note_data.note_type == "B" and bar_start == 0:
                    if note_data.col > col:
                        bar_end = min(bar_end,note_data.col)
                        bar_start = bar_start_tmp
                    if note_data.col < col:
                        bar_start_tmp = max(bar_start_tmp,note_data.col)
                # note_type N is a Note, note_type R is a Rest
                if (note_data.note_type == "N" or note_data.note_type == "R") and bar_start<=note_data.col<=bar_end and (closest_note_data is None or col>=note_data.col) and (abs(col - note_data.col)<note_delta):
                    note_delta=abs(col - note_data.col)
                    closest_note_data = note_data

        return closest_note_data

    def FindNotesIndicesBetween2Notes(self, page, note_data_1, note_data_2):
        """Find the indices of the notes between 2 notes

        Need to consider the various cases of selection.
        For now only single selection mode is supported with contiguous selection.
        Todo: manage multiple selections

        Parameters
        ----------
        page : SvgPage
            One page of score of SvgPage
        note_data_1 : namedtuple note_data
            Note data of the 1st note
        note_data_2 : namedtuple note_data
            Note data of the 2nd note

        Returns
        -------
        set_of_indices : set
            set containing all the indices of notes between two other notes (included)
        """

        set_of_indices = set()

        for row in page.notes_in_row:
            if row == note_data_1.row and row == note_data_2.row:
                for note_data in page.notes_in_row[row]:
                    if (note_data.note_type == "N" or note_data.note_type == "R") and note_data.col>=note_data_1.col and note_data.col<=note_data_2.col:
                        set_of_indices = set_of_indices.union(page.get_indices_for_row_col(note_data.row,note_data.col))
                break
            if row == note_data_1.row and row < note_data_2.row:
                for note_data in page.notes_in_row[row]:
                    if (note_data.note_type == "N" or note_data.note_type == "R") and note_data.col>=note_data_1.col:
                        set_of_indices = set_of_indices.union(page.get_indices_for_row_col(note_data.row,note_data.col))
            elif row > note_data_1.row and row < note_data_2.row:
                for note_data in page.notes_in_row[row]:
                    if (note_data.note_type == "N" or note_data.note_type == "R"):
                        set_of_indices = set_of_indices.union(page.get_indices_for_row_col(note_data.row,note_data.col))
            elif row > note_data_1.row and row == note_data_2.row:
                for note_data in page.notes_in_row[row]:
                    if (note_data.note_type == "N" or note_data.note_type == "R") and note_data.col<=note_data_2.col:
                        set_of_indices = set_of_indices.union(page.get_indices_for_row_col(note_data.row,note_data.col))

        return set_of_indices

    def ScrollMusicPaneToMatchEditor(self, select_closest_note=False, select_closest_page=False):
        """Scroll the score in the Music Pane to match the editor pointer and highlight notes

        Parameters
        ----------
        select_closest_note : bool, optional
            A flag to identify whether note closest to pointer in editor or
            text selection is to be highlighted (default is False)
        select_closest_page : bool, optional
            A flag used to align score view in Music Pane to editor selection
            (default is False)

        Returns
        -------
        Nothing to return
        """

        frame = self.frame
        editor = frame.editor
        music_pane = frame.music_pane
        tune = frame.tune_list_controller.GetSelectedTune()
        if not tune or not self.current_svg_tune or (not select_closest_note and not select_closest_page):
            #FAU: No need to continue to process
            return

        # workaround for the fact the abcm2ps returns incorrect row numbers
        # check the row number of the first note and if it doesn't agree with the actual value
        # then pretend that we have more or less extra header lines
        num_header_lines, first_note_line_index = self.get_num_extra_header_lines(tune)

        caret_current_pos = editor.GetCurrentPos()
        caret_current_row = editor.LineFromPosition(caret_current_pos)
        tune_first_line_no = editor.LineFromPosition(tune.offset_start)

        #FAU: Get the text selection and then corresponding line
        #     To enable to highlight notes based on selection need also to make sure
        #     on which svgPage the selection starts and ends
        p1, p2 = editor.GetSelection()
        line_p2 = editor.LineFromPosition(p2)
        line_p1 = editor.LineFromPosition(p1)
        p1_page_index = p2_page_index = frame.current_page_index

        #FAU: This part is to find the associated svgPage.
        #     It used to exit as soon as page of the cursor is found but need to browse completely
        #     as selection can be on multiple svgPages
        #if select_closest_page or select_closest_note:
        abc_from_editor = AbcTune(editor.GetTextRange(tune.offset_start, tune.offset_end))
        first_note_editor = abc_from_editor.first_note_line_index

        #if first_note_editor is not None:
        if first_note_editor is None:
            #No need to continue as no Note
            return

        caret_body_row = caret_current_row - tune_first_line_no - first_note_editor
        p1_body_row = max(line_p1 - tune_first_line_no - first_note_editor, 0)
        p2_body_row = max(line_p2 - tune_first_line_no - first_note_editor,0)
        if caret_body_row >= 0:
            # create a list of pages but start with the current page because it has the most chance
            #page_indices = [frame.current_page_index] + \
            #               [p for p in range(self.current_svg_tune.page_count) if p != frame.current_page_index]
            #FAU: To manage selection no need to prioritize
            page_indices = [p for p in range(self.current_svg_tune.page_count)]
            caret_svg_row = caret_body_row + self.current_svg_tune.first_note_line_index + 1 # row in svg-file is 1-based
            p1_row = p1_body_row + self.current_svg_tune.first_note_line_index + 1
            p2_row = p2_body_row + self.current_svg_tune.first_note_line_index + 1
            new_page_index = None
            for page_index in page_indices:
                # render_page parses the page, which is what fills notes_in_row.
                page = self.current_svg_tune.render_page(page_index, frame.renderer)
                if page and page.notes_in_row and caret_svg_row in page.notes_in_row:
                    new_page_index = page_index
                    #FAU: Do not break anymore to find other pages for selection
                    #break
                    #if p1_row == caret_svg_row and p2_row == caret_svg_row:
                    #    p1_page_index = p2_page_index = page_index
                    #    p1_page = p2_page = page
                    #    break
                if page and page.notes_in_row and p1_row in page.notes_in_row:
                    p1_page_index = page_index
                    p1_page = page
                if page and page.notes_in_row and p2_row in page.notes_in_row:
                    p2_page_index = page_index
                    p2_page = page
                #if new_page_index is not None and p1_page_index is not None and p2_page_index is not None:
                #    break

            if select_closest_page and new_page_index is not None and new_page_index != frame.current_page_index:
                self.select_page(new_page_index)
        else:
            select_closest_note=False

        musicpane_current_page = music_pane.current_page # 1.3.6.2 [JWdJ]
        if len(musicpane_current_page.notes) == 0:
            # there is nothing on this page to select
            select_closest_note=False

        #FAU: This is to track for the current page shown in the musicpane.
        current_page_index = frame.current_page_index

        #FAU: To search for the closest note, value initialised corresponding to a long distance
        closest_xy = None
        #closest_col = -9999
        #note_delta = 9999
        #closest_note_indice = None
        closest_note_indice_p2 = None
        closest_note_data_p1 = None
        closest_note_data_p2 = None

        selection_multi_notes = False
        current_position_is_p1 = False
        if p1!=p2 and select_closest_note:
            #FAU:  As in a selection do not highlight the note just after the cursor. Thus remove 1.
            p2 -= 1
            selection_multi_notes = True
            #FAU: current_position_is_p1 is defined to identify which page to show depending on selection
            #     from left to right (False) or right to left (True).
            if p1 == caret_current_pos:
                current_position_is_p1 = True

        # 1.3.6.2 [JWdJ] 2015-02
        row_offset = tune_first_line_no - 1 - num_header_lines

        if select_closest_note:
            #FAU: This is to manage the case with selection not completely in the current page or even not at all comprised
            if p2_page_index != current_page_index or p1_page_index != current_page_index:
                if (p2_page_index > current_page_index and p1_page_index > current_page_index) or (p2_page_index < current_page_index and p1_page_index < current_page_index):
                    #FAU: no need to continue to process so can return
                    musicpane_current_page.clear_note_selection()
                    if select_closest_note:
                        wx.CallAfter(music_pane.redraw)
                    return
                else:
                    if p2_page_index > current_page_index:
                        closest_note_data_p2 = self.closestNoteData(p2_page,row_offset,line_p2,p2 - editor.PositionFromLine(line_p2))
                        closest_note_indice_p2 = p2_page.get_indices_for_row_col(closest_note_data_p2.row,closest_note_data_p2.col)
                    if p1_page_index < current_page_index:
                        closest_note_data_p1 = self.closestNoteData(p1_page,row_offset,line_p1,col = p1 - editor.PositionFromLine(line_p1))

            #FAU: search note data corresponding to selection
            if closest_note_data_p2 is None:
                col = p2 - editor.PositionFromLine(line_p2)
                closest_note_data_p2 = self.closestNoteData(musicpane_current_page,row_offset,line_p2,col)
            if selection_multi_notes and closest_note_data_p2 is not None:
                if closest_note_data_p1 is None:
                    col = p1 - editor.PositionFromLine(line_p1)
                    closest_note_data_p1 = self.closestNoteData(musicpane_current_page,row_offset,line_p1,col)
                if closest_note_data_p1 is None:
                    #No note found close to p1 so ignore multi note selection
                    selection_multi_notes = False
                else:
                    selected_indices = self.FindNotesIndicesBetween2Notes(musicpane_current_page, closest_note_data_p1, closest_note_data_p2)
            else:
                selection_multi_notes = False

        ## 1.3.6.2 [JWdJ] 2015-02
        #for i, (x, y, abc_row, abc_col, desc) in enumerate(page.notes):
        #    abc_row += row_offset
        #    #FAU 20250126: search for the closest while not switching to next one to early
        #    #              with if abc_row == line and and (abs(col - abc_col) < abs(closest_col - abc_col))
        #    #              as soon as cursor shifted after the letter of note next note was selected even if only duration of previous note
        #    #              %%TODO%%: improve to consider highlight only if cursor is in a note?
        #    if abc_row == line and col>=abc_col and (abs(col - abc_col)<note_delta): # and (abs(col - abc_col) < abs(closest_col - abc_col))
        #        note_delta=abs(col - abc_col)
        #        closest_col = abc_col
        #        closest_xy = (x, y)
        #        if select_closest_note:
        #            closest_note_indice = i
        #            #if page.selected_indices != {i}:
        #            #    # 1.3.6.2 [JWdJ] 2015-02
        #            #    page.clear_note_selection()
        #            #    page.add_note_to_selection(i)
        #            #    self.selected_note_indices = [i]
        #            #    self.selected_note_descs = [page.notes[i] for i in self.selected_note_indices]

        if closest_note_data_p2 is not None:
            if closest_note_indice_p2 is None:
                closest_note_indice_p2 = musicpane_current_page.get_indices_for_row_col(closest_note_data_p2.row,closest_note_data_p2.col)
            closest_xy = (closest_note_data_p2.x,closest_note_data_p2.y)
            musicpane_current_page.clear_note_selection()
            if selection_multi_notes:
                self.selected_note_indices = []
                for i in selected_indices:
                    musicpane_current_page.add_note_to_selection(i)
                    self.selected_note_indices.append(i)
            elif select_closest_note:
                for i in closest_note_indice_p2:
                    musicpane_current_page.add_note_to_selection(i)
                    self.selected_note_indices = [i]

            self.selected_note_descs = [musicpane_current_page.notes[i] for i in self.selected_note_indices]
        elif select_closest_note:
            musicpane_current_page.clear_note_selection()
            if select_closest_note:
                wx.CallAfter(music_pane.redraw)

        if closest_note_data_p1 is not None and ((current_position_is_p1 and
                    closest_note_data_p1.row in musicpane_current_page.notes_in_row)
                    or
                    (p1_page_index == current_page_index and p2_page_index != current_page_index)):
            closest_xy = (closest_note_data_p1.x,closest_note_data_p1.y)

        if closest_xy is not None:
            if select_closest_note:
                wx.CallAfter(music_pane.redraw)
            self.scroll_music_pane(*closest_xy)

    def scroll_music_pane(self, x, y):
        music_pane = self.frame.music_pane
        #FAU: Scroll function need to take into account the zoom factor
        x = self.zoom_factor*x
        y = self.zoom_factor*y
        sx, sy = music_pane.CalcUnscrolledPosition((0, 0))
        vw, vh = music_pane.VirtualSize
        w, h = music_pane.ClientSize
        margin = 50
        orig_scroll = (sx, sy)
        if not sx+margin <= x <= w+sx-margin:
            sx = x - w + w/5
        if not (sy+margin <= y <= h+sy-margin):
            sy = y-h/2
        sx = max(0, min(sx, vw))
        sy = max(0, min(sy, vh))
        if (sx, sy) != orig_scroll:
            ux, uy = music_pane.GetScrollPixelsPerUnit()
            music_pane.Scroll(int(sx/ux), int(sy/uy))

    def OnEditorMouseRelease(self, evt):
        evt.Skip()
        frame = self.frame
        p1, p2 = frame.editor.GetSelection()
        if p1 == p2:
            self.ScrollMusicPaneToMatchEditor(select_closest_note=True, select_closest_page=frame.mni_auto_refresh.IsChecked())
        else:
            self.ScrollMusicPaneToMatchEditor(select_closest_note=True, select_closest_page=False)

    # p09 This function needs more work, see comments below.
    def OnPosChanged(self, evt):
        # This function is called by the interrupt stc.EVT_STC_UPDATEUI
        # which occurs whenever the edit window is updated. This can
        # occur many times. To view who initializes the interrupt,
        # print traceback.extract_stack(None, n) where n is the
        # depth of the stack to view.
        #print traceback.extract_stack(None, 5)
        frame = self.frame
        self.queue_number_movement += 1
        position = frame.editor.GetCurrentPos()
        line_no = frame.editor.LineFromPosition(position)
        #print '*****OnPosChanged***** : position =    ',position,'  ',line_no
        if line_no != self.last_line_number_selected:
            self.last_line_number_selected = line_no
            # 1.3.6 [SS] 2014-12-02
            #wx.CallLater(260, frame.tune_list_controller.OnMovedToDifferentLine, self.queue_number_movement)
        # 1.3.6 [SS] 2014-12-02
        wx.CallLater(260, frame.tune_list_controller.OnMovedToDifferentLine, self.queue_number_movement)
        # if you remove the comment from ScrollMusicToMatchEditor, you will
        # not be able to select a group of notes in the MusicPane. On the
        # otherhand, the following function allows the highlighted note
        # in the MusicPane follow the highlighted note in the editor when
        # it is controlled by the keyboard arrow keys. p09
        #FAU 20250126: To avoid to have sort of a race, keep the call but
        #              only when no action on the music pane to select
        #              Add a property in music_pane to identify when a drag selection is ongoing
        if not frame.music_pane.mouse_select_ongoing:
            self.ScrollMusicPaneToMatchEditor(select_closest_note=True, select_closest_page=True) #patch p08

    def OnPageSelected(self, evt):
        self.select_page(self.frame.cur_page_combo.GetSelection())
        self.frame.editor.SetFocus()

    def select_page(self, page_index):
        self.frame.current_page_index = page_index
        self.UpdateMusicPane()

    def UpdateMusicPane(self):
        frame = self.frame
        cur_page_combo = frame.cur_page_combo
        pages = self.current_svg_tune.page_count
        # 1.3.6.2 [JWdJ] 2015-02
        if cur_page_combo.GetCount() != pages:
            # update page selection combo box
            sel = frame.current_page_index
            cur_page_combo.Clear()
            for page in range(1, pages + 1):
                cur_page_combo.Append('%d / %d' % (page, pages))
            if not (sel < cur_page_combo.GetCount()):
                sel = 0
            frame.current_page_index = sel

            # hide page controls if there are less than 2 pages
            # 1.3.6.2 [JWdJ] 2015-02
            cur_page_combo.Parent.Show(pages > 1)
            if wx.Platform != "__WXMSW__":
                frame.toolbar.Realize() # 1.3.6.4 [JWDJ] fixes toolbar repaint bug on Windows

        # 1.3.6.2 [JWdJ] 2015-02
        try:
            page = self.current_svg_tune.render_page(frame.current_page_index, frame.renderer)
            frame.music_pane.set_page(page)
            #FAU 20250128: rebuild highlight based on position in editor
            #              ScrollMusicPaneToMatchEditor is called without requesting to go to closest page
            page.clear_note_selection()
            self.ScrollMusicPaneToMatchEditor(select_closest_note=True, select_closest_page=False)
            frame.update_statusbar_and_messages()
        except Exception as e:
            error_msg = traceback.format_exc()
            wx.CallLater(600, frame.SetErrorMessage, u'Internal error when drawing svg: %s' % error_msg)
            frame.music_pane.clear()

    # 1.3.6.2 [JWdJ] 2015-02
    def OnMusicUpdateDone(self, evt): # MusicUpdateDoneEvent
        # MusicUpdateThread.run posts an event MusicUpdateDoneEvent with the svg_files
        frame = self.frame
        tune = evt.GetValue()
        same_tune = tune.is_equal(self.current_svg_tune)
        self.current_svg_tune = tune
        selected = frame.tune_list_controller.GetSelectedTune()
        if selected:
            frame.error_marks.apply(frame.editor.LineFromPosition(selected.offset_start), tune.header_line_count, tune.diagnostics)
        else:
            frame.error_marks.clear()
        if not same_tune:
            frame.playback.music_and_score_out_of_sync()
            frame.current_page_index = 0 # 1.3.7.2 [JWDJ] always go to first page after switching tunes

        self.svg_tunes.add(tune) # 1.3.6.3 [JWDJ] for proper disposable of svg files
        self.UpdateMusicPane()
