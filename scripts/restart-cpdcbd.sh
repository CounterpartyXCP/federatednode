#!/bin/sh

sudo sv restart counterpartyd
sudo sv restart counterpartyd-testnet
sleep 10
sudo sv restart counterblockd
sudo sv restart counterblockd-testnet
