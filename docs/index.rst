counterpartyd Build System (counterpartyd_build)
==================================================

`counterpartyd_build <https://github.com/xnova/counterpartyd_build>`__ is the automated build system for
`counterpartyd <https://github.com/PhantomPhreak/counterpartyd>`__. This is an alternative method from
manual ``counterpartyd`` installation and running, which may be especially helpful in the following circumstances:

- You are a Windows user, or a Linux user that isn't super experienced with the command line interface.
- You want to deploy ``counterpartyd`` in a production environment, and have it run automatically on system startup
- You want to build your own ``counterpartyd`` binaries

This build system can can be used for the following tasks at this time:

- Automated setup of ``counterpartyd`` to run from source on Windows or Ubuntu Linux
- Automated creation of a Windows binary installer to allow for "point-and-click" installation of
  ``counterpartyd`` on Windows (as a packaged ``counterpartyd.exe`` binary)

Future plans for the build system (*pull requests for these features would be greatly appreciated*):

- Add support for Linux distributions beyond Ubuntu Linux
- Add support for Mac OS X automated setup from source
- Add support for creation of installer for Mac OS X
- Add support for creation of ``.rpm``, ``.deb.``, etc. binary packages for Linux

What is Counterparty?
----------------------

**Counterparty is an protocol that provides decentralized financial instrument on top of the Bitcoin blockchain.** 

Besides acting as a store of value, decentralized payment network and public ledger, Bitcoin itself allows programs to embed arbitrary data into
transactions. The value of this is immense, as it allows programs to be developed that add new functionality on top of Bitcoin, while inheriting
Bitcoin's security model, peer to peer processing system, and decentralized nature in the process.   


Table of Contents
------------------

.. toctree::
   :maxdepth: 3

   GettingStarted
   BuildingFromSource


Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

