#!/bin/bash

set -euo pipefail

. ../common.sh

# Perform a regular shutdown
docker compose stop duplyvolume

# Check that there are no error messages
OUTPUT=`docker compose logs --no-log-prefix duplyvolume | grep -v "Healthcheck passed"`

if [[ "$OUTPUT" =~ `cat ./duplyvolume-logs-expected.txt` ]]; then
    echo "Output is as expected"
else
    echo "Output is not as expected"
    echo "$OUTPUT"
    exit 1
fi
