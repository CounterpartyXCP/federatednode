#!/bin/bash

EXTRA_PARAMS=""

# See whether to run for testnet or not
if [ ! -z "$TESTNET" ]; then
    EXTRA_PARAMS="${EXTRA_PARAMS} --testnet"
fi

# copy on startup as a volume mount may overlay /root/.bitcoin, and we always want this file there...
cp /root/bitcoin.conf.default /root/.bitcoin/bitcoin.conf

/usr/local/bin/bitcoind ${EXTRA_PARAMS} "$@"