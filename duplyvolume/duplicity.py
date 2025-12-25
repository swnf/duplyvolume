import logging
import os
import shutil
from datetime import datetime
import asyncio
from typing import Optional

from .config import config

logger = logging.getLogger(__name__)


async def find_last_backup(volume_name: str):
    # It seems like there is no machine-readable output option (jsonstat is something different)
    process = await asyncio.create_subprocess_exec(
        "duplicity",
        "collection-status",
        *config.duplicity_flags,
        config.duplicity_target(volume_name),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=config.duplicity_env,
    )

    stdout, _ = await process.communicate()
    if process.returncode != 0:
        raise Exception(f"Failed to find last backup for {volume_name}")

    lines = stdout.decode("utf-8").split("\n")
    return max(
        datetime.strptime(line[16:], "%a %b %d %H:%M:%S %Y")
        for line in lines
        if line.startswith("Chain end time: ")
    )


async def do_backup(volume_name: str):
    await run_duplicity(
        "duplicity",
        "backup",
        *(
            []
            if config.full_if_older_than is None
            else ["--full-if-older-than", config.full_if_older_than]
        ),
        "--allow-source-mismatch",  # TODO: is this necessary?
        *config.duplicity_flags,
        f"/source/{volume_name}",
        config.duplicity_target(volume_name),
    )


async def do_remove(
    volume_name: str,
    remove_older_than: Optional[str],
    remove_all_but_n_full: Optional[int],
    remove_all_inc_of_but_n_full: Optional[int],
):
    if remove_all_inc_of_but_n_full is not None:
        flags = [
            "remove-all-inc-of-but-n-full",
            str(remove_all_inc_of_but_n_full),
        ]
    elif remove_all_but_n_full is not None:
        flags = ["remove-all-but-n-full", str(remove_all_but_n_full)]
    elif remove_all_inc_of_but_n_full is not None:
        flags = ["remove-older-than", remove_older_than]
    else:
        raise Exception("do_remove cannot run without any argument")

    await run_duplicity(
        "duplicity",
        *flags,
        "--force",
        *config.duplicity_flags,
        config.duplicity_target(volume_name),
    )


async def do_restore(volume_name: str):
    # Delete content of volume because duplicity will never remove files (even with --force)
    for filename in await asyncio.to_thread(os.listdir, f"/source/{volume_name}"):
        file_path = f"/source/{volume_name}/{filename}"
        if await asyncio.to_thread(os.path.isdir, file_path):
            await asyncio.to_thread(shutil.rmtree, file_path)
        else:
            await asyncio.to_thread(os.unlink, file_path)

    await run_duplicity(
        "duplicity",
        "restore",
        *config.duplicity_flags,
        config.duplicity_target(volume_name),
        f"/source/{volume_name}",
    )


async def run_duplicity(*args: str):
    duplicity_process = await asyncio.create_subprocess_exec(
        args[0],
        *args[1:],
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=config.duplicity_env,
    )
    # Make the type checker happy
    assert duplicity_process.stdout is not None
    assert duplicity_process.stderr is not None
    try:

        async def forward(reader: asyncio.StreamReader, func):
            while True:
                line = await reader.readline()
                if len(line) == 0:
                    break
                func(line.decode("utf-8").strip())

        await asyncio.gather(
            forward(duplicity_process.stdout, logger.info),
            forward(duplicity_process.stderr, logger.error),
        )
    except:
        try:
            # NOTE: This might trigger "Unknown child process pid ..., will report returncode 255" if it is called in the non-error case
            duplicity_process.terminate()
        except ProcessLookupError:
            # Happens if duplicity is not running anymore
            pass
    finally:
        duplicity_status = await duplicity_process.wait()

    # NOTE: It is important that we raise the CancelledError and nothing else if a coroutine is cancelled
    if duplicity_status:
        raise Exception(f"Duplicity failed with code {duplicity_status}")
