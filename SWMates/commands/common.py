"""Helpers shared by the add-in commands."""

import os
import traceback

import adsk.core
import adsk.fusion

# Own "SW MATES" panel on every Assemble/Assembly toolbar tab (new Fusion UI), or on
# the Solid tab with the classic UI. Tabs are searched across all workspaces because
# the new assembly documents use their own toolbar (ASSEMBLY / MANAGE / UTILITIES).
OWN_PANEL_PREFIX = 'SWMatesPanel_'
OWN_PANEL_NAME = 'SW MATES'
ASSEMBLE_TAB_HINTS = ('assem',)
FALLBACK_TAB_ID = 'SolidTab'
# The buttons are also added to every UTILITIES > ADD-INS panel.
ADDINS_PANEL_HINT = 'addins'
RESOURCES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'resources')

# Fusion only keeps weak references to event handlers: keep them alive here.
handlers = []


def app():
    return adsk.core.Application.get()


def ui():
    return app().userInterface


def design():
    return adsk.fusion.Design.cast(app().activeProduct)


def show_error(prefix='SW Mates'):
    ui().messageBox('{}\n\n{}'.format(prefix, traceback.format_exc()))


def _items(collection):
    return [collection.item(i) for i in range(collection.count)]


def _assemble_tabs():
    tabs = [t for t in _items(ui().allToolbarTabs)
            if any(h in t.id.lower() or h in t.name.lower() for h in ASSEMBLE_TAB_HINTS)]
    if not tabs:
        fallback = ui().allToolbarTabs.itemById(FALLBACK_TAB_ID)
        if fallback is not None:
            tabs = [fallback]
    return tabs


def _own_panels(create):
    panels = []
    for tab in _assemble_tabs():
        pid = OWN_PANEL_PREFIX + tab.id
        panel = tab.toolbarPanels.itemById(pid)
        if panel is None and create:
            panel = tab.toolbarPanels.add(pid, OWN_PANEL_NAME, '', False)
        if panel is not None:
            panels.append(panel)
    return panels


def _addins_panels():
    return [p for p in _items(ui().allToolbarPanels)
            if ADDINS_PANEL_HINT in p.id.lower() and not p.id.startswith(OWN_PANEL_PREFIX)]


def target_panels(create=False):
    """Panels holding the add-in buttons: own SW MATES panels + ADD-INS panels."""
    return _own_panels(create) + _addins_panels()


def add_command(cmd_id, name, tooltip, icon_folder, created_handler, promote=False):
    defs = ui().commandDefinitions
    cmd_def = defs.itemById(cmd_id)
    if cmd_def is None:
        cmd_def = defs.addButtonDefinition(cmd_id, name, tooltip, os.path.join(RESOURCES, icon_folder))
    cmd_def.commandCreated.add(created_handler)
    handlers.append(created_handler)

    for panel in target_panels(create=True):
        if panel.controls.itemById(cmd_id) is None:
            control = panel.controls.addCommand(cmd_def)
            if panel.id.startswith(OWN_PANEL_PREFIX):
                control.isPromoted = promote
                control.isPromotedByDefault = promote
    return cmd_def


def remove_command(cmd_id):
    for panel in target_panels():
        control = panel.controls.itemById(cmd_id)
        if control is not None:
            control.deleteMe()
    cmd_def = ui().commandDefinitions.itemById(cmd_id)
    if cmd_def is not None:
        cmd_def.deleteMe()


def remove_panel():
    for panel in _own_panels(create=False):
        if panel.controls.count == 0:
            panel.deleteMe()


def placement_report():
    """Where the buttons ended up, plus all toolbar tabs (for troubleshooting)."""
    lines = ['SW MATES panel: ' + (', '.join('tab "{}" ({})'.format(t.name, t.id) for t in _assemble_tabs())
                                   or 'không tìm thấy tab Assembly')]
    lines.append('ADD-INS panels: ' + ', '.join(p.id for p in _addins_panels()))
    lines.append('Tất cả toolbar tabs: ' + ', '.join('{}={}'.format(t.id, t.name)
                                                     for t in _items(ui().allToolbarTabs)))
    return '\n'.join(lines)


def log(message):
    try:
        app().log(message)
    except Exception:
        pass   # older Fusion versions have no Application.log


def connect(event, handler):
    event.add(handler)
    handlers.append(handler)


def length_text(value_cm):
    d = design()
    if d is None:
        return '{:.3f} cm'.format(value_cm)
    um = d.unitsManager
    return um.formatInternalValue(value_cm, um.defaultLengthUnits, True)
