import logging
import asyncio
from contextlib import contextmanager


async def send_command_to_control(command, interrupt=None, silent=False):
    if not silent:
        print(f"Started command {command}, streaming logs...", flush=True)
    buffer = ""
    # NOTE: Don't use localhost, will be IPv6
    reader, writer = await asyncio.open_connection("127.0.0.1", 6000)

    try:
        writer.write((command + "\n").encode("utf-8"))
        await writer.drain()

        while True:
            try:
                received = await reader.read(1024)
                if len(received) == 0:
                    break
                decoded = received.decode("utf-8")

                if not silent:
                    print(decoded, flush=True, end="")
                buffer += decoded

            except asyncio.CancelledError:
                if interrupt is None:
                    print("Warning: The command is still running", flush=True)
                    raise

                # NOTE: Don't use localhost, will be IPv6
                _, writer2 = await asyncio.open_connection("127.0.0.1", 6000)
                try:
                    writer2.write((interrupt + "\n").encode("utf-8"))
                    await writer2.drain()

                    # Don't break or raise, continue running
                finally:
                    writer2.close()
                    await writer2.wait_closed()

    finally:
        writer.close()
        await writer.wait_closed()

    return buffer


class WriterHandler(logging.StreamHandler):
    def __init__(self, writer):
        super().__init__()
        self.writer = writer

    def emit(self, record):
        self.writer.write((self.format(record) + "\n").encode("utf-8"))


@contextmanager
def stream_logs_to(writer):
    handler = WriterHandler(writer)
    handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    logging.root.addHandler(handler)
    try:
        yield
    finally:
        logging.root.removeHandler(handler)
