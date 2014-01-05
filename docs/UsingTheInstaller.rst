Using the Installer
===================

.. warning::

    The Windows installer is in a beta state.  

.. note::

    Please make sure you've followed the instructions in :doc:`SettingUpBitcoind` before moving through this section.


This section covers installing ``counterpartyd`` and its prerequisites via the available Windows installer.

Currently this installer is only available under Windows, but binary-based installers/packages will be coming
to other OSes in the future.

On Windows
~~~~~~~~~~~~~~~~~~~~~~

- Download the ``counterpartyd`` installer for `64-bit Windows <https://github.com/xnova/counterpartyd_binaries/blob/master/counterpartyd-v0.1-amd64_install.exe?raw=true>`__
  (32 bit Windows installer will be available shortly)
- Run the installer and navigate through the setup wizard
- The installer will verify all dependencies are on your system, as well as installing ``counterpartyd.exe``
  (i.e. which has been created as a self-contained program with all the necessary Python dependencies compiled in)
- The installer will gather data on your bitcoind installation, and create a basic ``counterpartyd`` configuration file from that
- The installer will also have ``counterpartyd`` run as a service on startup (called "Counterparty") automatically

You can start and stop the Counterparty service via the Services icon in the Administrative Tools Control Panel.


On Linux
~~~~~~~~~~~~~~~~~~~~~~~

There is no pre-made installer for Linux at this time, as the source install is rather straightforward.

Just follow the instructions for Linux in :doc:`BuildingFromSource`.
