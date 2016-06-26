#!/bin/bash

# Respond to docker stop's SIGTERM gracefully
# Utilize the SIGTERM propagation pattern from http://veithen.github.io/2014/11/16/sigterm-propagation.html
: ${PARAMS:=""}
trap 'kill -TERM $PID' TERM INT
/usr/local/bin/bitcoind ${PARAMS} $@ &
PID=$!
wait $PID
trap - TERM INT
wait $PID
EXIT_STATUS=$?