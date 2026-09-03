from __future__ import annotations

import asyncio
import sys

from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

from state import State
from connection_manager import ConnectionManager
from controller import DualSense
from gui import MainWindow
from config import load_user_config


async def async_main(app: QApplication) -> None:

    state = State()
    user_config = load_user_config()
    connection = ConnectionManager(state, user_config)
    controller = DualSense(connection, state)

    controller.start()
    await connection.start()

    window = MainWindow(state, user_config, connection, controller)
    window.show()

    try:
        while state.running:
            await asyncio.sleep(0.1)

    finally:
        state.running = False

        try:
            await connection.stop_motors("TOPSIDE SHUTDOWN")
        except Exception:
            pass

        try:
            await connection.shutdown()
        except Exception:
            pass

        controller.close()


def main() -> None:

    app = QApplication(sys.argv)

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    with loop:
        loop.run_until_complete(async_main(app))


if __name__ == "__main__":
    main()
