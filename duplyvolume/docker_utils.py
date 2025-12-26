import json
import logging
import os
from typing import Optional
import asyncio
import aiodocker
from aiodocker.containers import DockerContainer

from .utils import my_hostname

logger = logging.getLogger(__name__)
restart_queue: list[str] = []


async def stop_containers(client: aiodocker.Docker, containers: list[str]):
    for container_id in containers:
        target_container = await client.containers.get(container_id)
        if target_container["State"]["Status"] == "running":
            logger.info(f"Stopping container {target_container["Name"].lstrip("/")}")
            try:
                await target_container.stop()
                restart_queue.append(container_id)
            except asyncio.CancelledError:
                # NOTE: This is important if our own process terminates during stop (wait for stop or start won't work)
                await target_container.stop()
                # NOTE: It is important that this also happens in the cancel case
                restart_queue.append(container_id)
                raise


async def start_containers(
    client: aiodocker.Docker, exclude_containers: Optional[list[str]] = None
):
    for container_id in list(restart_queue):
        if container_id in ([] if exclude_containers is None else exclude_containers):
            continue
        target_container = await client.containers.get(container_id)
        logger.info(f"Starting container {target_container["Name"].lstrip("/")}")
        try:
            await target_container.start()
            restart_queue.remove(container_id)
        except asyncio.CancelledError:
            await target_container.start()
            restart_queue.remove(container_id)
            raise


async def find_myself(client: aiodocker.Docker) -> DockerContainer:
    for container_id in [
        container.id for container in await client.containers.list(all=True)
    ]:
        # NOTE: containers.list does not return the full config
        container = await client.containers.get(container_id)
        if container["Config"]["Hostname"] == my_hostname:
            return container
    raise Exception("Unable to find current container, aborting backup")


def convert_mount(old_mount: dict) -> dict:
    if old_mount["Type"] == "bind":
        return {
            "Target": old_mount["Destination"],
            "Source": old_mount["Source"],
            "Type": "bind",
            "ReadOnly": not old_mount["RW"],
        }
    elif old_mount["Type"] == "volume":
        return {
            "Target": old_mount["Destination"],
            "Source": old_mount["Name"],
            "Type": "volume",
            "ReadOnly": not old_mount["RW"],
        }
    else:
        raise Exception(f"Unknown mount type {old_mount['Type']}")


async def start_runner(
    mounts: list[dict],
    command: str,
    args: dict,
    myself: DockerContainer,
    client: aiodocker.Docker,
):
    runner_container = await client.containers.run(
        {
            "Cmd": [command, json.dumps(args)],
            "Image": myself["Image"],
            "Env": [f"{key}={value}" for key, value in os.environ.items()],
            "HostConfig": {
                "AutoRemove": True,
                # "Inherit" mounts (also important for secrets)
                # NOTE: The format is incompatible to the one returned by get()
                "Mounts": [
                    *[convert_mount(mount) for mount in myself["Mounts"]],
                    *mounts,
                ],
            },
            "AttachStdin": False,
            "AttachStdout": False,
            "AttachStderr": False,
            "Tty": False,
            "OpenStdin": False,
        }
    )

    runner_status = None

    async def do_wait():
        nonlocal runner_status
        runner_status = (await runner_container.wait())["StatusCode"]

    # If we wait after the log stream is closed, the container might have been already deleted
    wait_task = asyncio.create_task(do_wait())
    try:
        runner_logger = logging.getLogger(__package__).getChild("runner")
        async for line in runner_container.log(stdout=True, stderr=True, follow=True):
            parts = line.rstrip("\n").split(":", 2)
            if len(parts) == 3 and "." in parts[1]:
                levelname, name, message = parts
                _, name_suffix = name.split(".", 2)
                # The name -> level conversion is legacy behavior
                runner_logger.getChild(name_suffix).log(
                    logging.getLevelName(levelname), message
                )
            else:
                runner_logger.error(":".join(parts))
    except asyncio.CancelledError:
        await runner_container.stop()
        # NOTE: The wait_task might be cancelled, we have to wait here again
        await runner_container.wait()
        raise
    finally:
        await wait_task

    if runner_status != 0:
        raise Exception(f"Runner failed with code {runner_status}")
