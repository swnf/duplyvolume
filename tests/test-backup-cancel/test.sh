#!/bin/bash

set -euo pipefail

. ../common.sh

# Create a large file to make sure the backup takes a long time
docker compose exec container1 sh -c "fallocate -l 10GB /volume1/file1"

# Start backup in the background
# See https://stackoverflow.com/a/20018118 for the non-blocking pipe
docker compose exec duplyvolume backup > /tmp/duplyvolume-backup-test-output &
sleep 1
exec 3< /tmp/duplyvolume-backup-test-output
rm /tmp/duplyvolume-backup-test-output

# Give the backup some time to start
sleep 20

# Test that a healthcheck during a running backup is successful
# Don't check the output, other log lines might end up in it
docker compose exec duplyvolume healthcheck

# Cancel the backup
docker compose exec duplyvolume pkill -SIGINT -f "duplyvolume backup"

# Wait for the original backup call to terminate
wait

OUTPUT_BACKUP=`cat <&3 | grep -v "Healthcheck passed"`
if [[ "$OUTPUT_BACKUP" =~ `cat ./duplyvolume-backup-expected.txt` ]]; then
    echo "Backup output is as expected"
else
    echo "Backup output is not as expected"
    echo "$OUTPUT_BACKUP"
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
