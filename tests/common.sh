docker compose up -d

function cleanup() {
    # For debugging purposes
    docker compose logs --no-log-prefix duplyvolume
    docker compose down -t 0 --volumes
}

trap cleanup EXIT

function wait_for_container() {
    for i in {1..10}; do
        if [[ `docker compose ps --format '{{.Status}}' $1` =~ $2 ]]; then
          echo "$1 has started $(docker compose ps --format '{{.Status}}' $1)"
          return 0
        fi
        sleep 1
    done
    echo "$1 failed to start"
    return 1
}

wait_for_container container1 '^Up .+$' &
wait_for_container duplyvolume '^Up .+ \(healthy\)$' &

wait

# If we run rm inside the container we don't need sudo in this script
# We need sh here to run the glob inside the container
docker compose exec duplyvolume sh -c "rm -rf /target/*"
