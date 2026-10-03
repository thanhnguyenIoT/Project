"""Helpers shared by the add-in commands."""

import os
import traceback

import adsk.core
import adsk.fusion

WORKSPACE_ID = 'FusionSolidEnvironment'
PANEL_IDS = ['AssemblePanel', 'SolidScriptsAddinsPanel']
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


def find_panel():
    ws = ui().workspaces.itemById(WORKSPACE_ID)
    if ws is None:
        return None
    for pid in PANEL_IDS:
        panel = ws.toolbarPanels.itemById(pid)
        if panel is not None:
            return panel
    return None


def add_command(cmd_id, name, tooltip, icon_folder, created_handler, promote=False):
    defs = ui().commandDefinitions
    cmd_def = defs.itemById(cmd_id)
    if cmd_def is None:
        cmd_def = defs.addButtonDefinition(cmd_id, name, tooltip, os.path.join(RESOURCES, icon_folder))
    cmd_def.commandCreated.add(created_handler)
    handlers.append(created_handler)

    panel = find_panel()
    if panel is not None and panel.controls.itemById(cmd_id) is None:
        control = panel.controls.addCommand(cmd_def)
        control.isPromoted = promote
        control.isPromotedByDefault = promote
    return cmd_def


def remove_command(cmd_id):
    panel = find_panel()
    if panel is not None:
        control = panel.controls.itemById(cmd_id)
        if control is not None:
            control.deleteMe()
    cmd_def = ui().commandDefinitions.itemById(cmd_id)
    if cmd_def is not None:
        cmd_def.deleteMe()


def connect(event, handler):
    event.add(handler)
    handlers.append(handler)


def length_text(value_cm):
    d = design()
    if d is None:
        return '{:.3f} cm'.format(value_cm)
    um = d.unitsManager
    return um.formatInternalValue(value_cm, um.defaultLengthUnits, True)
