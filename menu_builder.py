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

import os

import wx
import wx.lib.agw.aui as aui
import wx.lib.platebtn as platebtn
from wx import GetTranslation as _

import printing
from wxhelper import create_menu, create_menu_bar, append_menu_item, append_submenu, delete_menuitem


def setup_menus(frame):
    # 1.3.7.1 [JWDJ] creation of menu bar now more structured using less code
    ornaments = 'v u - accent staccato tenuto - open plus snap - trill pralltriller mordent roll fermata - 0 1 2 3 4 5 - turn turnx invertedturn invertedturnx - shortphrase breath'.split()
    dynamics = 'p pp ppp - f ff fff - mp mf sfz'.split()
    directions = 'coda segno D.C. D.S. fine barline repeat_left repeat_right repeat_both repeat1 repeat2'.split()

    frame.popup_ornaments = create_symbols_popup_menu(frame, ornaments)
    frame.popup_dynamics = create_symbols_popup_menu(frame, dynamics)
    frame.popup_directions = create_symbols_popup_menu(frame, directions)

    transpose_menu = create_menu([], parent=frame)
    for i in reversed(range(-12, 12+1)):
        if i < 0:
            append_menu_item(transpose_menu, _('Down %d semitones') % abs(i), '', lambda e, i=i: frame.exporter.OnTranspose(i))
        elif i == 0:
            transpose_menu.AppendSeparator()
        elif i > 0:
            append_menu_item(transpose_menu, _('Up %d semitones') % i, '', lambda e, i=i: frame.exporter.OnTranspose(i))

    view_menu = create_menu([], parent=frame)
    append_menu_item(view_menu, _("&Refresh music")+"\tF5", "", frame.score_view.OnToolRefresh)
    frame.mni_auto_refresh = append_menu_item(view_menu, _("&Automatically refresh music as I type"), "", None, kind=wx.ITEM_CHECK)
    view_menu.AppendSeparator()
    frame.mni_reduced_margins = append_menu_item(view_menu, _("&Use reduced margins when displaying tunes on screen"), "", frame.OnReducedMargins, kind=wx.ITEM_CHECK)
    append_menu_item(view_menu, _("&Change editor font..."), "", frame.OnChangeFont)
    append_menu_item(view_menu, _("&Use default editor font"), "", frame.OnUseDefaultFont)
    append_menu_item(view_menu, _("&Actual editor font size") + "\tCtrl+1", "", frame.OnActualFontSize)
    view_menu.AppendSeparator()
    append_menu_item(view_menu, _("&Reset window layout to default"), "", frame.OnResetView)
    view_menu.AppendSeparator()
    append_menu_item(view_menu, _("&Full screen") + '\tShift+Alt+F', "", frame.toggle_fullscreen)

    #append_menu_item(view_menu, _("&Maximize/restore musical score pane") + "\tCtrl+M", "", frame.score_view.OnToggleMusicPaneMaximize)

    frame.recent_menu = create_menu([], parent=frame)

    disable_in_exclusive = lambda menu_item: disable_in_exclusive_mode(frame, menu_item)
    add_to_multi = lambda menu_item: add_to_multi_list(frame, menu_item)

    menuBar = create_menu_bar([
        (_("&File")     , [
            (_('&New') + '\tCtrl+N', _("Create a new file"), frame.document.OnNew, disable_in_exclusive),
            (_('&Open...') + '\tCtrl+O', _("Open an existing file"), frame.document.OnOpen, disable_in_exclusive),
            (_("&Close") + '\tCtrl+W', _("Close the current file"), frame.document.OnCloseFile, disable_in_exclusive),
            (),
            (_("&Import and add..."), _("Import a song in ABC, Midi or MusicXML format and add it to the current document."), frame.document.OnImport, disable_in_exclusive),
            (),
            (_("&Export selected"), [
                (_('as &PDF...'), '', frame.exporter.OnExportPDF),
                (_('as one &PDF...'), '', frame.exporter.OnExportSelectedToSinglePDF, add_to_multi),
                (_('as &MIDI...'), '', frame.exporter.OnExportMidi),
                (_('as &SVG...'), '', frame.exporter.OnExportSVG),
                (_('as &HTML...'), '', frame.exporter.OnExportHTML),
                (_('as HTML (&interactive)...'), '', frame.exporter.OnExportInteractiveHTML),
                (_('as Music&XML...'), '', frame.exporter.OnExportMusicXML),
                (_('as A&BC...'), '', frame.exporter.OnExportToABC),
                (_('as &Wave...'), '', frame.exporter.OnExportToWave),
                (_('as &MP3...'), '', frame.exporter.OnExportToMP3),
                (_('as &AAC...'), '', frame.exporter.OnExportToAAC)]),
            (_("Export &all"), [
                (_('as a &PDF Book...'), '', frame.exporter.OnExportAllPDF),
                (_('as PDF &Files...'), '', frame.exporter.OnExportAllPDFFiles),
                (_('as &MIDI...'), '', frame.exporter.OnExportAllMidi),
                (_('as &HTML...'), '', frame.exporter.OnExportAllHTML),
                (_('as HTML (&interactive)...'), '', frame.exporter.OnExportAllInteractiveHTML),
                #(_('as &EPUB...'), '', frame.exporter.OnExportAllEpub),
                (_('as Music&XML...'), '', frame.exporter.OnExportAllMusicXML)]),
            (),
            (_("&Save") + "\tCtrl+S", _("Save the active file"), frame.document.OnSave),
            (_("Save &As...") + "\tShift+Ctrl+S", _("Save the active file with a new filename"), frame.document.OnSaveAs),
            (),
            (_("&Print...") + "\tCtrl+P", _("Print the selected tune"), lambda event: printing.OnPrint(frame, event)),
            (_("&Print preview") + "\tCtrl+Shift+P", '', lambda event: printing.OnPrintPreview(frame, event)),
            (_("P&age Setup..."), _("Change the printer and printing options"), lambda event: printing.OnPageSetup(frame, event)),
            (),
            (_('&Recent files'), frame.recent_menu, disable_in_exclusive),
            (),
            (wx.ID_EXIT, _("&Quit") + "\tCtrl+Q", _("Exit the application (prompt to save files)"), frame.OnQuit)]),
        (_("&Edit")     , [
            (_("&Undo") + "\tCtrl+Z", _("Undo the last action"), frame.OnUndo),
            (_("&Redo") + "\tCtrl+Y", _("Redo the last action"), frame.OnRedo),
            (),
            (_("&Cut") + "\tCtrl+X", _("Cut the selection and put it on the clipboard"), frame.OnCut),
            (_("&Copy") + "\tCtrl+C", _("Copy the selection and put it on the clipboard"), frame.OnCopy),
            (_("&Paste") + "\tCtrl+V", _("Paste clipboard contents"), frame.OnPaste),
            (_("&Delete"), _("Delete the selection"), frame.OnDelete),
            (),
            (_("&Insert musical symbol"), [
                (_('Note ornaments'), frame.popup_ornaments),
                (_('Directions'), frame.popup_directions), # 1.3.6.1 [SS] 2015-01-22
                (_('Dynamics'), frame.popup_dynamics)]),
            (),
            (_("&Transpose"), transpose_menu),
            (_("&Change note length"), [
                (_('Double note lengths') + '\tCtrl+Shift++', '', frame.exporter.OnDoubleL),
                (_('Halve note lengths') + '\tCtrl+Shift+-', '', frame.exporter.OnHalveL)]),
            (_("A&lign bars") + "\tCtrl+Shift+A", '', frame.exporter.OnAlignBars),
            (),
            (_("&Find...") + "\tCtrl+F", '', frame.find_replace.OnFind),
            (_("Find in Files") + '\tCtrl+Shift+F', '', frame.OnSearchDirectories, disable_in_exclusive), # 1.3.6 [SS] 2014-11-21
            (_("Find &Next") + "\t"+("F3" if wx.Platform != '__WXMAC__' else "Ctrl+G"), '', frame.find_replace.OnFindNext),
            (_("&Replace...") + "\t"+("Ctrl+H" if wx.Platform != "__WXMAC__" else "Alt+Ctrl+F"), '', frame.find_replace.OnReplace),
            (),
            (_("&Select all") + "\tCtrl+A", '', frame.OnSelectAll)]),
        (_("&Settings") , [
            (_("&ABC settings") + '...', "", frame.OnAbcSettings),
            (_("&Midi device settings") + "...", "", frame.OnMidiSettings),
            (_("ABC &typing assistance"), setup_typing_assistance_menu(frame)),
            (),
            (_('&Clear cache') + '...', '', frame.OnClearCache), #1.3.6.1 [SS] 2015-1-10 do not use 5003 (on Linux it will add Ctr-S shortcut)
            (_('Cold &restart'), '', frame.OnColdRestart)]), # 1.3.6.1 [SS] 2014-12-28
        (_("&Tools")    , [
            (_('Generate &incipits file...'), '', frame.tune_list_controller.OnGenerateIncipits),
            (_('&View incipits...'), '', frame.tune_list_controller.OnViewIncipits),
            (),
            (_('&Renumber X: fields...'), '', frame.tune_list_controller.OnRenumberTunes),
            (_('&Sort tunes...'), '', frame.tune_list_controller.OnSortTunes)]),
        (_("&View")     , view_menu),
        (_("&Internals"), [ #p09 [SS] 2014-10-22
            (_("Messages"), _("Show warnings and errors"), frame.OnShowMessages),
            (_("Input processed tune"), '', frame.OnShowAbcTune),
            (_("List of Tunes"), '', frame.OnShowTunesList),
            (_("Output midi file"), '', frame.OnShowMidiFile),
            (_("Show settings status"), '', frame.OnShowSettings)]),
        (_("&Help")     , [
            (_("&Show fields and commands reference"), '', frame.OnViewFieldReference),
            (),
            (_("&EasyABC Help"), _("Link to EasyABC Website"), frame.OnEasyABCHelp),
            (_("&ABC Standard Version 2.1"), _("Link to the ABC Standard version 2.1"), frame.OnABCStandard),
            (_("&Learn ABC"), _("Link to the ABC notation website"), frame.OnABCLearn),
            (_("&Abcm2ps help"), _("Link to the Abcm2ps website"), frame.OnAbcm2psHelp),
            (_("&Abc2midi help"), _("Link to the Abc2midi website"), frame.OnAbc2midiHelp),
            (_("ABC &Quick Reference Card"), _("Link to a PDF with the most common ABC commands"), frame.OnAbcCheatSheet),
            (),
            (_("&Check for update..."), _("Link to EasyABC download page"), frame.OnCheckLastestVersion),
            (),
            (wx.ID_ABOUT, _("About EasyABC") + "...", '', frame.OnAbout)
        ]),
    ], parent=frame)

    frame.SetMenuBar(menuBar)

    frame.Bind(wx.EVT_FIND, frame.find_replace.OnFindNext)
    frame.Bind(wx.EVT_FIND_NEXT, frame.find_replace.OnFindNext)
    frame.Bind(wx.EVT_FIND_REPLACE, frame.find_replace.OnFindReplace)
    frame.Bind(wx.EVT_FIND_REPLACE_ALL, frame.find_replace.OnFindReplaceAll)
    frame.Bind(wx.EVT_FIND_CLOSE, frame.find_replace.OnFindClose)


