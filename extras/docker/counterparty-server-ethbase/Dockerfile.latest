FROM counterparty/base

MAINTAINER Counterparty Developers <dev@counterparty.io>

# Install ethereum dependencies
# NEW PACKAGES TO BUILD `solc`
# from http://www.ethdocs.org/en/latest/ethereum-clients/cpp-ethereum/building-from-source/linux-ubuntu.html
RUN apt-add-repository --keyserver pgp.mit.edu -y ppa:george-edison55/cmake-3.x
RUN apt-get -y update && apt-get -y install language-pack-en-base gcc-4.8 software-properties-common
RUN add-apt-repository --keyserver pgp.mit.edu -y ppa:ethereum/ethereum
RUN add-apt-repository --keyserver pgp.mit.edu -y ppa:ethereum/ethereum-dev
RUN apt-get -y update && apt-get -y install build-essential cmake libboost-all-dev libgmp-dev \
    libleveldb-dev libminiupnpc-dev libreadline-dev libncurses5-dev \
    libcurl4-openssl-dev libcryptopp-dev libmicrohttpd-dev libjsoncpp-dev \
    libargtable2-dev libedit-dev mesa-common-dev ocl-icd-libopencl1 opencl-headers \
    libgoogle-perftools-dev ocl-icd-dev libv8-dev libz-dev libjsonrpccpp-dev

# Install counterparty-lib
RUN git clone -b evmparty https://github.com/CounterpartyXCP/counterparty-lib.git /counterparty-lib
COPY . /counterparty-lib
WORKDIR /counterparty-lib
RUN python3 setup.py install_serpent
RUN python3 setup.py install_solc
