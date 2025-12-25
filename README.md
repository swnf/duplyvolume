# duplyvolume

A simple solution to back up docker volumes.

Features:
- Support encryption, incremental backups, and S3 storage based on [duplicity](https://duplicity.us/)
- Auto-discover docker volumes
- Automatically stop/start only the containers that use a volume
- Schedule backups using cron expressions
- Overwrite retention period using volume labels

_Not_ implemented:
- Backup/Restore a single volume. You can use the duplicity command line for that.
- Better stop/start strategies. With the current strategy, a container can be stopped multiple times if it has multiple attached volumes or shares a volume with another container. This can lead to inconsistencies in the backup.

## Example

Example `docker-compose.yaml` configuration:

```yaml
duplyvolume:
  image: "ghcr.io/swnf/duplyvolume:1-latest"
  restart: unless-stopped
  environment:
    BACKUP_CRON: "0 3 * * 0"
    TZ: "Europe/Berlin"
  volumes:
    - "/var/run/docker.sock:/var/run/docker.sock"
    - "/path/to/backup:/target"
```

For S3 support specify `S3_BUCKET_NAME`/`S3_REGION_CODE`/`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` and remove the `/target` volume.

## Commands

| Command                                       | Description                                                                                                                                                                                                              |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `docker-compose exec duplyvolume backup`      | Perform a backup of all volumes (Press <kbd>Ctrl-C</kbd> to cancel)                                                                                                                                                      |
| `docker-compose exec duplyvolume restore`     | Restore **all** volumes. This will overwrite all contents of your volumes. If a volume has no recent backups, duplyvolume will assume that it was deleted and will _not_ restore it. (Press <kbd>Ctrl-C</kbd> to cancel) |
| `docker-compose exec duplyvolume cancel`      | Cancel a running backup running somewhere else                                                                                                                                                                           |
| `docker-compose exec duplyvolume healthcheck` | Perform a healthcheck                                                                                                                                                                                                    |
| `docker-compose stop duplyvolume`             | Cancel all running backups and shut down                                                                                                                                                                                 |

## Environment variables

_All environment variable values can be substituted with files. Just point for example `PASSPHRASE_FILE` to the path of a file_

| Variable                       | Description                                                                                                                                                                                                                                  |
| ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `IGNORE_REGEX`                 | Ignore volumes with names matching this regex. By default, volume names containing "tmp", "cache" and anonymous volumes are ignored.                                                                                                         |
| `BACKUP_CRON`                  | A cron expression in the format year - month - day - week - day of week - hour - minute - second. "\*" is the wildcard character. For more information, see [here](https://apscheduler.readthedocs.io/en/stable/modules/triggers/cron.html). |
| `FULL_IF_OLDER_THAN`           | If the last backup is older than this timespan, perform a full instead of an incremental backup. Defaults to one month ("1M", see [Time Formats](https://duplicity.gitlab.io/stable/duplicity.1.html#time-formats)).                         |
| `REMOVE_OLDER_THAN`            | Delete all backups older than this timespan. Dependencies of newer backups will not be deleted.                                                                                                                                              |
| `REMOVE_ALL_BUT_N_FULL`        | Delete all backups older than the last n full backups.                                                                                                                                                                                       |
| `REMOVE_ALL_INC_OF_BUT_N_FULL` | Delete _incremental_ backups older than the last n full backups.                                                                                                                                                                             |
| `TZ`                           | The timezone used for the backup scheduler.                                                                                                                                                                                                  |
| `PASSPHRASE`                   | The passphrase used to encrypt the backup. It will only encrypt volume contents, not volume metadata. If this is not set, the backup will be unencrypted.                                                                                    |
| `S3_BUCKET_NAME`               | The name of a S3 bucket. If this is set, the bucket will be used instead of `/target`. This setting also requires `S3_REGION_CODE` or `S3_ENDPOINT_URL`.                                                                                     |
| `S3_REGION_CODE`               | The region code of a S3 bucket. This setting also requires `S3_BUCKET_NAME`. It is mutually exclusive with `S3_ENDPOINT_URL`.                                                                                                                |
| `S3_ENDPOINT_URL`              | The endpoint url of a S3 bucket. This setting also requires `S3_BUCKET_NAME`. It is mutually exclusive with `S3_REGION_CODE`. Use this setting if you want to use a custom S3 compatible storage server.                                     |
| `S3_STORAGE_CLASS`             | The S3 storage class to use. Can only be `STANDARD` or `STANDARD_IA`. Defaults to `STANDARD`                                                                                                                                                 |
| `AWS_ACCESS_KEY_ID`            | A valid AWS access key ID for the S3 bucket                                                                                                                                                                                                  |
| `AWS_SECRET_ACCESS_KEY`        | A valid AWS secret access key for the S3 bucket                                                                                                                                                                                              |

## Volume labels

Volume labels can overwrite the defaults from environment variables:

| Label                                      | Description                        |
| ------------------------------------------ | ---------------------------------- |
| `duplyvolume.remove_older_than`            | See `REMOVE_OLDER_THAN`            |
| `duplyvolume.remove_all_but_n_full`        | See `REMOVE_ALL_BUT_N_FULL`        |
| `duplyvolume.remove_all_inc_of_but_n_full` | See `REMOVE_ALL_INC_OF_BUT_N_FULL` |
