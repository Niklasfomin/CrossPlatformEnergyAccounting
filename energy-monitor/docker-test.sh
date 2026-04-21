#!/bin/bash

random_docker_loop() {
    while true; do
        # Generate a random container name
        cname="randctr_$(tr -dc a-z0-9 </dev/urandom | head -c 8)"
        # Choose a random image from a list (add more images as needed)
        images=(alpine busybox ubuntu)
        img=${images[$RANDOM % ${#images[@]}]}
        echo "Creating and running container: $cname with image: $img"
        # Run the container in detached mode, start multiple random processes, then remove
        docker run --name "$cname" -d $img sh -c "\
            (yes > /dev/null &) && \
            (dd if=/dev/urandom of=/dev/null bs=1M count=5 iflag=fullblock &) && \
            (shuf -i 1-1000000 | head -n 10000 > /dev/null &) && \
            (sleep \$((RANDOM % 10 + 1)) &) && \
            sleep 5"
        sleep 35
        docker rm -f "$cname" 2>/dev/null
        sleep 1
    done
}

random_docker_loop
