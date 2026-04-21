#!/bin/bash

# Usage: ./docker-test.sh [sleep_between_containers] [num_parallel_containers]
SLEEP_BETWEEN_CONTAINERS="${1:-35}"
NUM_PARALLEL_CONTAINERS="${2:-1}"

random_docker_container() {
    while true; do
        # Generate a random container name
        cname="randctr_$(tr -dc a-z0-9 </dev/urandom | head -c 8)"
        # Choose a random image from a list (add more images as needed)
        images=(alpine busybox ubuntu)
        img=${images[$RANDOM % ${#images[@]}]}
        echo "Creating and running container: $cname with image: $img"
        # Stagger process spawning and termination inside the container
        docker run --name "$cname" -d $img sh -c "\
            (yes > /dev/null &) && \
            (sleep 2; dd if=/dev/urandom of=/dev/null bs=1M count=5 iflag=fullblock &) && \
            (sleep 4; shuf -i 1-1000000 | head -n 10000 > /dev/null &) && \
            (sleep 6; sleep 3 &) && \
            sleep 10"
        sleep "$SLEEP_BETWEEN_CONTAINERS"
        docker rm -f "$cname" 2>/dev/null
        sleep 1
    done
}

random_docker_container
