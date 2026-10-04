"""SW Mates - SolidWorks-style assembly mates for Autodesk Fusion.

Entry point of the add-in: Fusion calls run() when the add-in starts and
stop() when it is stopped.
"""

from .commands import common, manager_cmd, mate_cmd

_COMMANDS = [mate_cmd, manager_cmd]


def run(context):
    try:
        for cmd in _COMMANDS:
            cmd.start()
        report = common.placement_report()
        common.log('SW Mates: đã nạp.\n' + report)
        if not (isinstance(context, dict) and context.get('IsApplicationStartup')):
            # Started by hand from Scripts and Add-Ins: say where the buttons are.
            common.ui().messageBox('SW Mates đã chạy.\n\n' + report, 'SW Mates')
    except Exception:
        common.show_error('SW Mates: lỗi khi khởi động add-in')


def stop(context):
    try:
        for cmd in _COMMANDS:
            cmd.stop()
        common.remove_panel()
        common.handlers.clear()
    except Exception:
        common.show_error('SW Mates: lỗi khi dừng add-in')
