## Versions ##
* v1.1.3 (2016-01-18)
  * COMPATIBLE WITH: `counterparty-lib` 9.53.0 and `counterblock` 1.3.1
  * Updated `bitcoin` core to 0.11.2
  * Update `mongodb` to 3.0.x
* v1.1.2 (2015-11-01)
  * COMPATIBLE WITH: `counterparty-lib` 9.52.0 and `counterblock` 1.2.0
  * updated nginx version to newest
* v1.1.1 (2015-02-19)
  * numerous smaller bug fixes
* v1.1.0 (2015-02-12)
  
  This was a major update to the build system, to coincide with the structural changes made to `counterpartyd` (now `counterparty-lib` and `counterparty-cli`) and `counterblockd` (now `counterblock`):
  
  * Revamped and refactored build system: Build system is for federated node only, given that `counterparty` and `counterblock` both have their own setuptools `setup.py` files now.
  * Renamed repo from `counterparty_build` to `federatednode_build`
  * Removed Windows and Ubuntu 12.04/13.10 support. 
  * Service name changes: `counterpartyd service` changed to `counterparty`, `counterblockd` service changed to `counterblock`. `bitcoind` service changed to `bitcoin`
  * Bitcoin-testnet data-dir location changed: moved from `~xcp/.bitcoin-testnet` to `~xcp/.bitcoin/testnet3`
  * All configuration file locations changed:

    * `counterparty`: From `~xcp/.config/counterpartyd/counterparty.conf` to `~xcp/.config/counterparty/server.conf`
    * `counterparty-testnet`: From `~xcp/.config/counterpartyd-testnet/counterpartyd.conf` to `~xcp/.config/counterparty/server-testnet.conf`
    * `counterblock`: From `~xcp/.config/counterblockd/counterblockd.conf` to `~xcp/.config/counterblock/server.conf`
    * `counterblock-testnet`: From `~xcp/.config/counterblockd-testnet/counterblockd.conf` to `~xcp/.config/counterblock/server-testnet.conf`

  * Log and data directories changed as well (please see `counterparty` and `counterblock` release notes for more information, as well as the federated node document’s troubleshooting section for the new paths with federated nodes).
  * Updated the setup guide for federated nodes for new paths, service names, and more, located at: http://counterparty.io/docs/federated_node/

  * Updating:

    When updating to this new version, please BACKUP all data, and do a complete rebuild. Best way to kick this off is to do:
```
BRANCH=develop wget -q -O /tmp/fednode_run.py https://raw.github.com/CounterpartyXCP/federatednode_build/${BRANCH}/run.py sudo python3 /tmp/fednode_run.py
```

    When prompted, choose rebuild (‘r’), and then answer the other questions as appropriate. This rebuild should not delete your existing data, but does automatically build out everything for the new configuration files and paths.

    NOTE: If you have any customized `counterblock` configuration files, you will need to manually migrate those changes over from the old path (`~xcp/.config/counterblockd/counterblockd.conf`) to the new path (`~xcp/.config/counterblock/counterblock.conf`) (please don’t overwrite the new file, but just paste in the modified changes).
