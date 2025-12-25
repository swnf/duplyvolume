import logging
import os
import re
from datetime import datetime, timedelta
import asyncio
import aiodocker
from typing import Optional
import json

from .metadata import write_metadata, list_volumes_by_metadata, read_metadata
from .config import config
from .docker_utils import find_myself, start_runner
from .duplicity import find_last_backup
from .utils import my_hostname, VolumeInfo

active_task: Optional[asyncio.Task] = None
logger = logging.getLogger(__name__)


async def backup_stage1(task_lock: asyncio.Lock):
    global active_task
    async with task_lock, aiodocker.Docker() as client:
        logger.info("Preparing backup")
        volume_map: dict[str, VolumeInfo] = {}
        stage2_mounts = []
        myself = await find_myself(client)
        for container_id in [
            container.id for container in await client.containers.list(all=True)
        ]:
            # Skip own container
            if container_id == myself.id:
                continue

            # NOTE: containers.list does not return the full config
            # NOTE: Don't continue here on error like in healthcheck. Restore/Backup assumes a stable environment without changes.
            container = await client.containers.get(container_id)
            for mount in container["Mounts"]:
                if (
                    not mount["RW"]
                    or not mount["Type"] == "volume"
                    or (
                        config.ignore_regex is not None
                        and re.match(config.ignore_regex, mount["Name"])
                    )
                ):
                    continue
                volume_name = mount["Name"]
                if volume_name not in volume_map:
                    volume_labels = (
                        await (await client.volumes.get(volume_name)).show()
                    )["Labels"]
                    if volume_labels is None:
                        volume_labels = {}

                    volume_info: VolumeInfo = {"used_by_containers": [container.id]}
                    if "duplyvolume.remove_older_than" in volume_labels:
                        volume_info["remove_older_than"] = volume_labels[
                            "duplyvolume.remove_older_than"
                        ]
                    if "duplyvolume.remove_all_but_n_full" in volume_labels:
                        volume_info["remove_all_but_n_full"] = int(
                            volume_labels["duplyvolume.remove_all_but_n_full"]
                        )
                    if "duplyvolume.remove_all_inc_of_but_n_full" in volume_labels:
                        volume_info["remove_all_inc_of_but_n_full"] = int(
                            volume_labels["duplyvolume.remove_all_inc_of_but_n_full"]
                        )

                    volume_map[volume_name] = volume_info

                    stage2_mounts.append(
                        {
                            # NOTE: While creating a container it is "Target", otherwise "Destination"
                            "Target": f"/source/{volume_name}",
                            "Source": volume_name,
                            "Type": "volume",
                            "ReadOnly": True,
                        }
                    )
                else:
                    volume_map[volume_name]["used_by_containers"].append(container.id)

        if len(stage2_mounts) == 0:
            logger.warning("Nothing found to back up, doing nothing")
            return

        logger.info("Updating volume metadata")
        for volume_name in volume_map.keys():
            volume = await client.volumes.get(volume_name)
            volume_info = await volume.show()
            await write_metadata(
                volume_name,
                # Only store Name/Labels for now, anything else is probably unnecessary and could cause issues
                json.dumps(
                    {k: v for k, v in volume_info.items() if k in {"Name", "Labels"}}
                ),
            )

        logger.info("Starting backup stage 2")
        active_task = asyncio.create_task(
            start_runner(
                stage2_mounts,
                "backup-stage2",
                volume_map,
                myself,
                client,
            )
        )
        try:
            await active_task
        finally:
            active_task = None


async def restore_stage1(task_lock: asyncio.Lock):
    global active_task
    async with task_lock, aiodocker.Docker() as client:
        logger.info("Preparing restore")
        volume_info = []
        for volume_name in await list_volumes_by_metadata():
            volume_info.append((volume_name, await find_last_backup(volume_name)))
        if len(volume_info) == 0:
            logger.warning("No volumes found in target, doing nothing")
            return
        last_backup = max(date for _, date in volume_info)
        volume_map: dict[str, list[str]] = {
            volume_name: []
            for volume_name, date in volume_info
            if date >= last_backup - timedelta(hours=6)
        }
        logger.info(
            f"Restoring volumes {", ".join(volume_map.keys())} ({len(volume_map.keys())}/{len(volume_info)})",
        )
        stage2_mounts = [
            {
                # NOTE: While creating a container it is "Target", otherwise "Destination"
                "Target": f"/source/{volume_name}",
                "Source": volume_name,
                "Type": "volume",
                "ReadOnly": False,
            }
            for volume_name in volume_map.keys()
        ]
        myself = await find_myself(client)
        for container_id in [
            container.id for container in await client.containers.list(all=True)
        ]:
            # Skip own container
            if container_id == myself.id:
                continue

            # NOTE: containers.list does not return the full config
            # NOTE: Don't continue here on error like in healthcheck. Restore/Backup assumes a stable environment without changes.
            container = await client.containers.get(container_id)
            for mount in container["Mounts"]:
                if not mount["Type"] == "volume":
                    continue
                volume_name = mount["Name"]
                if volume_name in volume_map:
                    volume_map[volume_name].append(container.id)

        if len(stage2_mounts) == 0:
            logger.warning("Nothing found to restore, doing nothing")
            return

        logger.info("Creating volumes with correct metadata if necessary")
        existing_volume_names = [
            volume["Name"] for volume in (await client.volumes.list())["Volumes"]
        ]
        for volume_name in volume_map.keys():
            # If volume already exists, skip it
            if volume_name in existing_volume_names:
                continue
            # Otherwise create it. This is only necessary to ensure it has the correct Labels (otherwise docker-compose complains)
            volume_info = json.loads(await read_metadata(volume_name))
            await client.volumes.create(volume_info)

        logger.info("Starting restore stage 2")
        active_task = asyncio.create_task(
            start_runner(
                stage2_mounts,
                "restore-stage2",
                volume_map,
                myself,
                client,
            )
        )
        try:
            await active_task
        finally:
            active_task = None


async def healthcheck(task_lock: asyncio.Lock):
    async with aiodocker.Docker() as client:
        for container_id in [
            container.id for container in await client.containers.list(all=True)
        ]:
            try:
                # NOTE: containers.list does not return the full config
                container = await client.containers.get(container_id)
            except aiodocker.DockerError as e:
                if e.status == 404:
                    # The container was removed since the call to .list()
                    # Continue like it was never there, ignore the exception to avoid scary errors in log
                    continue
                raise
            container_entrypoint = container["Config"]["Entrypoint"]
            container_cmd = container["Config"]["Cmd"]
            container_hostname = container["Config"]["Hostname"]
            container_creation = datetime.fromisoformat(container["Created"][0:26])
            # Has to match entrypoint
            if container_entrypoint == [
                "/sbin/tini",
                "--",
                "/usr/local/bin/duplyvolume",
            ]:
                if container_cmd == ["control"] and container_hostname != my_hostname:
                    raise Exception(
                        "It seems like there is another duplyvolume container running. Don't do that."
                    )
                if container_cmd == ["backup-stage2"] and not task_lock.locked():
                    raise Exception(
                        "It seems like there is a leftover backup container. I won't delete it."
                    )
                if container_cmd == [
                    "backup-stage2"
                ] and datetime.now() - container_creation > timedelta(hours=3):
                    raise Exception("It seems like a backup is stuck.")


async def cancel_backup(task_lock: asyncio.Lock):
    if active_task is not None:
        active_task.cancel()
    async with task_lock:
        logger.info("Runner container stopped")
