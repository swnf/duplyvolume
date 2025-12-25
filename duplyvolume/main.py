import json
import logging
import sys
import argparse
import asyncio
import signal

from .ipc import send_command_to_control
from .control import control
from .runner_tasks import backup_stage2, restore_stage2

logger = logging.getLogger(__name__)


def main():
    # NOTE: Otherwise the process just crashes when docker tries to stop the container
    signal.signal(signal.SIGTERM, signal.default_int_handler)

    logging.basicConfig()
    logging.getLogger(__package__).setLevel(logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument("command", type=str, help="The command to execute")
    parser.add_argument("data", type=json.loads, nargs="?", help=argparse.SUPPRESS)

    # NOTE: Not in async code because parse_args can call sys.exit
    args = parser.parse_args()

    # NOTE: If asyncio.run is interrupted once, it cancels all tasks and waits for them
    try:
        if args.command == "control":
            asyncio.run(control())
        elif args.command == "backup-stage2" and args.data is not None:
            asyncio.run(backup_stage2(args.data))
        elif args.command == "restore-stage2" and args.data is not None:
            asyncio.run(restore_stage2(args.data))
        elif args.command == "backup":
            asyncio.run(send_command_to_control("backup", interrupt="cancel"))
        elif args.command == "restore":
            asyncio.run(send_command_to_control("restore", interrupt="cancel"))
        elif args.command == "healthcheck":
            # TODO: can this happen in the runner?
            result = asyncio.run(send_command_to_control("healthcheck"))
            sys.exit(
                0
                if any(
                    line for line in result.split("\n") if "Healthcheck passed" in line
                )
                else 1
            )
        elif args.command == "cancel":
            asyncio.run(send_command_to_control("cancel"))
        else:
            print(f"Invalid command '{args.command}'")
            sys.exit(1)
    except KeyboardInterrupt:
        pass
