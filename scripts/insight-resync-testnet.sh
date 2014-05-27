#!/bin/sh
CURDIR=`pwd`
cd ~xcp/insight-api
export BITCOIND_USER=`cat ~xcp/.bitcoin-testnet/bitcoin.conf | sed -n 's/.*rpcuser=\([^ \n]*\).*/\1/p'`
export BITCOIND_PASS=`cat ~xcp/.bitcoin-testnet/bitcoin.conf | sed -n 's/.*rpcpassword=\([^ \n]*\).*/\1/p'`
INSIGHT_NETWORK=testnet INSIGHT_DB=~xcp/insight-api/db BITCOIND_DATADIR=~xcp/.bitcoin-testnet util/sync.js -D
cd $CURDIR
