#!/bin/bash

set -euo pipefail

for TEST_DIR in ./test-*; do
    echo "Test $TEST_DIR"
    pushd $TEST_DIR
    ./test.sh
    popd
done

echo "All tests passed successfully"
