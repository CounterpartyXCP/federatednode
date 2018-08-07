FROM aspireorg/base

MAINTAINER Aspire Developers <admin@aspirecrypto.com>

# install bitcoin-addrindex
ENV ASPIREGAS_VER="0.13.2"
WORKDIR /tmp
RUN wget -O bitcoin-addrindex.tar.gz https://github.com/btcdrak/bitcoin/releases/download/v${ASPIREGAS_VER}-addrindex/bitcoin-${ASPIREGAS_VER}-addrindex-x86_64-linux-gnu.tar.gz
RUN tar -xvzf bitcoin-addrindex.tar.gz
RUN install -C -m 755 -o root -g root --backup=off bitcoin-${ASPIREGAS_VER}/bin/* /usr/local/bin/
RUN rm bitcoin-addrindex.tar.gz && rm -rf bitcoin-${ASPIREGAS_VER}

# Set up bitcoind dirs and files
RUN mkdir -p /root/.aspiregas/
COPY aspiregas.conf /root/.aspiregas/
COPY start.sh /usr/local/bin/start.sh
RUN chmod a+x /usr/local/bin/start.sh

EXPOSE 9874 11374 19874 22485

# NOTE: Defaults to running on mainnet, specify -e TESTNET=1 to start up on testnet
ENTRYPOINT ["start.sh"]
