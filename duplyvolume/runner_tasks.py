import logging
import aiodocker

from .config import config
from .docker_utils import start_containers, stop_containers
from .duplicity import do_backup, do_remove, do_restore
from .utils import VolumeInfo

logger = logging.getLogger(__name__)


async def backup_stage2(volume_map: dict[str, VolumeInfo]):
    async with aiodocker.Docker() as client:
        logger.info("Backup stage 2 started")
        try:
            for volume_name, volume_info in volume_map.items():
                # Start all containers which have not yet been started again, but exclude containers needed for the next backup
                await start_containers(client, volume_info["used_by_containers"])
                await stop_containers(client, volume_info["used_by_containers"])
                logger.info(f"Backing up volume {volume_name}")
                await do_backup(volume_name)
                remove_older_than = volume_info.get(
                    "remove_older_than", config.remove_older_than
                )
                remove_all_but_n_full = volume_info.get(
                    "remove_all_but_n_full", config.remove_all_but_n_full
                )
                remove_all_inc_of_but_n_full = volume_info.get(
                    "remove_all_inc_of_but_n_full", config.remove_all_inc_of_but_n_full
                )
                if (
                    remove_older_than is not None
                    or remove_all_but_n_full is not None
                    or remove_all_inc_of_but_n_full is not None
                ):
                    logger.info(f"Removing old backups from volume {volume_name}")
                    await do_remove(
                        volume_name,
                        remove_older_than,
                        remove_all_but_n_full,
                        remove_all_inc_of_but_n_full,
                    )
            logger.info("Backup stage 2 done")
        finally:
            await start_containers(client)
            logger.info("All containers are running again")


async def restore_stage2(volume_map: dict[str, list[str]]):
    async with aiodocker.Docker() as client:
        logger.info("Restore stage 2 started")
        try:
            for volume_name, used_by_containers in volume_map.items():
                # Start all containers which have not yet been started again, but exclude containers needed for the next restore
                # TODO: It is problematic if a container is stopped/started multiple times because in-between it the volumes can change
                await start_containers(client, used_by_containers)
                await stop_containers(client, used_by_containers)
                logger.info(f"Restoring volume {volume_name}")
                await do_restore(volume_name)
            logger.info("Restore stage 2 done")
        finally:
            await start_containers(client)
            logger.info("All containers are running again")
