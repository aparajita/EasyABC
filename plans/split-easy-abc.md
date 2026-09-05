# Split easy_abc.py

**Created:** 2026-09-04  <br>
**Status:** Complete

## Status Dashboard

| Phase | Description | Status | Sub-plan |
|-------|-------------|--------|----------|
| 1 | [Shared state and constants](#-phase-1-shared-state-and-constants) | ✅ Complete | — |
| 2 | [tune_model.py](#-phase-2-tune_modelpy) | ✅ Complete | — |
| 3 | [abc_transform.py](#-phase-3-abc_transformpy) | ✅ Complete | — |
| 4 | [dialogs.py](#-phase-4-dialogspy) | ✅ Complete | — |
| 5 | [abc_tools.py](#-phase-5-abc_toolspy) | ✅ Complete | — |
| 6 | [abc_midi_export.py](#-phase-6-abc_midi_exportpy) | ✅ Complete | — |
| 7 | [background_threads.py](#-phase-7-background_threadspy) | ✅ Complete | — |
| 8 | [search_panel.py](#-phase-8-search_panelpy) | ✅ Complete | — |
| 9 | [settings_dialogs.py and printing.py](#-phase-9-settings_dialogspy-and-printingpy) | ✅ Complete | — |
| 10 | [Method-move probe](#-phase-10-method-move-probe) | ✅ Complete | — |
| 11 | [tune_document.py](#-phase-11-tune_documentpy) | ✅ Complete | — |
| 12 | [score_view.py](#-phase-12-score_viewpy) | ✅ Complete | — |
| 13 | [playback_controller.py](#-phase-13-playback_controllerpy) | ✅ Complete | — |
| 14 | [typing_assistant.py](#-phase-14-typing_assistantpy) | ✅ Complete | — |
| 15 | [exporter.py](#-phase-15-exporterpy) | ✅ Complete | — |
| 16 | [find_replace.py, incipits, printing functions](#-phase-16-find_replacepy-incipits-printing-functions) | ✅ Complete | — |
| 17 | [menu_builder.py](#-phase-17-menu_builderpy) | ✅ Complete | — |
| 18 | [Gate](#-phase-18-gate) | ✅ Complete | — |

## Conventions for every phase

These apply to every phase below. Each phase's tasks assume them.

- **Working directory** is `/Users/aparajita/Developer/projects/EasyABC`. All paths are relative to it. The source file is `easy_abc.py`.
- **Moving a top-level function or class** uses the `mcp__serena__jet_brains_move` tool with `relative_path: "easy_abc.py"`, `name_path: "<Symbol>"`, `target_relative_path: "<new_module>.py"`. It creates the target file if missing, appends the symbol, adds `from <new_module> import <Symbol>` at line 2 of `easy_abc.py`, rewrites every caller, and adds imports to the target module for names the moved body uses. Move symbols one at a time, in the order listed in the phase.
- **After every move**, read the import block at the top of the target module. If it contains `from easy_abc import <name>`, stop and do one of these: if `<name>` is listed in the current phase, move it now and continue; if `<name>` is a module-level constant, it belongs in `constants.py` or `app_state.py` (Phase 1) and that phase was incomplete, so report and stop; otherwise report and stop. A `from easy_abc import` line must never remain in any module when the phase ends, because `easy_abc.py` imports every new module and the cycle fails at startup.
- **Import placement**: the tool inserts `from X import Y` at line 2 of `easy_abc.py`, above the licence comment. At the end of each phase, relocate those lines into the import block, directly after the line `from aligner import align_lines, extract_incipit, bar_sep, bar_sep_without_space, get_bar_length, bar_and_voice_overlay_sep`. Merge lines importing from the same module into one line.
- **The tool prunes imports** in `easy_abc.py` it now considers unused. Leave the pruning in place.
- **Module-level constants used only by moved code** (`gs_search_paths`, `gchordpat`, `keypat`, `search_parts_re`, `clean_lyrics_re`, `myRECORDSTOP`, `EVT_RECORDSTOP`, `myMUSICUPDATEDONE`, `EVT_MUSIC_UPDATE_DONE`, `gmidi_in`) are moved with the same tool in the phase that moves their users, before those users. They are listed where they belong.
- **New modules start with** the licence header copied verbatim from lines 6 through 21 of `easy_abc.py`, then imports. Each new module imports only what it uses, by name: never `from utils import *` or `from wxhelper import *`. `from wx import GetTranslation as _` is needed by every module that calls `_()`.
- **Edits other than tool moves** go through the `Edit` tool, never through `sed` or a script.
- **No compile, no launch, no test run** happens in phases 1 through 17. Phase 18 is the only gate.
- **Snapshot at the end of each phase** with one Bash call: `git add -A && git stash store -m "Finished phase N" "$(git stash create)"`, then `git reset -q` so the index is left as it was.

## ✅ Phase 1: Shared state and constants

**Status:** Complete  <br>
**BlockedBy:** —  <br>
**Files:** app_state.py, constants.py, wxhelper.py, easy_abc.py  <br>
**Recommended model/effort:** Sonnet, medium effort — one class design already fixed below, then a mechanical rewrite of about forty `global` sites

### Tasks

1. Create `app_state.py` containing one class and one instance:

   ```python
   class AppState(object):
       """Process-wide mutable state shared by the frame, the converters and the worker threads."""
       def __init__(self):
           self.messages = u''          # accumulated stdout/stderr of external tools, shown in MyInfoFrame
           self.visible_abc_code = u''  # the ABC last handed to abcm2ps or abc2midi, shown in MyAbcFrame
           self.running = True          # False once the main loop has exited; worker threads poll it

   app_state = AppState()
   ```

   A shared instance is needed because `global execmessages; execmessages += x` rebinds a module attribute, and once the writers live in different modules from the readers each module holds its own stale copy. Attribute assignment on one instance is visible everywhere.

2. In `easy_abc.py`, delete the module-level assignments `execmessages = u''` (line 292), `visible_abc_code = u''` (line 293) and `application_running = True` (line 118). Add `from app_state import app_state` to the import block.

3. Rewrite every site that reads or writes those three names. Find them with `grep -n "execmessages\|visible_abc_code\|application_running" easy_abc.py`. At each site: delete the `global execmessages`, `global visible_abc_code`, `global execmessages, visible_abc_code` and `global application_running` statements; replace `execmessages` with `app_state.messages`, `visible_abc_code` with `app_state.visible_abc_code`, and `application_running` with `app_state.running`. This includes the `update_text` static methods of `MyInfoFrame` (line 9130) and `MyAbcFrame` (line 9173), the `if application_running:` test in `MusicUpdateThread.run` (line 1609), and `application_running = False` after `app.MainLoop()` (line 9351). Lines 6300 through 6308 are commented-out code mentioning `current_locale`; leave them.

4. Create `constants.py` and move these module-level assignments into it verbatim, then import them by name in `easy_abc.py`: `program_version`, `program_name`, `abcm2ps_default_encoding`, `utf8_byte_order_mark`, `max_int`, `WX4`, `application_path`, `cwd` (including the `os.getenv('EASYABCDIR')` fallback and the `sys.path.append(cwd)` line), `control_margin`, `default_midi_volume`, `default_midi_pan`, `default_midi_instrument`, `line_end_re`, `tune_index_re`. `constants.py` imports `sys`, `os`, `codecs`, `re`, `wx`, and `from utils import get_application_path`. These are plain assignments, not symbols the move tool handles, so use `Edit`.

5. Move `apply_editor_appearance` and `get_normal_fontsize` from `easy_abc.py` into `wxhelper.py` with the move tool. Both are wx helpers used by `MainFrame`, `ErrorFrame` and `MyAbcFrame`, which end up in different modules. `wxhelper.py` needs `import wx.stc as stc` for `apply_editor_appearance`.

6. Relocate the imports the tool added at line 2 per the conventions.

## ✅ Phase 2: tune_model.py

**Status:** Complete  <br>
**BlockedBy:** 1  <br>
**Files:** tune_model.py, easy_abc.py  <br>
**Recommended model/effort:** Sonnet, low effort — tool moves in a fixed order

### Tasks

1. Using `Edit`, move the two `namedtuple` assignments `Tune` (line 150) and `MidiNote` (line 151) into a new `tune_model.py`, and add `from tune_model import Tune, MidiNote` to `easy_abc.py`. `tune_model.py` imports `from collections import namedtuple`.
2. Move with the tool, in this order: `text_to_lines`, `read_abc_file`, `MidiTune`, `SvgTune`, `AbcTunes`.
3. Confirm `tune_model.py` imports `line_end_re` from `constants` and nothing from `easy_abc`.
4. Relocate imports per the conventions.

## ✅ Phase 3: abc_transform.py

**Status:** Complete  <br>
**BlockedBy:** 2  <br>
**Files:** abc_transform.py, easy_abc.py  <br>
**Recommended model/effort:** Sonnet, low effort — tool moves in a fixed order

### Tasks

1. Using `Edit`, move the assignment `all_notes = "C,, D,, ...".split()` (line 288) into a new `abc_transform.py`, keeping `from abc_transform import all_notes` in `easy_abc.py` because `MainFrame.DoReMiToNote` and `OnCharEvent` still read it.
2. Move with the tool, in this order: `str2fraction`, `frac_mod`, `note_to_index`, `str2bool`, `get_hash_code`, `remove_non_note_fragments`, `get_notes_from_abc`, `copy_bar_symbols_from_first_voice`, `process_MCM`, `change_abc_tempo`, `sort_abc_tunes`, `process_abc_code`, `fix_boxmarks_texts`, `change_texts_into_chords`.
3. Confirm `abc_transform.py` imports `Tune` and `text_to_lines` from `tune_model`, `program_name` from `constants`, and nothing from `easy_abc`.
4. Relocate imports per the conventions.

## ✅ Phase 4: dialogs.py

**Status:** Complete  <br>
**BlockedBy:** 3  <br>
**Files:** abc_tools.py, dialogs.py, easy_abc.py  <br>
**Recommended model/effort:** Sonnet, low effort — tool moves in a fixed order

### Tasks

1. Move the three exception classes `AbortException`, `Abcm2psException`, `NWCConversionException` (lines 152 through 154) into a new `abc_tools.py` with the tool. They go first because `MyFileDropTarget` catches `AbortException` and must import it from `abc_tools`, not `easy_abc`.
2. Move with the tool into `dialogs.py`, in this order: `FieldReferenceTree`, `IncipitsFrame`, `ErrorFrame`, `ProgressFrame`, `MyMidiTextTree`, `MyInfoFrame`, `MyAbcFrame`, `MyTunesListFrame`, `AboutFrame`, `MyFileDropTarget`.
3. Confirm `dialogs.py` imports `app_state` from `app_state`, `WX4`, `control_margin`, `cwd`, `program_name` from `constants`, `apply_editor_appearance`, `get_normal_fontsize` from `wxhelper`, `AbortException` from `abc_tools`, and nothing from `easy_abc`.
4. Relocate imports per the conventions.

## ✅ Phase 5: abc_tools.py

**Status:** Complete  <br>
**BlockedBy:** 4  <br>
**Files:** abc_tools.py, easy_abc.py  <br>
**Recommended model/effort:** Sonnet, low effort — tool moves in a fixed order

### Tasks

1. Using `Edit`, move the assignment `gs_search_paths` (line 437 with its two comment lines) into `abc_tools.py`.
2. Move with the tool, in this order: `start_process`, `get_output_from_process`, `show_in_browser`, `launch_file`, `get_default_path_for_executable`, `get_ghostscript_path`, `find_ps_to_pdf_converter`, `AbcToPS`, `GetSvgFileList`, `abc_to_svg`, `AbcToSvg`, `AbcToAbc`, `MidiToMftext`, `get_midi_structure_as_text`, `AbcToPDF`, `NWCToXml`.
3. Confirm `abc_tools.py` imports `process_abc_code` from `abc_transform`, `MyMidiTextTree` from `dialogs`, `app_state` from `app_state`, `abcm2ps_default_encoding`, `cwd` from `constants`, and nothing from `easy_abc`.
4. Relocate imports per the conventions.

## ✅ Phase 6: abc_midi_export.py

**Status:** Complete  <br>
**BlockedBy:** 5  <br>
**Files:** abc_midi_export.py, easy_abc.py  <br>
**Recommended model/effort:** Sonnet, low effort — tool moves in a fixed order

### Tasks

1. Using `Edit`, move the assignments `gchordpat` and `keypat` (lines 921 and 922) into a new `abc_midi_export.py`.
2. Move with the tool, in this order: `test_for_guitar_chords`, `list_voices_in`, `grab_time_signature`, `drum_intro`, `need_left_repeat`, `make_abc_introduction`, `add_abc2midi_options`, `abc_to_midi`, `process_abc_for_midi`, `AbcToMidi`.
3. Confirm `abc_midi_export.py` imports `get_output_from_process` from `abc_tools`, `change_abc_tempo`, `process_MCM`, `str2bool` from `abc_transform`, `MyAbcFrame`, `MyInfoFrame` from `dialogs`, `MidiTune`, `text_to_lines` from `tune_model`, `default_midi_pan`, `default_midi_volume` from `constants`, `app_state` from `app_state`, and nothing from `easy_abc`.
4. Relocate imports per the conventions.

## ✅ Phase 7: background_threads.py

**Status:** Complete  <br>
**BlockedBy:** 6  <br>
**Files:** background_threads.py, easy_abc.py  <br>
**Recommended model/effort:** Sonnet, low effort — tool moves in a fixed order

### Tasks

1. Using `Edit`, move the assignments `myRECORDSTOP`, `EVT_RECORDSTOP` (lines 1451 and 1452), `gmidi_in` (line 1461), `myMUSICUPDATEDONE`, `EVT_MUSIC_UPDATE_DONE` (lines 1463 and 1464) into a new `background_threads.py`. Keep `from background_threads import EVT_RECORDSTOP, EVT_MUSIC_UPDATE_DONE` in `easy_abc.py`, which binds both in `MainFrame.__init__`.
2. Move with the tool, in this order: `RecordStopEvent`, `MusicUpdateDoneEvent`, `MusicUpdateThread`, `MidiThread`, `RecordThread`. `SearchFilesThread` is not moved here; it goes to `search_panel.py` in Phase 8.
3. Confirm `background_threads.py` imports `Abcm2psException`, `abc_to_svg`, `start_process` from `abc_tools`, `frac_mod`, `process_abc_code` from `abc_transform`, `SvgTune`, `read_abc_file` from `tune_model`, `cwd` from `constants`, `app_state` from `app_state`, and nothing from `easy_abc`.
4. Relocate imports per the conventions.

## ✅ Phase 8: search_panel.py

**Status:** Complete  <br>
**BlockedBy:** 7  <br>
**Files:** search_panel.py, easy_abc.py  <br>
**Recommended model/effort:** Sonnet, low effort — tool moves in a fixed order

### Tasks

1. Using `Edit`, move the assignments `search_parts_re` and `clean_lyrics_re` (lines 3822 and 3823) into a new `search_panel.py`.
2. Move with the tool, in this order: `lyrics_to_text`, `SearchFilesThread`, `FlexibleListCtrl`, `AbcSearchPanel`.
3. Confirm `search_panel.py` imports `read_abc_file` from `tune_model`, `control_margin` from `constants`, and nothing from `easy_abc`.
4. Relocate imports per the conventions.

## ✅ Phase 9: settings_dialogs.py and printing.py

**Status:** Complete  <br>
**BlockedBy:** 8  <br>
**Files:** settings_dialogs.py, printing.py, easy_abc.py  <br>
**Recommended model/effort:** Sonnet, low effort — tool moves plus one two-line edit

### Tasks

1. In `MyChordPlayPage` (line 2217), `frame = app._frames[0]` reads the module-level `app` assigned in `easy_abc.py`'s `__main__` block. Replace it with `frame = wx.GetApp()._frames[0]`.
2. Move with the tool into `settings_dialogs.py`, in this order: `MyNoteBook`, `AbcFileSettingsFrame`, `MyChordPlayPage`, `MyVoicePage`, `MidiSettingsFrame`, `MyAbcm2psPage`, `ColorSettingsFrame`, `MusicXmlPage`, `MidiOptionsFrame`.
3. Confirm `settings_dialogs.py` imports `WX4`, `control_margin`, `cwd`, `default_midi_instrument`, `default_midi_pan`, `default_midi_volume` from `constants` and nothing from `easy_abc`.
4. Move `MusicPrintout` with the tool into a new `printing.py`.
5. Relocate imports per the conventions. After this phase `easy_abc.py` holds only the header, imports, `PaneManager`, `MainFrame`, `MyApp` and the `__main__` block.

## ✅ Phase 10: Method-move probe

**Status:** Complete  <br>
**BlockedBy:** 9  <br>
**Files:** easy_abc.py, score_view.py  <br>
**Recommended model/effort:** Fable, low effort — the result decides the procedure for phases 11 through 17

### Method-move procedure

**Manual form.** `mcp__serena__jet_brains_move` with `name_path: "MainFrame/scroll_to_notes"` and `target_relative_path: "score_view.py"` refused the move: "Move from 'MainFrame/scroll_to_notes' in easy_abc.py to score_view.py had no effect. The source is still at its original location." It wrote nothing to `easy_abc.py` and did not create `score_view.py`, so a method whose body uses `self` cannot be moved to a top-level function by the tool. Phases 11 through 17 therefore:

1. Create the controller class in its module with `Edit`, per the controller conventions below.
2. Cut each method body from `MainFrame` and paste it under the class, then rewrite references per that phase's ownership list.
3. Rewrite `MainFrame` callers found by `grep -n "self\.<method>\b" easy_abc.py`.

### Tasks

1. Try `mcp__serena__jet_brains_move` with `relative_path: "easy_abc.py"`, `name_path: "MainFrame/scroll_to_notes"`, `target_relative_path: "score_view.py"` and no `target_parent_name_path`. `scroll_to_notes` (about 10 lines) reads `self.music_pane` and `self.zoom_factor`, so it exercises a method whose body uses `self`. Moving a method with an unused `self` is known to work and produces a top-level function with `self` removed and callers rewritten; moving a method into a class in another file is known to be unsupported.
2. Inspect `score_view.py` and the diff of `easy_abc.py`. Record the outcome as a **Method-move procedure** subsection at the top of this phase, in one of these two forms, so phases 11 through 17 follow it:
   - **Tool form**, if the method arrived as a top-level function keeping a `self` parameter and callers were rewritten to pass `self`: each later phase moves its methods with the tool, then wraps the functions into the controller class by indenting them under `class X(object):` and renaming the `self` parameter's uses of frame state per that phase's ownership list.
   - **Manual form**, if the tool refused or produced a function with `self` references dangling: each later phase creates the controller class with `Edit`, cuts each method body from `MainFrame` and pastes it under the class, then rewrites references per that phase's ownership list, and rewrites `MainFrame` callers by `grep -n "self\.<method>\b" easy_abc.py`.
3. Revert the probe with `git checkout easy_abc.py` and `rm score_view.py` unless the result is exactly what Phase 12 wants, in which case leave it.

## Controller conventions (phases 11 through 17)

Every controller class follows the same shape, so phases can be written by ownership lists alone.

- The class lives in its own module, takes the frame in its constructor, and stores it as `self.frame`. The frame constructs it in `MainFrame.__init__` directly after `self.settings` is assigned, as `self.<attribute> = <Class>(self)`, and the attribute name is given in each phase.
- **Frame state** a moved method reads or writes stays on the frame and is accessed as `self.frame.<name>`. The frame-wide shared names, read by nearly every controller, are: `editor`, `settings`, `cache_dir`, `tune_list`, `music_pane`, `statusbar`, `manager`, `renderer`, `error_marks`, `styler`, `toolbar`, `GetMenuBar()`, the `mni_*` menu items, `zoom_slider`, `bpm_slider`, `timing_slider`, `progress_slider`, `cur_page_combo`, `play_button`, `loop_check`, `follow_score_check`, `play_bitmap`, `pause_bitmap`.
- **Owned state** listed in the phase is initialised in the controller's `__init__` and accessed as `self.<name>`. Its initialiser is deleted from `MainFrame.__init__`. If a method outside the controller reads that state, the reference becomes `self.<controller>.<name>`; `grep -n "self\.<name>\b" easy_abc.py` finds them.
- **Methods of the same controller** are called as `self.<method>`. **Methods of a different controller** are called as `self.frame.<controller>.<method>`. **Methods still on `MainFrame`** are called as `self.frame.<method>`. The frame's own callers of a moved method become `self.<controller>.<method>`.
- **wx event handlers** keep their `event` parameter and signature. Menu and toolbar `Bind` calls in `setup_menus` and `setup_toolbar` that name a moved handler become `self.<controller>.<Handler>`. These are the same rewrite as any other frame caller; Phase 17 then moves `setup_menus` and `setup_toolbar` themselves.
- `wx.CallAfter`, `wx.CallLater` and `Bind` calls inside moved methods that pass `self.<method>` are rewritten by the same rules.
- Properties on `MainFrame` (`current_page_index`, `current_file`) stay on the frame and are read as `self.frame.current_page_index`.
- `global execmessages` and similar statements no longer exist after Phase 1; `app_state` is imported into each controller module that needs it.

## ✅ Phase 11: tune_document.py

**Status:** Complete  <br>
**BlockedBy:** 10  <br>
**Files:** tune_document.py, easy_abc.py  <br>
**Recommended model/effort:** Fable, low effort — two classes, ownership of `tunes` and the file path moves off the frame

### Tasks

1. Create `tune_document.py` with class `TuneDocument`, frame attribute `self.document`. Owned state: `_current_file` with the `current_file` property (getter and setter, currently `MainFrame` lines 4257 through 4265), `untitled_number`, `document_name`, `updating_text`. `current_file` is read across `MainFrame`; every `self.current_file` becomes `self.document.current_file`.
2. Move these `MainFrame` methods onto `TuneDocument`: `new_tune`, `add_recent_file`, `CanClose`, `OnNew`, `OnOpen`, `OnImport`, `load_or_import`, `abc_bytes_to_text`, `fix_end_of_line_sequence`, `load`, `load_and_position`, `ask_save`, `save`, `save_as`, `OnSave`, `OnSaveAs`, `OnCloseFile`, `OnDropFile`. `abc_bytes_to_text` and `fix_end_of_line_sequence` use nothing from the frame; make them module-level functions in `tune_document.py` rather than methods.
3. Create class `TuneList` in the same module, frame attribute `self.tune_list_controller`. Owned state: `tunes` (the `AbcTunes` instance), `selected_tune`, `multi_tunes_menu_items`. Move onto it: `GetTunes`, `GetTune`, `GetTuneAbc`, `GetSelectedTune`, `GetSelectedTunes`, `selected_tune_iterator`, `GetTextRangeOfTune`, `GetTextPositionOfTune`, `GetFileHeaderBlock`, `UpdateTuneList`, `UpdateTuneListAndReselectTune`, `OnTuneSelected`, `OnTuneDeselected`, `OnTuneListClick`, `OnTuneDoubleClicked`, `SelectOnlyTuneIfTuneNotSelected`, `MoveTune`, `OnMoveTuneUp`, `OnMoveTuneDown`, `OnSortTunes`, `OnRenumberTunes`, `update_multi_tunes_menu_items`, `select_tune_at_current_pos`, `OnMovedToDifferentLine`.
4. `GetSelectedTune` is called from at least nine other method groups. Every `self.GetSelectedTune()` elsewhere becomes `self.frame.tune_list_controller.GetSelectedTune()` inside a controller, or `self.tune_list_controller.GetSelectedTune()` inside `MainFrame`. Apply the same to `GetSelectedTunes`, `GetTune`, `GetFileHeaderBlock`, `GetTunes`.
5. Rewrite frame callers and `Bind` sites per the controller conventions.

## ✅ Phase 12: score_view.py

**Status:** Complete  <br>
**BlockedBy:** 11  <br>
**Files:** score_view.py, easy_abc.py  <br>
**Recommended model/effort:** Fable, low effort — the editor-to-score scrolling code shares selection state with playback

### Tasks

1. Create `score_view.py` with class `ScoreView`, frame attribute `self.score_view`. Owned state: `svg_tunes`, `current_svg_tune`, `selected_note_descs`, `selected_note_indices`, `zoom_factor`, `last_line_number_selected`, `queue_number_movement`, `queue_number_refresh_music`, `music_update_thread`, `score_is_maximized`. Playback (Phase 13) reads `current_svg_tune`, `selected_note_descs`, `selected_note_indices` as `self.frame.score_view.<name>`; the tune list clears `selected_note_descs` in `OnTuneSelected` and must be rewritten to `self.frame.score_view.selected_note_descs`.
2. Move onto `ScoreView`: `ScrollMusicPaneToMatchEditor`, `scroll_music_pane`, `scroll_to_notes`, `OnMusicPaneClick`, `OnRightClickMusicPane`, `OnMusicPaneDoubleClick`, `OnMusicPaneKeyDown`, `OnNoteSelectionChangedDesc`, `transpose_selected_note`, `parse_desc`, `get_num_extra_header_lines`, `UpdateMusicPane`, `OnMusicUpdateDone`, `select_page`, `OnPageSelected`, `OnZoomSlider`, `OnZoomSliderClick`, `OnEditorMouseRelease`, `OnPosChanged`, `OnToggleMusicPaneMaximize`, `closestNoteData`, `FindNotesIndicesBetween2Notes`, `refresh_tunes`, `OnToolRefresh`. `parse_desc` uses nothing from the frame; make it a module-level function.
3. `MainFrame.__init__` binds `EVT_MUSIC_UPDATE_DONE` to `OnMusicUpdateDone` and `music_pane` events to the `OnMusicPane*` handlers; those `Bind` targets become `self.score_view.<Handler>`.
4. Rewrite frame callers and `Bind` sites per the controller conventions.

## ✅ Phase 13: playback_controller.py

**Status:** Complete  <br>
**BlockedBy:** 12  <br>
**Files:** playback_controller.py, easy_abc.py  <br>
**Recommended model/effort:** Fable, low effort — timers, threads and the media player interact; three pure functions are extracted

### Tasks

1. Create `playback_controller.py` with class `PlaybackController`, frame attribute `self.playback`. Owned state: `mc` (the media player), `midi_tunes`, `current_midi_tune`, `current_time_slice`, `future_time_slice`, `played_notes_timeline`, `started_playing`, `play_music_thread`, `play_timer`, `index`, `queue_number_follow_score`, `applied_tempo_multiplier`, `record_thread`, `uses_fluidsynth`. `Exporter` (Phase 15) reads `mc` and `uses_fluidsynth` as `self.frame.playback.<name>`.
2. `extract_note_timings`, `fill_time_gaps` and `group_notes_by_time` read no frame state except `self.frame.settings` in `extract_note_timings`. Move them to module-level functions in `playback_controller.py`; `extract_note_timings` takes `settings` as a parameter. `MidiNote` and `max_int` are imported from `tune_model` and `constants`.
3. Move onto `PlaybackController`: `play`, `stop_playing`, `update_playback_rate`, `OnBpmSlider`, `OnBpmSliderClick`, `reset_BpmSlider`, `OnChangeLoopPlayback`, `OnChangeFollowScore`, `UpdateTimingSliderVisibility`, `OnChangeTiming`, `OnTimingSliderClick`, `start_midi_out`, `do_load_media_file`, `OnMediaLoaded`, `OnAfterStop`, `OnToolRecord`, `OnToolStop`, `OnSeek`, `OnPlayTimer`, `FollowScore`, `music_and_score_out_of_sync`, `OnRecordBpmSelected`, `OnRecordMetreSelected`, `OnRecordStop`, `update_play_button`, `OnToolPlay`, `loop_midi_playback`, `set_loop_midi_playback`, `OnToolPlayLoop`, `PlayMidi`, `GetAbcToPlay`, `handle_midi_conversion`, `internal_midi_conversion`, `ReportFluidSynthIsMissing`, `get_tempo_multiplier`, `flip_tempobox`.
4. `MainFrame.__init__` creates `self.mc` and `self.play_timer` and binds `EVT_RECORDSTOP`, the media-player events and the timer; move that construction into `PlaybackController.__init__` and rebind to `self.<Handler>`. `MainFrame.OnClose` and `Destroy` stop the timer and threads; those lines become `self.playback.<name>`.
5. Rewrite frame callers and `Bind` sites per the controller conventions.

## ✅ Phase 14: typing_assistant.py

**Status:** Complete  <br>
**BlockedBy:** 13  <br>
**Files:** typing_assistant.py, easy_abc.py, tune_document.py, playback_controller.py  <br>
**Recommended model/effort:** Fable, low effort — `OnCharEvent` is 260 lines with many branches reading menu state

### Tasks

1. Using `Edit`, move the assignments `doremi_prefixes` and `doremi_suffixes` (lines 289 and 290) into a new `typing_assistant.py`.
2. Create class `TypingAssistant` in that module, frame attribute `self.typing_assistant`. Owned state: `keyboard_input_mode`. The eight `mni_TA_*` check items stay on the frame and are read as `self.frame.mni_TA_<name>.IsChecked()`.
3. Move onto `TypingAssistant`: `OnCharEvent`, `OnKeyDownEvent`, `AutoInsertXNum`, `DoReMiToNote`, `FixNoteDurations`, `add_bar_if_needed`, `insert_bar`, `AddTextWithUndo`, `replace_selection`, `position_is_music_code`, `position_is_in_chord`, `StartKeyboardInputMode`, `get_metre_and_default_length`, `OnDoReMiModeChange`, `OnInsertSymbol`.
4. `AddTextWithUndo` is called from the document, playback and frame code; each caller becomes `self.frame.typing_assistant.AddTextWithUndo` or `self.typing_assistant.AddTextWithUndo`.
5. `InitEditor` on the frame binds `stc.EVT_STC_CHARADDED` and `wx.EVT_KEY_DOWN` on the editor to `OnCharEvent` and `OnKeyDownEvent`; those targets become `self.typing_assistant.<Handler>`.
6. Rewrite frame callers and `Bind` sites per the controller conventions.

## ✅ Phase 15: exporter.py

**Status:** Complete  <br>
**BlockedBy:** 14  <br>
**Files:** exporter.py, easy_abc.py  <br>
**Recommended model/effort:** Sonnet, medium effort — many small methods, uniform rewrite, no owned state

### Tasks

1. Create `exporter.py` with class `Exporter`, frame attribute `self.exporter`. It owns no state.
2. Move onto `Exporter`: `GetFileNameForTune`, `OnExportToClipboard`, `OnExportMidi`, `OnExportAllMidi`, `export_midi`, `OnExportToMP3`, `OnExportToAAC`, `OnExportToWave`, `export_wave`, `export_mp3`, `export_aac`, `export_ffmpeg`, `OnExportAllPDFFiles`, `OnExportPDF`, `OnExportAllPDF`, `OnExportSelectedToSinglePDF`, `export_pdf`, `export_pdf_tunes`, `OnExportSVG`, `export_svg`, `OnExportMusicXML`, `OnExportAllMusicXML`, `export_tunes_to_musicxml`, `export_musicxml`, `OnExportHTML`, `OnExportInteractiveHTML`, `export_html`, `comment_pageheight`, `export_interactive_html`, `OnExportAllHTML`, `OnExportAllInteractiveHTML`, `OnExportAllEpub`, `copy_to_destination_and_launch_file`, `OnExportToABC`, `export_abc`, `export_tune`, `create_tune_from_multi_abc`, `export_tunes`, `AbcToAbcCurrentTune`, `OnHalveL`, `OnDoubleL`, `OnTranspose`, `OnAlignBars`. `comment_pageheight` and `create_tune_from_multi_abc` use nothing from the frame; make them module-level functions.
3. Calls into other controllers follow the conventions: `self.frame.tune_list_controller.GetSelectedTunes()`, `self.frame.document.OnNew(...)`, `self.frame.playback.ReportFluidSynthIsMissing()`, `self.frame.playback.get_tempo_multiplier()`, `self.frame.update_statusbar_and_messages()`.
4. Rewrite frame callers and `Bind` sites per the controller conventions.

## ✅ Phase 16: find_replace.py, incipits, printing functions

**Status:** Complete  <br>
**BlockedBy:** 15  <br>
**Files:** find_replace.py, dialogs.py, printing.py, easy_abc.py  <br>
**Recommended model/effort:** Sonnet, low effort — three small, independent groups

### Tasks

1. Create `find_replace.py` with class `FindReplace`, frame attribute `self.find_replace`. Owned state: `find_data`, `find_dialog`, `replace_dialog`. Move onto it: `OnFind`, `OnReplace`, `close_existing_find_and_replace_dialogs`, `OnFindClose`, `get_scintilla_find_flags`, `OnFindReplace`, `OnFindReplaceAll`, `OnFindNextABC`, `OnFindNext`. `TuneList.OnTuneSelected` reads `find_dialog` and `replace_dialog`; rewrite those reads to `self.frame.find_replace.<name>`.
2. `generate_incipits_abc` reads only `self.frame.settings` and calls `GetTune`; move it into `dialogs.py` as a module-level function `generate_incipits_abc(settings, tune_list_controller, ...)` with the frame-derived values as parameters, and move `OnGenerateIncipits` and `OnViewIncipits` onto `TuneList` in `tune_document.py`, importing `IncipitsFrame` and `generate_incipits_abc` from `dialogs`.
3. Move `print_or_preview_svg`, `OnPageSetup`, `OnPrint`, `OnPrintPreview` into `printing.py` as module-level functions taking `frame` as their first parameter, and the owned state `printData` becomes a module-level attribute set on first use. Bind sites in `setup_menus` become `lambda event: printing.OnPrint(self, event)` or an equivalent `functools.partial`.
4. Rewrite frame callers and `Bind` sites per the controller conventions.

## ✅ Phase 17: menu_builder.py

**Status:** Complete  <br>
**BlockedBy:** 16  <br>
**Files:** menu_builder.py, easy_abc.py  <br>
**Recommended model/effort:** Sonnet, medium effort — `setup_menus` is one 150-line table whose handler references must all resolve

### Tasks

1. Create `menu_builder.py` with module-level functions, each taking `frame` as the first parameter, moved from `MainFrame`: `setup_menus`, `setup_toolbar`, `create_symbols_popup_menu`, `create_upload_context_menu`, `add_to_multi_list`, `setup_typing_assistance_menu`, `add_slider_to_toolbar`, `add_combobox_to_toolbar`, `add_label_and_controls_to_panel`, `add_checkbox_to_toolbar`, `update_recent_files_menu`, `on_recent_file`, `show_toolbar_panel`, `disable_in_exclusive_mode`, `GrayUngray`. Inside these, `self.` becomes `frame.`. Widgets they create (`self.toolbar`, `self.mni_*`, `self.bpm_slider`, …) stay as `frame.<name>` attributes, so nothing else changes its access path.
2. Every handler reference in `setup_menus` and `setup_toolbar` must name the object that now owns it: `frame.OnUndo` for handlers still on the frame, `frame.exporter.OnExportPDF`, `frame.playback.OnToolPlay`, `frame.document.OnOpen`, `frame.tune_list_controller.OnSortTunes`, `frame.score_view.OnZoomSlider`, `frame.typing_assistant.OnDoReMiModeChange`, `frame.find_replace.OnFind`, and the `printing` and incipits forms from Phase 16. Before rewriting each reference, run `grep -n "def <Handler>\b" *.py` and use the module that defines it.
3. `MainFrame.__init__` calls `self.setup_menus()` and `self.setup_toolbar()`; these become `menu_builder.setup_menus(self)` and `menu_builder.setup_toolbar(self)`. `update_recent_files_menu` is called from `TuneDocument.add_recent_file` and from `restore_settings`; both become `menu_builder.update_recent_files_menu(self.frame)` or `menu_builder.update_recent_files_menu(self)`.

## ✅ Phase 18: Gate

**Status:** Complete  <br>
**BlockedBy:** 17  <br>
**Files:** —  <br>
**Recommended model/effort:** Sonnet, low effort — run checks, report output verbatim, hand the manual list to the user

### Tasks

1. Install the checker into the project venv: `.venv/bin/python -m pip install pyflakes`.
2. Run `.venv/bin/python -m py_compile easy_abc.py app_state.py constants.py tune_model.py abc_transform.py dialogs.py abc_tools.py abc_midi_export.py background_threads.py search_panel.py settings_dialogs.py printing.py tune_document.py score_view.py playback_controller.py typing_assistant.py exporter.py find_replace.py menu_builder.py wxhelper.py` and report any error verbatim.
3. Run `.venv/bin/python -m pyflakes` on the same file list. Fix every "undefined name" and every "imported but unused" in the new modules. Fix every "undefined name" in `easy_abc.py`. An undefined name is a reference the move left behind and is fixed by importing from the module that now defines it, found with `grep -n "^def <name>\|^class <name>\|^<name> =" *.py`.
4. Run `.venv/bin/python -m pytest tests` and report the output.
5. Confirm `grep -rn "from easy_abc import" *.py` prints nothing.
6. Ask the user to run `./run.sh` and check, in order: open an ABC file, select a tune, press Play and hear it, Export to PDF, type a note into the editor and see typing assistance react, sort tunes via the menu, and Find text. Report what the user says.
7. Uninstall the checker: `.venv/bin/python -m pip uninstall -y pyflakes`.
