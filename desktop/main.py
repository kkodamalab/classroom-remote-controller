import sys
from PySide6.QtWidgets import QApplication
from qasync import QEventLoop
import asyncio
from desktop.ui import Window


def main():
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    window = Window()
    window.show()
    with loop:
        loop.run_forever()


if __name__ == '__main__':
    main()
