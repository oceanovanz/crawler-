import asyncio
import pygame

import gui
from state import State
from controller import DualSense
from connection_manager import ConnectionManager
from config import load_user_config


def create_state() -> State:
    user_config = load_user_config()
    return State(pi_ip=user_config.pi_ip, record_dir=user_config.record_dir)


async def main() -> None:
    pygame.init()
    gui.init()

    state = create_state()
    connection = ConnectionManager(state)
    controller = DualSense(state, connection)

    controller.start()

    await connection.start()

    try:
        await gui.ui(state, controller, connection)

    finally:
        state.running = False

        try:
            await connection.stop_motors("TOPSIDE SHUTDOWN")
        except Exception:
            pass

        await connection.stop()

        controller.close()
        pygame.quit()


def run() -> None:
    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        pass

    finally:
        pygame.quit()


if __name__ == "__main__":
    run()