def setup_toolbar(frame):
    frame.toolbar = aui.AuiToolBar(frame, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, style=aui.AUI_TB_NO_AUTORESIZE)#, agwStyle=aui.AUI_TB_DEFAULT_STYLE | aui.AUI_TB_OVERFLOW)
    try:
        frame.toolbar.SetAGWWindowStyleFlag(aui.AUI_TB_PLAIN_BACKGROUND)
    except:
        pass
    frame.id_play = 3000
    frame.id_stop = 3001
    frame.id_record = 3002
    frame.id_refresh = 3003
    frame.id_dynamics = 3004
    frame.id_directions = 3005
    frame.id_ornamentations = 3006
    frame.id_add_tune = 3007
    frame.id_abc_assist = 3008

    frame.bpm_menu = bpm_menu = create_menu([], parent=frame)
    for i, bpm in enumerate([30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140]):
        append_menu_item(bpm_menu, str(bpm), '', frame.playback.OnRecordBpmSelected, kind=wx.ITEM_RADIO)

    frame.metre_menu = metre_menu = create_menu([], parent=frame)
    for i, metre in enumerate(['2/4', '3/4', '4/4', '5/4']):
        append_menu_item(metre_menu, metre, '', frame.playback.OnRecordMetreSelected, kind=wx.ITEM_RADIO)

    frame.record_popup = record_popup = create_menu([], parent=frame)
    append_submenu(record_popup, _('Beats per minute'), bpm_menu)
    append_submenu(record_popup, _('Metre'), metre_menu)

    button_style = platebtn.PB_STYLE_DEFAULT | platebtn.PB_STYLE_NOBG
    image_path = frame.get_image_path()
    frame.play_bitmap = wx.Image(os.path.join(image_path, 'toolbar_play.png')).ConvertToBitmap()
    frame.pause_bitmap = wx.Image(os.path.join(image_path, 'toolbar_pause.png')).ConvertToBitmap()
    frame.play_button = play = platebtn.PlateButton(frame.toolbar, frame.id_play, "", frame.play_bitmap, style=button_style)
    frame.stop_button = stop = platebtn.PlateButton(frame.toolbar, frame.id_stop, "", wx.Image(os.path.join(image_path, 'toolbar_stop.png')).ConvertToBitmap(), style=button_style)
    frame.record_btn = record = platebtn.PlateButton(frame.toolbar, frame.id_record, "", wx.Image(os.path.join(image_path, 'toolbar_record.png')).ConvertToBitmap(), style=button_style)

    play.SetHelpText('Play (F6)')
    record.SetMenu(record_popup)
    frame.toolbar.AddControl(play)
    frame.toolbar.AddControl(stop)
    frame.toolbar.AddControl(record)
    frame.toolbar.AddSeparator()

    # 1.3.6.3 [JWdJ] 2015-04-26 turned off abc assist for it is not finished yet
    abc_assist = platebtn.PlateButton(frame.toolbar, frame.id_abc_assist, "", wx.Image(os.path.join(image_path, 'bulb.png')).ConvertToBitmap(), style=button_style)
    abc_assist.SetHelpText(_('ABC assist'))
    abc_assist.SetToolTip(wx.ToolTip(_('ABC assist'))) # 1.3.7.0 [JWdJ] 2015-12
    frame.toolbar.AddControl(abc_assist, label=_('ABC assist'))
    frame.Bind(wx.EVT_BUTTON, frame.OnToolAbcAssist, abc_assist) # 1.3.6.2 [JWdJ] 2015-03

    # ornamentations = frame.toolbar.AddSimpleTool(frame.id_ornamentations, "", wx.Image(os.path.join(image_path, 'toolbar_ornamentations.png')).ConvertToBitmap(), _('Note ornaments'))
    # dynamics = frame.toolbar.AddSimpleTool(frame.id_dynamics, "", wx.Image(os.path.join(image_path, 'toolbar_dynamics.png')).ConvertToBitmap(), _('Dynamics'))
    # directions = frame.toolbar.AddSimpleTool(frame.id_directions, "", wx.Image(os.path.join(image_path, 'toolbar_directions.png')).ConvertToBitmap(), _('Directions'))

    # frame.Bind(wx.EVT_TOOL, frame.OnToolDynamics, dynamics)
    # frame.Bind(wx.EVT_TOOL, frame.OnToolOrnamentation, ornamentations)
    # frame.Bind(wx.EVT_TOOL, frame.OnToolDirections, directions)

    frame.toolbar.AddSeparator()

    frame.zoom_slider = add_slider_to_toolbar(frame, _('Zoom'), False, value=1000, minValue=500, maxValue=3000, size=(130, -1))

    #wx_slider_set_tick_freq(frame.zoom_slider, 10)
    frame.Bind(wx.EVT_SLIDER, frame.score_view.OnZoomSlider, frame.zoom_slider)
    frame.zoom_slider.Bind(wx.EVT_LEFT_DOWN, frame.score_view.OnZoomSliderClick)

    # 1.3.6.2 [JWdJ] 2015-02-15 text 'Page' was drawn multiple times. Replaced StaticLabel with StaticText
    frame.cur_page_combo = add_combobox_to_toolbar(frame, _('Page'), choices=[' 1 / 1 '], style=wx.CB_DROPDOWN | wx.CB_READONLY)
    if frame.cur_page_combo.GetCount() > 0:  #EPO
        frame.cur_page_combo.Select(0)
    frame.Bind(wx.EVT_COMBOBOX, frame.score_view.OnPageSelected, frame.cur_page_combo)
    # 1.3.6.3 [SS] 2015-05-03
    frame.bpm_slider = add_slider_to_toolbar(frame, _('Tempo'), False, value=0, minValue=-100, maxValue=100, size=(130, -1))
    if wx.Platform == "__WXMSW__":
        frame.bpm_slider.SetTick(0)  # place a tick in the middle for neutral tempo
    frame.progress_slider = add_slider_to_toolbar(frame, _('Play position'), False, value=0, minValue=0, maxValue=100, size=(130, -1))

    frame.loop_check = add_checkbox_to_toolbar(frame, _('Loop'))
    frame.loop_check.Bind(wx.EVT_CHECKBOX, frame.playback.OnChangeLoopPlayback)

    frame.follow_score_check = add_checkbox_to_toolbar(frame, _('Follow score'))
    frame.follow_score_check.Bind(wx.EVT_CHECKBOX, frame.playback.OnChangeFollowScore)

    frame.timing_slider = add_slider_to_toolbar(frame, '', False, value=0, minValue=-1000, maxValue=1000, size=(130, -1))
    frame.timing_slider.Bind(wx.EVT_SLIDER, frame.playback.OnChangeTiming)
    frame.timing_slider.Bind(wx.EVT_LEFT_DOWN, frame.playback.OnTimingSliderClick)

    frame.Bind(wx.EVT_SLIDER, frame.playback.OnSeek, frame.progress_slider)
    frame.Bind(wx.EVT_SLIDER, frame.playback.OnBpmSlider, frame.bpm_slider)
    frame.bpm_slider.Bind(wx.EVT_LEFT_DOWN, frame.playback.OnBpmSliderClick)

    play.Bind(wx.EVT_LEFT_DOWN, frame.playback.OnToolPlay)
    play.Bind(wx.EVT_LEFT_DCLICK, frame.playback.OnToolPlayLoop)
    frame.Bind(wx.EVT_BUTTON, frame.playback.OnToolStop, stop)
    frame.Bind(wx.EVT_BUTTON, frame.playback.OnToolRecord, record)

    frame.popup_upload = create_upload_context_menu(frame)

    # 1.3.6.3 [JWDJ] fixes toolbar repaint bug
    frame.playback.flip_tempobox(False)
    frame.cur_page_combo.Parent.Show(False)

    frame.manager.AddPane(frame.toolbar, aui.AuiPaneInfo().
                        Name("tb2").Caption("Toolbar2").
                        ToolbarPane().Top().Floatable(True).Dockable(False))


