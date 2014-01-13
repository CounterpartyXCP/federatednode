Setting up bitcoind
====================

.. warning::

    This section sets up ``counterpartyd`` to run on mainnet, which means that when using it, **you will be working with real XCP**.
	If you would like to run on testnet instead, please see the section entitled **Running counterpartyd on testnet** in
	:doc:`Additional Topics <AdditionalTopics>`.

``counterpartyd`` communicates with the Bitcoin reference client (``bitcoind``). Normally, you'll run ``bitcoind``
on the same computer as your instance of ``counterpartyd`` runs on. However, you can also use a ``bitcoind``
sitting on a different server entirely.

This step is necessary whether you're :doc:`building counterpartyd from source <BuildingFromSource>` or
using the :doc:`installer package <UsingTheInstaller>`.

At this time, third-party RPC interfaces such as Blockchain.info's are not supported.

On Windows
-----------

Go to `the bitcoind download page <http://bitcoin.org/en/download>`__
and grab the installer for Windows. Install it with the default options.

Once installed, launch the GUI wallet program (Bitcoin-QT) to start the download of the blockchain.
Then, type Windows Key-R and enter ``cmd.exe`` to open a Windows command prompt. Type the following::

    cd %LOCALAPPDATA%\..\Roaming\.bitcoin
    notepad bitcoin.conf  

Say Yes to when Notepad asks if you want to create a new file, then paste in the text below::

    rpcuser=rpc
    rpcpassword=rpcpw1234
    server=1
    daemon=1
    txindex=1

**NOTE**:

- If you want ``bitcoind`` to be on testnet, not mainnet, see the section entitled **Running counterpartyd on testnet** in :doc:`Additional Topics <AdditionalTopics>`.
- You should change the RPC password above to something more secure.
    
Once done, press CTRL-S to save, and close Notepad.

After this, you must wait for the blockchain to finish downloading. Once this is done, you have two options:

- Close Bitcoin-QT and run ``bitcoind.exe`` directly. You can run it on startup by adding to your
  Startup program group in Windows, or using something like `NSSM <http://nssm.cc/usage>`__.
- You can simply restart Bitcoin-QT (for the configuration changes to take effecnt) and use that. This is
  fine for development/test setups, but not normally suitable for production systems. (You can have
  Bitcoin-QT start up automatically by clicking on Settings, then Options and checking the
  box titled "Start Bitcoin on system startup".


On Ubuntu Linux
----------------

If not already installed (or running on a different machine), do the following
to install it (on Ubuntu, other distros will have similar instructions)::

    sudo apt-get install python-software-properties
    sudo add-apt-repository ppa:bitcoin/bitcoin
    sudo apt-get update
    sudo apt-get install bitcoind
    mkdir -p ~/.bitcoin/
    echo -e "rpcuser=rpc\nrpcpassword=rpcpw1234\nserver=1\ndaemon=1" > ~/.bitcoin/bitcoin.conf

Please then edit the ``~/.bitcoin/bitcoin.conf`` file and set the file to the contents specified above (.

Next, start ``bitcoind``::

    bitcoind

The bitcoin server should now be started. The blockchain will begin to download automatically. You must let it finish 
downloading entirely before going to the next step. You can check the status of this by running::

     bitcoind getinfo|grep blocks

When done, the block count returned by this command will match the value given from
`this page <http://blockexplorer.com/q/getblockcount>`__.

For automatic startup of ``bitcoind`` on system boot, `this page <https://bitcointalk.org/index.php?topic=25518.0>`__
provides some good tips.
