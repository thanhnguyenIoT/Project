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
        common.log('SW Mates: đã nạp. Nút lệnh nằm ở {} và UTILITIES > ADD-INS.'.format(
            common.panel_location()))
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
