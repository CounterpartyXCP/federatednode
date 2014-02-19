Using the Installer
===================

.. warning::

    Due to the current pace of ``counterpartyd`` development, at the current moment it is recommended that
    **Windows users do not use the Windows installer**, and instead follow the instructions in :doc:`BuildingFromSource`
    (which are really not that involved). The reason for this is because the Windows installer always lags
    current ``counterpartyd`` progress by a few days normally, and at this point in heavy development, this fact will
    most likely cause issues for its users. Building from source is the best way to keep up with the frequent updates.


.. note::

    Please make sure you've followed the instructions in :doc:`SettingUpBitcoind` before moving through this section.


This section covers installing ``counterpartyd`` and its prerequisites via the available Windows installer.

Currently this installer is only available under Windows, but binary-based installers/packages will be coming
to other OSes in the future.

On Windows
~~~~~~~~~~~~~~~~~~~~~~

- Download the ``counterpartyd`` installer for `64-bit Windows <https://github.com/xnova/counterpartyd_binaries/raw/master/counterpartyd-v6.0-amd64_install.exe>`__
  (currently not available for 32 bit Windows. If there is enough demand we can create a Win32 installer.)
- Run the installer and navigate through the setup wizard
- The installer will verify all dependencies are on your system, as well as installing ``counterpartyd.exe``
  (i.e. which has been created as a self-contained program with all the necessary Python dependencies compiled in)
- The installer will gather data on your bitcoind installation, and create a basic ``counterpartyd.conf`` configuration file from that
- The installer will also have ``counterpartyd`` run on login automatically

You can start ``counterpartyd`` via the Counterparty shortcut under your Programs Menu.


On Linux
~~~~~~~~~~~~~~~~~~~~~~~

There is no pre-made installer for Linux at this time, as the source install is rather straightforward.

Just follow the instructions for Linux in :doc:`BuildingFromSource`.