def create_symbols_popup_menu(frame, symbols):
    menu = create_menu([], parent=frame)
    image_path = frame.get_image_path()
    for symbol in symbols:
        if symbol == '-':
            menu.AppendSeparator()
        else:
            img_file = os.path.join(image_path, symbol + '.png')
            description = ('!%s!' % symbol).replace('!pralltriller!', 'P').replace('!accent!', '!>!').replace('!staccato!', '.').replace('!u!', 'u').replace('!v!', 'v').replace('!repeat_left!', '|:').replace('!repeat_right!', ':|').replace('!repeat_both!', '::').replace('!barline!', ' | ').replace('!repeat1!', '|1 ').replace('!repeat2!', ':|2 ')
            image = wx.Image(img_file)
            append_menu_item(menu, ' ', description, frame.typing_assistant.OnInsertSymbol, bitmap=image.ConvertToBitmap())
    return menu


def create_upload_context_menu(frame):
    add_to_multi = lambda menu_item: add_to_multi_list(frame, menu_item)
    menu = create_menu([
        (_('Move up'), '', frame.tune_list_controller.OnMoveTuneUp),
        (_('Move down'), '', frame.tune_list_controller.OnMoveTuneDown),
        (),
        (_('Copy'), '', frame.exporter.OnExportToClipboard),
        (_('Export to &MIDI...'), '', frame.exporter.OnExportMidi),
        (_('Export to &PDF...'), '', frame.exporter.OnExportPDF),
        (_('Export to &one PDF...'), '', frame.exporter.OnExportSelectedToSinglePDF, add_to_multi),
        (_('Export to &SVG...'), '', frame.exporter.OnExportSVG),
        (_('Export to &HTML...'), '', frame.exporter.OnExportHTML),
        (_('Export to HTML (&interactive)...'), '', frame.exporter.OnExportInteractiveHTML),
        (_('Export to Music&XML...'), '', frame.exporter.OnExportMusicXML),
        (_('Export to &ABC...'), '', frame.exporter.OnExportToABC),
        (_('Export to &Wave...'), '', frame.exporter.OnExportToWave),
        (_('Export to &MP3...'), '', frame.exporter.OnExportToMP3),
        (_('Export to &AAC...'), '', frame.exporter.OnExportToAAC)
    ], parent=frame)

    # global current_locale
    # if current_locale.GetLanguageName(wx.LANGUAGE_DEFAULT) == 'Swedish':
    #     id = wx.NewId()
    #     item = wx.MenuItem(menu, id, _('Upload tune to FolkWiki'))
    #     menu.AppendItem(item)
    #     menu.AppendSeparator()
    #     frame.Bind(wx.EVT_MENU, frame.OnUploadTune, id=id)

    # if current_locale.GetLanguageName(wx.LANGUAGE_DEFAULT) == 'Danish':
    #     id = wx.NewId()
    #     item = wx.MenuItem(menu, id, _('Upload tune to Spillemandsportalen'))
    #     menu.AppendItem(item)
    #     menu.AppendSeparator()
    #     frame.Bind(wx.EVT_MENU, frame.OnUploadTune, id=id)
    #     item.Enable(False)  # disabled for now

    return menu


