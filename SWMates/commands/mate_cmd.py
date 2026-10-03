"""The "Mate" command: a SolidWorks-like Mate PropertyManager for Fusion.

Pick two entities on two different components (the first one moves, as in
SolidWorks), choose a standard mate and confirm. Successive mates between the
same two components are merged into a single Fusion joint.
"""

import adsk.core
import adsk.fusion

from ..bridge import features, joints
from ..core import mates as m
from . import common

CMD_ID = 'SWMates_Mate'
CMD_NAME = 'Mate (SolidWorks)'
CMD_TOOLTIP = ('Lắp ghép kiểu SolidWorks: chọn 2 đối tượng trên 2 component '
               '(component chứa đối tượng thứ nhất sẽ di chuyển), chọn loại mate '
               '(Coincident, Concentric, Distance, Angle, ...). Các mate giữa cùng '
               'một cặp component được gộp thành một Fusion joint.')
RESTART_EVENT = 'SWMates_RestartMate'

ALIGN_ORDER = [m.ALIGN_AUTO, m.ALIGNED, m.ANTI_ALIGNED]

_state = {'ok': False, 'warnings': [], 'keep': False, 'sel': None}
_restart_handler = None


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def _create_inputs(inputs):
    sel = inputs.addSelectionInput('entities', 'Đối tượng mate',
                                   'Chọn 2 đối tượng (mặt, cạnh, điểm, joint origin)')
    sel.selectionFilters = features.SELECTION_FILTERS
    sel.setSelectionLimits(2, 2)
    _state['sel'] = sel

    types = inputs.addDropDownCommandInput('mateType', 'Loại mate',
                                           adsk.core.DropDownStyles.TextListDropDownStyle)
    for i, t in enumerate(m.MATE_TYPES):
        types.listItems.add(m.MATE_LABELS[t], i == 0, '')

    align = inputs.addDropDownCommandInput('alignment', 'Hướng (alignment)',
                                           adsk.core.DropDownStyles.TextListDropDownStyle)
    for i, a in enumerate(ALIGN_ORDER):
        align.listItems.add(m.ALIGN_LABELS[a], i == 0, '')

    units = common.design().unitsManager.defaultLengthUnits
    inputs.addValueInput('distance', 'Khoảng cách', units, adsk.core.ValueInput.createByReal(1.0))
    inputs.addValueInput('angle', 'Góc', 'deg', adsk.core.ValueInput.createByString('90 deg'))
    inputs.addBoolValueInput('flipDim', 'Đảo kích thước (Flip dimension)', True, '', False)
    inputs.addBoolValueInput('lockRot', 'Khóa xoay (Lock rotation)', True, '', False)
    inputs.addBoolValueInput('keep', 'Giữ hộp thoại (pushpin)', True, '', _state['keep'])
    status = inputs.addTextBoxCommandInput('status', '', '', 4, True)
    status.isFullWidth = True


def _selected_index(dropdown):
    item = dropdown.selectedItem
    return item.index if item is not None else 0


def _options(inputs):
    mate_type = m.MATE_TYPES[_selected_index(inputs.itemById('mateType'))]
    return m.MateOptions(
        mate_type=mate_type,
        alignment=ALIGN_ORDER[_selected_index(inputs.itemById('alignment'))],
        distance=inputs.itemById('distance').value,
        angle=inputs.itemById('angle').value,
        flip_dimension=inputs.itemById('flipDim').value,
        lock_rotation=inputs.itemById('lockRot').value,
    )


def _entities(inputs):
    sel = inputs.itemById('entities')
    if sel.selectionCount != 2:
        return None
    return sel.selection(0).entity, sel.selection(1).entity


def _select_item(dropdown, index):
    dropdown.listItems.item(index).isSelected = True


def _update_visibility(inputs):
    t = m.MATE_TYPES[_selected_index(inputs.itemById('mateType'))]
    inputs.itemById('distance').isVisible = t == m.DISTANCE
    inputs.itemById('angle').isVisible = t == m.ANGLE
    inputs.itemById('flipDim').isVisible = t in (m.DISTANCE, m.ANGLE, m.PERPENDICULAR)
    inputs.itemById('lockRot').isVisible = t == m.CONCENTRIC
    inputs.itemById('alignment').isVisible = t not in (m.LOCK, m.PERPENDICULAR)


def _suggest(inputs):
    pair = _entities(inputs)
    if pair is None:
        return
    try:
        k1 = features.classify(pair[0]).kind
        k2 = features.classify(pair[1]).kind
    except m.MateError:
        return
    _select_item(inputs.itemById('mateType'), m.MATE_TYPES.index(m.suggest_mate(k1, k2)))
    _select_item(inputs.itemById('alignment'), 0)


