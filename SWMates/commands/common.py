"""Helpers shared by the add-in commands."""

import os
import traceback

import adsk.core
import adsk.fusion

WORKSPACE_ID = 'FusionSolidEnvironment'
# Own "SW MATES" panel, placed on the Assemble tab (new Fusion UI) or the Solid tab.
OWN_PANEL_ID = 'SWMatesPanel'
OWN_PANEL_NAME = 'SW MATES'
ASSEMBLE_TAB_HINTS = ('assemble', 'assembly')
FALLBACK_TAB_ID = 'SolidTab'
# Always also listed under UTILITIES > ADD-INS, which exists in every UI layout.
ADDINS_PANEL_ID = 'SolidScriptsAddinsPanel'
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


def _workspace():
    return ui().workspaces.itemById(WORKSPACE_ID)


def _target_tab(ws):
    tabs = ws.toolbarTabs
    for i in range(tabs.count):
        tab = tabs.item(i)
        if any(h in tab.id.lower() for h in ASSEMBLE_TAB_HINTS):
            return tab
    return tabs.itemById(FALLBACK_TAB_ID)


def _own_panel(create):
    ws = _workspace()
    tab = _target_tab(ws) if ws is not None else None
    if tab is None:
        return None
    panel = tab.toolbarPanels.itemById(OWN_PANEL_ID)
    if panel is None and create:
        panel = tab.toolbarPanels.add(OWN_PANEL_ID, OWN_PANEL_NAME, '', False)
    return panel


def target_panels(create=False):
    """Panels holding the add-in buttons: (own panel, Utilities > Add-Ins)."""
    panels = []
    own = _own_panel(create)
    if own is not None:
        panels.append(own)
    ws = _workspace()
    addins = ws.toolbarPanels.itemById(ADDINS_PANEL_ID) if ws is not None else None
    if addins is not None:
        panels.append(addins)
    return panels


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
            if panel.id == OWN_PANEL_ID:
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
    panel = _own_panel(create=False)
    if panel is not None and panel.controls.count == 0:
        panel.deleteMe()


def panel_location():
    """Human readable location of the add-in buttons, for the startup log."""
    own = _own_panel(create=False)
    tab = _target_tab(_workspace()) if own is not None else None
    if tab is not None:
        return 'tab {} > panel {}'.format(tab.name, OWN_PANEL_NAME)
    return 'UTILITIES > ADD-INS'


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