def add_to_multi_list(frame, menu_item):
    frame.tune_list_controller.multi_tunes_menu_items += [menu_item]


def setup_typing_assistance_menu(frame):
    menu = frame.mnu_TA = create_menu([], parent=frame)
    frame.mni_TA_active = append_menu_item(menu, _("&Active") + '\tCtrl+T', "", lambda evt: GrayUngray(frame, evt), kind=wx.ITEM_CHECK)
    menu.AppendSeparator()
    frame.mni_TA_auto_case = append_menu_item(menu, _("Automatic uppercase/lowercase"), "", None, kind=wx.ITEM_CHECK)
    frame.mni_TA_do_re_mi = append_menu_item(menu, _("&Do-re-mi mode"), "", frame.typing_assistant.OnDoReMiModeChange, kind=wx.ITEM_CHECK)
    frame.mni_TA_add_note_durations = append_menu_item(menu, _("Add note &durations"), "", None, kind=wx.ITEM_CHECK)

    add_bar_menu = create_menu([], parent=frame)
    frame.mni_TA_add_bar_disabled = append_menu_item(add_bar_menu, _('Disabled'), "", None, kind=wx.ITEM_RADIO)
    frame.mni_TA_add_bar = append_menu_item(add_bar_menu, _('Using spacebar'), "", None, kind=wx.ITEM_RADIO)
    frame.mni_TA_add_bar_auto = append_menu_item(add_bar_menu, _('Automatic'), "", None, kind=wx.ITEM_RADIO)
    append_submenu(menu, _('Add &bar'), add_bar_menu)

    frame.mni_TA_add_right = append_menu_item(menu, _('Add &matching right symbol: ), ], } and "'), "", None, kind=wx.ITEM_CHECK)
    return menu


