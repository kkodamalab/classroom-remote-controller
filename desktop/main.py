import sys
from PySide6.QtWidgets import QApplication
from qasync import QEventLoop
import asyncio
from desktop.ui import Window
from desktop.version import APP_NAME, VERSION


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(VERSION)
    if '--diagnostics-self-test' in sys.argv:
        # Explicit offline test mode: injected failures, never OS input/network.
        from desktop.portable_diagnostics import run
        index = sys.argv.index('--diagnostics-self-test')
        if index + 1 >= len(sys.argv):
            raise SystemExit('A JSON report path is required')
        window = Window(autostart=False)
        try:
            asyncio.run(run(window, sys.argv[index + 1]))
        except Exception as exc:
            import json
            from pathlib import Path
            from desktop.diagnostics import classify
            code, detail = classify(exc)
            Path(sys.argv[index + 1]).write_text(json.dumps({'status':'failed', 'version':VERSION, 'code':code, 'detail':detail}), encoding='utf-8')
            raise SystemExit(1)
        finally:
            window.transport = window.session = None
            window.close()
        return
    if '--self-test' in sys.argv:
        # Packaging/import smoke test only: no network or OS input.
        import desktop.transport
        import win32com.client
        import pythoncom
        window = Window(autostart=False)
        window.close()
        return
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    window = Window()
    window.show()
    with loop:
        loop.run_forever()


if __name__ == '__main__':
    main()
