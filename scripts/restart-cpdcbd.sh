#!/bin/sh

sudo service counterpartyd restart
sudo service counterpartyd-testnet restart
sleep 10
sudo service counterblockd restart
sudo service counterblockd-testnet restart
