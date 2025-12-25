import logging
import asyncio
from functools import partial

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]

from .config import config
from .ipc import send_command_to_control, stream_logs_to
from .control_tasks import (
    backup_stage1,
    cancel_backup,
    healthcheck,
    restore_stage1,
)
from .utils import close_writer

logger = logging.getLogger(__name__)


async def handle_client(task_lock: asyncio.Lock, reader, writer):
    try:
        command = (await reader.readuntil()).decode("utf-8")[0:-1]
        with stream_logs_to(writer):
            if command == "backup":
                logger.info("Backup requested")
                try:
                    await backup_stage1(task_lock)
                    logger.info("Backup done")
                except:
                    logger.exception("Backup failed")
            elif command == "restore":
                logger.info("Restore requested")
                try:
                    await restore_stage1(task_lock)
                    logger.info("Restore done")
                except:
                    logger.exception("Restore failed")
            elif command == "cancel":
                logger.info("Cancellation of current backup requested")
                try:
                    await cancel_backup(task_lock)
                    logger.info("Successfully cancelled")
                except:
                    logger.exception("Cancellation failed")
            elif command == "healthcheck":
                try:
                    await healthcheck(task_lock)
                    logger.info("Healthcheck passed")
                except:
                    logger.exception("Healthcheck failed")
            else:
                logger.error(f"Unkown command {command}")
    except asyncio.IncompleteReadError:
        pass
    except:
        logger.exception("Closing client connection due to an unknown error")
    finally:
        await close_writer(writer)


async def scheduled_backup():
    logger.info("Scheduled backup triggered")
    await send_command_to_control("backup", silent=True)


async def control():
    if config.backup_cron is not None:
        scheduler = AsyncIOScheduler()
        scheduler.start()
        backup_job = scheduler.add_job(
            scheduled_backup, CronTrigger.from_crontab(config.backup_cron)
        )
        logger.info(f"Backup will run at {backup_job.next_run_time}")

    # NOTE: Has to be created inside the running event loop
    task_lock = asyncio.Lock()

    # NOTE: Don't use localhost, will be IPv6
    server = await asyncio.start_server(
        partial(handle_client, task_lock), "127.0.0.1", 6000
    )
    try:
        async with server:
            logger.info("Waiting for commands")
            await server.serve_forever()
    finally:
        logging.info("Shutting down")
        await server.wait_closed()
