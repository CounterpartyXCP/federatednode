#!/bin/bash

: ${PARAMS:=""}

# Respond to docker stop's SIGTERM gracefully
stopcmd="/usr/local/bin/bitcoin-cli ${PARAMS} $@ stop; exit 0"
trap "$stopcmd" SIGTERM

/usr/local/bin/bitcoind ${PARAMS} $@
