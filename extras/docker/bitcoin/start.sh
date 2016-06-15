#!/bin/bash

: ${PARAMS:=""}
/usr/local/bin/bitcoind ${PARAMS} "$@"
