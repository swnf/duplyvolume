import socket
from typing import TypedDict, NotRequired


async def close_writer(writer):
    try:
        await writer.drain()
    except ConnectionResetError:
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except ConnectionResetError:
            pass
        except BrokenPipeError:
            pass


my_hostname = socket.gethostname()


class VolumeInfo(TypedDict):
    remove_older_than: NotRequired[str]
    remove_all_but_n_full: NotRequired[int]
    remove_all_inc_of_but_n_full: NotRequired[int]
    used_by_containers: list[str]
