#!/bin/bash

EXTRA_PARAMS=""

# See whether to run for testnet or not
if [ ! -z "$TESTNET" ]; then
    EXTRA_PARAMS="${EXTRA_PARAMS} --testnet"
fi

/usr/local/bin/bitcoind ${EXTRA_PARAMS} "$@"