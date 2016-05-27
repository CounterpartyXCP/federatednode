FROM counterparty/base

MAINTAINER Counterparty Development Team <dev@counterparty.io>

# install bitcoin-addrindex
ENV BITCOIN_VER="0.12.1"
RUN wget -O /tmp/bitcoin-addrindex.tar.gz https://github.com/btcdrak/bitcoin/releases/download/v${BITCOIN_VER}-addrindex/bitcoin-${BITCOIN_VER}-addrindex-linux64.tar.gz
RUN tar -xvzf -C /tmp /tmp/bitcoin-addrindex.tar.gz
RUN install -C -m 755 -o root -g root --backup=off /tmp/bitcoin-${BITCOIN_VER}/bin/* /usr/local/bin/
RUN rm /tmp/bitcoin-addrindex.tar.gz && rm -rf /tmp/bitcoin-${BITCOIN_VER}

# Set up bitcoind dirs and files
RUN mkdir /root/.bitcoin/ /root/bitcoin_data/
COPY bitcoin.conf /root/.bitcoin/bitcoin.conf
COPY start.sh /usr/local/bin/start.sh
RUN chmod a+x /usr/bin/start.sh

EXPOSE 8332 8333 18332 18333

# NOTE: Defaults to running on mainnet, specify -e TESTNET=1 to start up on testnet
ENTRYPOINT ["start.sh"]