def add_slider_to_toolbar(frame, label_text, show_value, *args, **kwargs):
    panel = wx.Panel(frame.toolbar, -1)
    controls = [wx.Slider(panel, wx.ID_ANY, *args, **kwargs)]
    if show_value:
        controls.append(wx.StaticText(panel, wx.ID_ANY, str(kwargs['value'])))
    add_label_and_controls_to_panel(frame, panel, label_text, controls)
    frame.toolbar.AddControl(panel)
    if len(controls) == 1:
        return controls[0]
    else:
        return tuple(controls)


def add_combobox_to_toolbar(frame, label_text, *args, **kwargs):
    panel = wx.Panel(frame.toolbar, -1)
    control = wx.ComboBox(panel, wx.ID_ANY, *args, **kwargs)
    add_label_and_controls_to_panel(frame, panel, label_text, [control])
    frame.toolbar.AddControl(panel)
    return control


def add_label_and_controls_to_panel(frame, panel, label_text, controls):
    box = wx.BoxSizer(wx.HORIZONTAL)
    if label_text:
        box.Add(wx.StaticText(panel, wx.ID_ANY, u'{0}: '.format(label_text)), flag=wx.ALIGN_CENTER_VERTICAL)
    for control in controls:
        box.Add(control, flag=wx.ALIGN_CENTER_VERTICAL)
    box.AddSpacer(20)
    panel.SetSizer(box)
    panel.SetAutoLayout(True)


