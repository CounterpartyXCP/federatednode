#!/bin/sh

sudo sv stop bitcoind
sudo sv stop bitcoind-testnet
sudo sv stop insight
sudo sv stop insight-testnet
sudo sv stop counterpartyd
sudo sv stop counterpartyd-testnet
sudo sv stop counterblockd
sudo sv stop counterblockd-testnet
