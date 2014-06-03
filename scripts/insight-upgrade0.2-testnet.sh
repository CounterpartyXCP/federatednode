#!/bin/sh
CURDIR=`pwd`
cd ~xcp/insight-api
export BITCOIND_DATADIR=/home/xcp/.bitcoin-testnet/
export BITCOIND_USER=`cat /home/xcp/.bitcoin-testnet/bitcoin.conf | sed -n 's/.*rpcuser=\([^ \n]*\).*/\1/p'`
export BITCOIND_PASS=`cat /home/xcp/.bitcoin-testnet/bitcoin.conf | sed -n 's/.*rpcpassword=\([^ \n]*\).*/\1/p'`
INSIGHT_NETWORK=testnet INSIGHT_DB=/home/xcp/insight-api/db util/upgradeV0.2js
cd $CURDIR
