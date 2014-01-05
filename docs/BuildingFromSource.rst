Building & Running from Source
================================

.. note::

    Please make sure you've followed the instructions in :doc:`SettingUpBitcoind` before moving through this section.

This section provides information about how to install and run ``counterpartyd`` from source, using this
``counterpartyd`` build system (as an alternative to setting it up manually). This method is suitable for
Linux users, as well as Windows users that want to develop/enhance ``counterpartyd`` (or just don't want to
use the binary installer).


On Linux
-----------

Prerequisites
~~~~~~~~~~~~~

Currently, Ubuntu Linux (Server or Desktop) **12.04 LTS** and **13.10** are supported.

Support for other distributions is a future task.


Installing
~~~~~~~~~~~

**As the user you want to run** ``counterpartyd`` **as**, launch a terminal window, and type the following::

    sudo apt-get -y update
    sudo apt-get -y install git-core python3
    git clone https://github.com/xnova/counterpartyd_build ~/counterpartyd_build
    sudo python3 ~/counterpartyd_build/setup.py

The ``setup.py`` script will install necessary dependencies, check out the newest version of ``counterpartyd``
itself from git, create the python environment for ``counterpartyd``, and install an upstart script that
will automatically start ``counterpartyd`` on startup.


Creating a default config
~~~~~~~~~~~~~~~~~~~~~~~~~~

Follow the instructions listed under the **Config and Logging** section in :doc:`GettingStarted`.


Running from Source
~~~~~~~~~~~~~~~~~~~

After installing and creating the necessary basic config, run ``counterpartyd`` in the foreground to make sure
everything works fine::

    counterpartyd --log-file=-
    
(The above assumes ``/usr/local/bin`` is in your PATH, which is where the ``counterpartyd`` symlink (which just
points to the ``run.py`` script) is placed. If not, run ``/usr/local/bin/counterpartyd`` instead.

Once you're sure it launches and runs fine, press CTRL-C to exit it, and then run ``counterpartyd`` as a background process via::

    sudo service counterpartyd start

You can then run any of ``counterpartyd’s`` other functions, like `the examples listed here <https://github.com/PhantomPhreak/counterpartyd#examples>`__.

To run the ``counterpartyd`` testsuite::

    counterpartyd tests


Updating to the newest source
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

As the code is enhanced and improved on Github, you can refresh your local copy of the repositories like so::

    cd ~/counterpartyd_build
    git pull origin master
    cd ~/counterpartyd_build/dist/counterpartyd
    git pull origin master

    

On Windows
-----------

Prerequisites
~~~~~~~~~~~~~

.. note::

   If you are on a computer with a 64-bit version of Windows, it's normally best to get the 64-bit version of
   everything below. The only exception would be if you want to create a 32-bit installer for Counterpartyd.
   In that case, go with the 32-bit versions of all of the dependencies below.

Minimally required to build ``counterpartyd`` from source is the following:

- Python 3.3.x -- grab the `32-bit version <http://www.python.org/ftp/python/3.3.3/python-3.3.3.msi>`__
  or `64-bit version <http://www.python.org/ftp/python/3.3.3/python-3.3.3.amd64.msi>`__.
  Install to the default ``C:\Python33`` location
- Python Win32 extensions -- grab the `32-bit version <http://sourceforge.net/projects/pywin32/files/pywin32/Build%20218/pywin32-218.win32-py3.3.exe/download>`__
  or `64-bit version <http://sourceforge.net/projects/pywin32/files/pywin32/Build%20218/pywin32-218.win-amd64-py3.3.exe/download>`__
- Git for Windows. Download `here <http://git-scm.com/download/win>`__ and install. Use the default installer options

If you want to be able to build the Counterpartyd installer, also download the following:

- Grab NSIS from `here <http://prdownloads.sourceforge.net/nsis/nsis-2.46-setup.exe?download>`__ -- Please choose the default
  options during installation, and install to the default path
- Download the NSIS SimpleService plugin from `here <http://nsis.sourceforge.net/mediawiki/images/c/c9/NSIS_Simple_Service_Plugin_1.30.zip>`__
  and save the .dll file contained in that zip to your NSIS ``plugins`` directory (e.g. ``C:\Program Files (X86)\NSIS\plugins``)
- cx_freeze -- grab the `32-bit version <http://prdownloads.sourceforge.net/cx-freeze/cx_Freeze-4.3.2.win32-py3.3.msi?download>`__
  or `64-bit version <http://prdownloads.sourceforge.net/cx-freeze/cx_Freeze-4.3.2.win-amd64-py3.3.msi?download>`__ as appropriate


Installing
~~~~~~~~~~~

Type ``<Windows Key>-R`` to open the run dialog, and enter "cmd.exe" to launch a command window.

In the command window, type the following commands::

    cd C:\
    git clone https://github.com/xnova/counterpartyd_build
    cd counterpartyd_build
    C:\Python33\python.exe setup.py
     
The above steps will check out the build scripts to ``C:\counterpartyd_build``, and run the ``setup.py`` script, which
will check out the newest version of ``counterpartyd`` itself from git, create a virtual environment with the
required dependencies, and do other necessary tasks to integrate it into the system.

If you chose to start ``counterpartyd`` at startup automatically, the setup script will also create a shortcut
to ``counterpartyd`` in your Startup group. 

Upon the successful completion of this script, you can now run ``counterpartyd`` using the steps below.


Running from Source
~~~~~~~~~~~~~~~~~~~

After installing, open a command window and run ``counterpartyd`` in the foreground via::

    cd C:\counterpartyd_build
    C:\Python33\python.exe run.py --log-file=-

You can then run any of ``counterpartyd’s`` other functions, like `the examples listed here <https://github.com/PhantomPhreak/counterpartyd#examples>`__.

To run the ``counterpartyd`` testsuite::

    cd C:\counterpartyd_build
    run.py tests 


Updating to the newest source
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

As the code is enhanced and improved on Github, you can refresh your local copy of the repositories like so::

    cd C:\counterpartyd_build
    git pull origin master
    cd C:\counterpartyd_build\dist\counterpartyd
    git pull origin master


Building your own Installer
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Complete the instructions under **Prerequisites** above.
Then, execute the following commands to build the installer package::

    cd C:\counterpartyd_build
    C:\Python33\python.exe setup.py -b
    
If successful, you will be provided the location of the resulting installer package.


Mac OS X
--------

Mac OS support will be forthcoming.