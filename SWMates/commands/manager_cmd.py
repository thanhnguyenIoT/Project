"""The "Mate Manager" command: list the SolidWorks-style mates stored on joints
and delete individual mates (the joint is rebuilt from the remaining ones),
similar to the Mates folder in the SolidWorks FeatureManager tree."""

import math

import adsk.core
import adsk.fusion

from ..bridge import joints, storage
from ..core import mates as m
from . import common

CMD_ID = 'SWMates_Manager'
CMD_NAME = 'Mate Manager'
CMD_TOOLTIP = 'Xem danh sách mate (kiểu SolidWorks) giữa các component và xóa từng mate.'

ACTIONS = ['Xóa mate đã chọn', 'Xóa toàn bộ nhóm (joint)', 'Tạo lại joint (rebuild)']

_groups = []   # [(joint, records)] snapshot taken when the dialog opens


def _mate_text(index, rec):
    opts = m.MateOptions.from_dict(rec['opts'])
    text = '{}. {}'.format(index + 1, m.MATE_LABELS.get(opts.mate_type, opts.mate_type))
    if opts.mate_type == m.DISTANCE:
        text += ' = ' + common.length_text(opts.distance)
    elif opts.mate_type == m.ANGLE:
        text += ' = {:.2f}°'.format(opts.angle * 180.0 / 3.141592653589793)
    if opts.mate_type not in (m.LOCK, m.PERPENDICULAR):
        text += ' [{}]'.format('Anti-Aligned' if rec['anti'] else 'Aligned')
    return text


def _group_text(records):
    a, b = storage.pair_of(records)
    return '{}  ↔  {}'.format(a, b)


def _fill_mates(inputs):
    mates_dd = inputs.itemById('mate')
    mates_dd.listItems.clear()
    details = inputs.itemById('details')
    gi = inputs.itemById('group').selectedItem
    if gi is None or not _groups:
        details.formattedText = 'Chưa có mate nào được tạo bằng SW Mates trong thiết kế này.'
        return
    joint, records = _groups[gi.index]
    for i, rec in enumerate(records):
        mates_dd.listItems.add(_mate_text(i, rec), i == len(records) - 1, '')
    lines = ['Joint: <b>{}</b>'.format(joint.name)]
    lines += [_mate_text(i, r) for i, r in enumerate(records)]
    details.formattedText = '<br>'.join(lines)


class _CreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            design = common.design()
            if design is None:
                common.ui().messageBox('Hãy mở một thiết kế (Design) trước.')
                return
            _groups[:] = storage.managed_joints(design)
            cmd = args.command
            cmd.okButtonText = 'Thực hiện'
            inputs = cmd.commandInputs
            group = inputs.addDropDownCommandInput('group', 'Cặp component',
                                                   adsk.core.DropDownStyles.TextListDropDownStyle)
            for i, (joint, records) in enumerate(_groups):
                group.listItems.add(_group_text(records), i == 0, '')
            inputs.addDropDownCommandInput('mate', 'Mate', adsk.core.DropDownStyles.TextListDropDownStyle)
            action = inputs.addDropDownCommandInput('action', 'Thao tác',
                                                    adsk.core.DropDownStyles.TextListDropDownStyle)
            for i, a in enumerate(ACTIONS):
                action.listItems.add(a, i == 0, '')
            details = inputs.addTextBoxCommandInput('details', '', '', 6, True)
            details.isFullWidth = True
            _fill_mates(inputs)

            common.connect(cmd.inputChanged, _InputChangedHandler())
            common.connect(cmd.validateInputs, _ValidateHandler())
            common.connect(cmd.execute, _ExecuteHandler())
        except Exception:
            common.show_error()


class _InputChangedHandler(adsk.core.InputChangedEventHandler):
    def notify(self, args):
        try:
            if args.input.id == 'group':
                _fill_mates(args.inputs)
        except Exception:
            common.show_error()


class _ValidateHandler(adsk.core.ValidateInputsEventHandler):
    def notify(self, args):
        args.areInputsValid = bool(_groups) and args.inputs.itemById('group').selectedItem is not None


class _ExecuteHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        try:
            inputs = args.command.commandInputs
            design = common.design()
            joint, records = _groups[inputs.itemById('group').selectedItem.index]
            action = inputs.itemById('action').selectedItem.index
            result = None
            if action == 0:
                mate_item = inputs.itemById('mate').selectedItem
                if mate_item is None:
                    return
                result = joints.remove_mate(design, joint, records, mate_item.index)
            elif action == 1:
                joint.deleteMe()
            else:
                result = joints.build(design, joints.analyze_records(design, records, joint))
            if result is not None and result.warnings:
                common.ui().messageBox('\n'.join(result.warnings), 'SW Mates')
        except m.MateError as e:
            args.executeFailed = True
            args.executeFailedMessage = str(e)
        except Exception:
            args.executeFailed = True
            common.show_error()


def start():
    common.add_command(CMD_ID, CMD_NAME, CMD_TOOLTIP, 'manager', _CreatedHandler())


def stop():
    common.remove_command(CMD_ID)
