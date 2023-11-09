FROM ubuntu:18.04

MAINTAINER Counterparty Developers <dev@counterparty.io>

# Install common dependencies
RUN apt-get update && apt-get install -y wget

# install bitcoin core
ENV BITCOIN_VER="25.1"
ENV BITCOIN_FOLDER_VER="25.1"
ENV BITCOIN_SHASUM="a978c407b497a727f0444156e397b50491ce862d1f906fef9b521415b3611c8b"
WORKDIR /tmp

RUN wget --no-check-certificate -O bitcoin-${BITCOIN_VER}-x86_64-linux-gnu.tar.gz https://bitcoincore.org/bin/bitcoin-core-${BITCOIN_VER}/bitcoin-${BITCOIN_VER}-x86_64-linux-gnu.tar.gz

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