def _refresh_status(inputs):
    status = inputs.itemById('status')
    _state['ok'] = False
    pair = _entities(inputs)
    if pair is None:
        status.formattedText = ('Chọn đối tượng thứ nhất trên component <b>di chuyển</b>, '
                                'sau đó đối tượng thứ hai trên component cố định.')
        return
    try:
        analysis = joints.analyze(common.design(), pair[0], pair[1], _options(inputs))
    except m.MateError as e:
        status.formattedText = '<b>Không tạo được mate:</b> {}'.format(e)
        return
    _state['ok'] = True
    lines = ['Mates: <b>{}</b>'.format(m.summarize(analysis.constraints)),
             'Fusion joint: <b>{}</b>'.format(analysis.plan.describe())]
    if len(analysis.records) > 1:
        lines.append('(Gộp với {} mate có sẵn giữa hai component này)'.format(len(analysis.records) - 1))
    status.formattedText = '<br>'.join(lines)


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------

class _CreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            if common.design() is None:
                common.ui().messageBox('Hãy mở một thiết kế (Design) trước.')
                return
            cmd = args.command
            cmd.okButtonText = 'Mate'
            _state.update(ok=False, warnings=[])
            _create_inputs(cmd.commandInputs)
            _update_visibility(cmd.commandInputs)
            _refresh_status(cmd.commandInputs)
            common.connect(cmd.inputChanged, _InputChangedHandler())
            common.connect(cmd.validateInputs, _ValidateHandler())
            common.connect(cmd.executePreview, _PreviewHandler())
            common.connect(cmd.execute, _ExecuteHandler())
            common.connect(cmd.preSelect, _PreSelectHandler())
            common.connect(cmd.destroy, _DestroyHandler())
        except Exception:
            common.show_error()


class _InputChangedHandler(adsk.core.InputChangedEventHandler):
    def notify(self, args):
        try:
            inputs = args.inputs
            changed = args.input
            if changed.id == 'entities':
                _suggest(inputs)
            if changed.id == 'keep':
                _state['keep'] = changed.value
            _update_visibility(inputs)
            _refresh_status(inputs)
        except Exception:
            common.show_error()


class _ValidateHandler(adsk.core.ValidateInputsEventHandler):
    def notify(self, args):
        args.areInputsValid = _state['ok'] and _entities(args.inputs) is not None


def _run(inputs):
    pair = _entities(inputs)
    result = joints.apply_mate(common.design(), pair[0], pair[1], _options(inputs))
    _state['warnings'] = result.warnings
    return result


class _PreviewHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        if not _state['ok']:
            return
        try:
            _run(args.command.commandInputs)
            # Keep the preview as the final result: OK will not re-run execute.
            args.isValidResult = True
        except m.MateError:
            pass   # the status box already explains why
        except Exception:
            common.show_error()


class _ExecuteHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        try:
            _run(args.command.commandInputs)
        except m.MateError as e:
            args.executeFailed = True
            args.executeFailedMessage = str(e)
        except Exception:
            args.executeFailed = True
            common.show_error()


class _PreSelectHandler(adsk.core.SelectionEventHandler):
    """Like SolidWorks: the second entity must be on another component."""

    def notify(self, args):
        try:
            entity = args.selection.entity
            occ = features.occurrence_of(entity)
            if occ is None:
                args.isSelectable = False
                return
            features.classify(entity)
            sel = _state.get('sel')
            if sel is not None and sel.isValid and sel.selectionCount == 1:
                first = features.occurrence_of(sel.selection(0).entity)
                if first is not None and first.fullPathName == occ.fullPathName:
                    args.isSelectable = False
        except Exception:   # unsupported geometry (MateError) or API failure
            args.isSelectable = False


class _DestroyHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        try:
            completed = args.terminationReason == adsk.core.CommandTerminationReason.CompletedTerminationReason
            if completed and _state['warnings']:
                common.ui().messageBox('\n'.join(_state['warnings']), 'SW Mates')
            if completed and _state['keep']:
                common.app().fireCustomEvent(RESTART_EVENT, '')
        except Exception:
            common.show_error()


class _RestartHandler(adsk.core.CustomEventHandler):
    def notify(self, args):
        try:
            cmd_def = common.ui().commandDefinitions.itemById(CMD_ID)
            if cmd_def is not None:
                cmd_def.execute()
        except Exception:
            common.show_error()


# ---------------------------------------------------------------------------


def start():
    global _restart_handler
    common.add_command(CMD_ID, CMD_NAME, CMD_TOOLTIP, 'mate', _CreatedHandler(), promote=True)
    app = common.app()
    try:
        app.unregisterCustomEvent(RESTART_EVENT)
    except Exception:
        pass
    event = app.registerCustomEvent(RESTART_EVENT)
    _restart_handler = _RestartHandler()
    event.add(_restart_handler)


def stop():
    common.remove_command(CMD_ID)
    try:
        common.app().unregisterCustomEvent(RESTART_EVENT)
    except Exception:
        pass
