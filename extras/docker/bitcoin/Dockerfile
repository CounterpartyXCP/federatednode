FROM counterparty/base

MAINTAINER Counterparty Developers <dev@counterparty.io>

# install bitcoin core
ENV BITCOIN_VER="0.21.1"
ENV BITCOIN_FOLDER_VER="0.21.1"
ENV BITCOIN_SHASUM="366eb44a7a0aa5bd342deea215ec19a184a11f2ca22220304ebb20b9c8917e2b"
WORKDIR /tmp

RUN wget --no-check-certificate -O bitcoin-${BITCOIN_VER}-x86_64-linux-gnu.tar.gz https://bitcoin.org/bin/bitcoin-core-${BITCOIN_VER}/bitcoin-${BITCOIN_VER}-x86_64-linux-gnu.tar.gz

RUN myhash=$(sha256sum "bitcoin-${BITCOIN_VER}-x86_64-linux-gnu.tar.gz" | cut -d' ' -f1); \
    if [ "$myhash" = "$BITCOIN_SHASUM" ] ; \
        then echo "checksum ok"; \
        else echo "checksum failed for bitcoin-${BITCOIN_VER}-x86_64-linux-gnu.tar.gz"; exit 255 ; \
    fi
RUN tar -xvzf bitcoin-${BITCOIN_VER}-x86_64-linux-gnu.tar.gz
RUN install -C -m 755 -o root -g root --backup=off bitcoin-${BITCOIN_FOLDER_VER}/bin/* /usr/local/bin/
RUN rm bitcoin-${BITCOIN_VER}-x86_64-linux-gnu.tar.gz && rm -rf bitcoin-${BITCOIN_FOLDER_VER}

# Set up bitcoind dirs and files
RUN mkdir -p /root/.bitcoin/
COPY bitcoin.conf /root/.bitcoin/
COPY start.sh /usr/local/bin/start.sh
RUN chmod a+x /usr/local/bin/start.sh

EXPOSE 8332 8333 18332 18333

# NOTE: Defaults to running on mainnet, specify -e TESTNET=1 to start up on testnet
ENTRYPOINT ["start.sh"]
