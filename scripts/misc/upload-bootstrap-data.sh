#!/bin/sh
#Sample script to get and upload counterpartyd bootstrap data to s3
# Requires s3cmd (sudo apt-get install s3cmd; sudo s3cmd --configure)
#This script could then be configured and put into your /etc/cron.daily dir for instance

export CPD_USER_NAME=local
export CPD_USER_HOMEDIR=$(eval echo ~${CPD_USER_NAME})
S3_CONTAINER_NAME="counterparty-bootstrap"

echo "Stopping services..."
service counterpartyd stop
service counterpartyd-testnet stop

echo "Creating tarball (mainnet)..."
rm -f /tmp/counterpartyd-db.latest.tar.gz /tmp/counterpartyd-testnet-db.latest.tar.gz
cd ${CPD_USER_HOMEDIR}/.config/counterpartyd/ && tar -czvf /tmp/counterpartyd-db.latest.tar.gz counterpartyd.9.db*
s3cmd --force --bucket-location=US -P put /tmp/counterpartyd-db.latest.tar.gz s3://${S3_CONTAINER_NAME}/
rm -f /tmp/counterpartyd-db.latest.tar.gz

echo "Creating tarball (testnet)..."
cd ${CPD_USER_HOMEDIR}/.config/counterpartyd-testnet/ && tar -czvf /tmp/counterpartyd-testnet-db.latest.tar.gz counterpartyd.9.testnet.db*
s3cmd --force --bucket-location=US -P put /tmp/counterpartyd-testnet-db.latest.tar.gz s3://${S3_CONTAINER_NAME}/
rm -f /tmp/counterpartyd-testnet-db.latest.tar.gz

echo "Updating counterpartyd from git..."
/bin/bash -c 'cd ${CPD_USER_HOMEDIR}/counterpartyd_build && SUDO_USER=${CPD_USER_NAME} ./setup.py update'

echo "Restarting services..."
service counterpartyd start
service counterpartyd-testnet start
