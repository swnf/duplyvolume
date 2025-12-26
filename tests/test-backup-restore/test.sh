#!/bin/bash

set -euo pipefail

. ../common.sh

docker compose exec container1 sh -c "echo value1 > /volume1/file1"

OUTPUT_BACKUP=`docker compose exec duplyvolume backup | grep -v "Healthcheck passed"`
if [[ "$OUTPUT_BACKUP" =~ `cat ./duplyvolume-backup-expected.txt` ]]; then
    echo "Backup output is as expected"
else
    echo "Backup output is not as expected"
    echo "$OUTPUT_BACKUP"
    exit 1
fi

docker compose exec container1 sh -c "echo value2 > /volume1/file1"

OUTPUT_RESTORE=`docker compose exec duplyvolume restore | grep -v "Healthcheck passed"`
if [[ "$OUTPUT_RESTORE" =~ `cat ./duplyvolume-restore-expected.txt` ]]; then
    echo "Restore output is as expected"
else
    echo "Restore output is not as expected"
    echo "$OUTPUT_RESTORE"
    exit 1
fi

# Check the file content is "value1" again
FILE_CONTENTS=`docker compose exec container1 cat /volume1/file1`
if [[ "$FILE_CONTENTS" == "value1" ]]; then
    echo "File is as expected"
else
    echo "File is not as expected"
    echo "$FILE_CONTENTS"
    exit 1
fi

# Check the full log
OUTPUT=`docker compose logs --no-log-prefix duplyvolume | grep -v "Healthcheck passed"`

if [[ "$OUTPUT" =~ `cat ./duplyvolume-logs-expected.txt` ]]; then
    echo "Output is as expected"
else
    echo "Output is not as expected"
    echo "$OUTPUT"
    exit 1
fi
