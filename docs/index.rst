counterpartyd Build System (counterpartyd_build)
==================================================

`counterpartyd_build <https://github.com/xnova/counterpartyd_build>`__ is the automated build system for
`counterpartyd <https://github.com/PhantomPhreak/counterpartyd>`__. This is an alternative method from
`manual counterpartyd installation and running <https://github.com/PhantomPhreak/counterpartyd/blob/master/README.md>`__,
which includes a point-and-click Windows installer, as well as a source code build script that takes care of
all setup necessary to run ``counterpartyd`` from source.

**Using the build system, you have the following options:**

- If you are a **Windows user**, you can either :doc:`use the installer package <UsingTheInstaller>`, or
  :doc:`build from source <BuildingFromSource>`
- If you are an **Ubuntu Linux user**, you can :doc:`use the build system to automate your
  install/setup from source <BuildingFromSource>`
- If you are **neither**, at this point you will need to follow `the manual installation instructions <https://github.com/PhantomPhreak/counterpartyd/blob/master/README.md>`__.

.. warning::

    The Windows installer will be released around 1 week after project launch (or, once ``counterpartyd`` proves itself
    as relatively stable, without major bugs/issues). In the meantime, Windows-based users should :doc:`build from
    source <BuildingFromSource>` so that keeping up with any major bugfixes is more straightforward.  


When to use?
------------------

This build system will probably be especially helpful in any of the following circumstances:

- You are a Windows user, or a Linux user that isn't super experienced with the command line interface.
- You want to deploy ``counterpartyd`` in a production environment, and have it run automatically on system startup
- You want to build your own ``counterpartyd`` binaries

Future plans
------------------

Future plans for the build system (*pull requests for these features would be greatly appreciated*):

- Add support for Linux distributions beyond Ubuntu Linux
- Add support for Mac OS X automated setup from source
- Add support for creation of installer for Mac OS X
- Add support for creation of ``.rpm``, ``.deb.``, etc. binary packages for Linux

More information on Counterparty is available in the `specs <https://github.com/PhantomPhreak/Counterparty>`__.


Table of Contents
------------------

.. toctree::
   :maxdepth: 3

   SettingUpBitcoind
   UsingTheInstaller
   BuildingFromSource
   AdditionalTopics


Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

