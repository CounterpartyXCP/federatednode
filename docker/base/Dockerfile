FROM ubuntu:16.04

MAINTAINER Counterparty Develoeprs <dev@counterparty.io>

# Install common dependencies
RUN apt-get update && apt-get install -y apt-utils wget curl git mercurial \
    python3 python3-dev python3-setuptools python3-appdirs \
    build-essential vim unzip software-properties-common

# Set locale
RUN dpkg-reconfigure locales && \
    locale-gen en_US.UTF-8 && \
    /usr/sbin/update-locale LANG=en_US.UTF-8
ENV LC_ALL en_US.UTF-8

# Set home dir env variable
ENV HOME /root