def add_checkbox_to_toolbar(frame, *args, **kwargs):
    control = wx.CheckBox(frame.toolbar, wx.ID_ANY, *args, **kwargs)
    frame.toolbar.AddControl(control)
    return control


def update_recent_files_menu(frame):
    if frame.exclusive_file_mode:
        return
    recent_files = frame.settings.get('recentfiles', '').split('|')
    while frame.recent_menu.MenuItemCount > 0:
        delete_menuitem(frame.recent_menu, frame.recent_menu.FindItemByPosition(0))

    if len(recent_files) > 0:
        mru_index = 0
        recent_files_menu_id = 1100
        for path in recent_files:
            if path and os.path.exists(path):
                append_menu_item(frame.recent_menu, u'&{0}: {1}'.format(mru_index, path), path, lambda evt: on_recent_file(frame, evt), id=recent_files_menu_id)
                recent_files_menu_id += 1
                mru_index += 1


def on_recent_file(frame, event):
    menu = event.EventObject
    menu_item = menu.FindItemById(event.Id)
    path = menu_item.Help # 1.3.7.1 [JWDJ] sometimes wrong recent file was opened
    if not frame.editor.GetModify() and not frame.document.current_file:  # if a new unmodified document
        frame.document.load(path)
    else:
        new_frame = frame.document.OnNew()
        new_frame.document.load(path)


def show_toolbar_panel(frame, panel, visible):
    panel.Show(visible)


def disable_in_exclusive_mode(frame, menu_item):
    if frame.exclusive_file_mode:
        menu_item.Enable(False)


def GrayUngray(frame, evt=None):
    editMenu = frame.GetMenuBar().GetMenu(1)
    undo, redo, _, cut, copy, paste, delete, _, insert_symbol, _, transpose, note_length, align_bars, _, find, _, findnext, replace, _, selectall = editMenu.GetMenuItems()
    undo.Enable(frame.editor.CanUndo())
    redo.Enable(frame.editor.CanRedo())

    for mni in (frame.mni_TA_auto_case, frame.mni_TA_do_re_mi, frame.mni_TA_add_note_durations, frame.mni_TA_add_right, frame.mni_TA_add_bar_disabled, frame.mni_TA_add_bar, frame.mni_TA_add_bar_auto):
        mni.Enable(frame.mni_TA_active.IsChecked())
