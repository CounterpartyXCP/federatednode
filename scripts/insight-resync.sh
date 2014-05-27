#!/bin/sh
CURDIR=`pwd`
cd ~xcp/insight-api
export BITCOIND_DATADIR=~xcp/.bitcoin/
export BITCOIND_USER=`cat ~xcp/.bitcoin/bitcoin.conf | sed -n 's/.*rpcuser=\([^ \n]*\).*/\1/p'`
export BITCOIND_PASS=`cat ~xcp/.bitcoin/bitcoin.conf | sed -n 's/.*rpcpassword=\([^ \n]*\).*/\1/p'`
INSIGHT_NETWORK=livenet INSIGHT_DB=~xcp/insight-api/db util/sync.js -D
cd $CURDIR
