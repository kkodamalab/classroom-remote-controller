import sys
from PySide6.QtWidgets import QApplication
from qasync import QEventLoop
import asyncio
from desktop.ui import Window


def main():
    app = QApplication(sys.argv)
    if '--self-test' in sys.argv:
        # Packaging/import smoke test only: no network or OS input.
        import desktop.transport
        import win32com.client
        import pythoncom
        window = Window()
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
