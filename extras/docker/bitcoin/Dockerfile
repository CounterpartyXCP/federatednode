FROM counterparty/base

MAINTAINER Counterparty Developers <dev@counterparty.io>

# install bitcoin-addrindex
ENV BITCOIN_VER="0.13.2"
WORKDIR /tmp
RUN wget -O bitcoin-addrindex.tar.gz https://github.com/btcdrak/bitcoin/releases/download/v${BITCOIN_VER}-addrindex/bitcoin-${BITCOIN_VER}-addrindex-x86_64-linux-gnu.tar.gz
RUN tar -xvzf bitcoin-addrindex.tar.gz
RUN install -C -m 755 -o root -g root --backup=off bitcoin-${BITCOIN_VER}/bin/* /usr/local/bin/
RUN rm bitcoin-addrindex.tar.gz && rm -rf bitcoin-${BITCOIN_VER}

# Set up bitcoind dirs and files
RUN mkdir -p /root/.bitcoin/
COPY bitcoin.conf /root/.bitcoin/
COPY start.sh /usr/local/bin/start.sh
RUN chmod a+x /usr/local/bin/start.sh

EXPOSE 8332 8333 18332 18333

# NOTE: Defaults to running on mainnet, specify -e TESTNET=1 to start up on testnet
ENTRYPOINT ["start.sh"]
