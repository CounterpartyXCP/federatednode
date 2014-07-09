Setting up a Counterblock Federated Node
==============================================


Introduction
-------------

The Counterwallet web-wallet works against one or more Counterblock Federated Node back-end servers.
Each backend server runs ``bitcoind``, ``insight``, ``counterpartyd``, and ``counterblockd``, and exists as a fully self-contained
node. Counterwallet utilizes these backend servers in making API calls either sequentially (i.e. failover) or in
parallel (i.e. consensus-based). When a user logs in, this list is shuffled so that, in aggregate, user requests are
effectively load-balanced across available servers.

The nodes used by Counterwallet in this way are referred to as Federated Nodes, because they are self-contained and
independent, but (though special "multiAPI" functionality client-side) work together to provide services to Counterwallet users.
Indeed, by setting up multiple such (Counterblock) Federated Nodes, one can utilize a similar redundancy/reliability model
in one's own 3rd party application, that Counterwallet utilizes.  

By default, Counterblock Federated Nodes also host Counterwallet content (this will change in the future).
Regarding this, the Counterparty team itself operates the primary Counterwallet platform. However, as Counterwallet is open source
software, it is possible to host your own site with Counterwallet site (for your personal use, or as an offering to
others), or to even host your own Counterwallet servers to use with your own Counterparty wallet implementation.
The Counterparty team supports this kind of activity (as long as the servers are secure), as it aids with increasing decentralization.
    
Also note that due to the nature of Counterwallet being a deterministic wallet, users using one Counterwallet platform (i.e. the
official one, for instance) have the flexibility to start using a different Counterwallet platform instead at any time,
and as funds (i.e. private keys) are not stored on the server in any fashion, they will be able to see their funds on either.
(Note that the only thing that will not migrate are saved preferences, such as address aliases, the theme setting, etc.)

The above being said, this document walks one though some of the inner workings of Counterwallet, as well as describing
how one can set up their own Counterblock Federated Node server(s).

This document is primarily intended for system administrators and developers.


Components
----------

counterpartyd
^^^^^^^^^^^^^^

``counterpartyd`` is the Counterparty reference client itself. It's responsibilities include parsing out Counterparty
transactions from the Bitcoin blockchain. It has a basic command line interface, and a reletively low-level API for
getting information on specific transactions, or general state info.

counterblockd
^^^^^^^^^^^^^

The ``counterblockd`` daemon provides a more high-level API that layers on top of ``counterpartyd``'s API, and includes extended
information, such as market and price data, trade operations, asset history, and more. It is used extensively by Counterwallet
itself, and is appropriate for use by applications that require additional API-based functionality beyond the scope of
what ``counterpartyd`` provides.

``counterblockd`` also provides a proxy-based interface to all ``counterpartyd`` API methods, via the ``proxy_to_counterpartyd`` API call.

counterwallet
^^^^^^^^^^^^^^

This is the Counterwallet source code itself. ``counterwallet`` communicates with one or more Counterblock Federated Nodes,
and accesses API functionality of both ``counterblockd`` and ``counterpartyd``.



Counterblock Node Provisioning
--------------------------------

Production
^^^^^^^^^^^^

Here are the recommendations and/or requirements when setting up a production-grade Counterblock Federated Node server:

**Server Hardware/Network Recommendations:**

- Xeon E3+ or similar-class processor
- 16GB+ RAM (ECC)
- 2x SSD 120GB+ drives in RAID-1 (mirrored) configuration
- Hosted in a secure data center with physical security and access controls
- DDOS protection recommended if you will be offering your service to others

**Server Software:**

- Ubuntu 14.04 64-bit required

**Server Security:**

`This link <http://www.thefanclub.co.za/how-to/how-secure-ubuntu-1204-lts-server-part-1-basics>`__ is a good starting point
Specifically, see steps 1 through 5, 7, 12, and 13 though 17.

Some notes:

- SSH should run on a different port, with root access disabled
- Use iptables/ufw (software firewall) in addition to any hardware firewalls
- Utilize ``fail2ban``, ``psad``, ``chkrootkit`` and ``rkhunter``
- Utilize modified ``sysctl`` settings for improved security and DDOS protection 
- Only one or two trusted individuals should have access to the box. All root access through ``sudo``.
- Consider utilizing 2FA (two-factor authentication) on SSH and any other services that require login.
  `Duo <https://www.duosecurity.com/>`__ is a good choice for this (and has great `SSH integration <https://www.duosecurity.com/unix>`__).
- The system should have a proper hostname (e.g. counterblock.myorganization.org), and your DNS provider should be DDOS resistant
- System timezone should be set to UTC
- Enable Ubuntu's  `automated security updates <http://askubuntu.com/a/204>`__
- If running multiple servers, consider other tweaks on a per-server basis to reduce homogeneity.  


Testing / Development
^^^^^^^^^^^^^^^^^^^^^^

If you'd like to set up a Counterblock Federated Node system for testing and development, the requirements are minimal. Basically you
need to set up a Virtual Machine (VM) instance (or hardware) with **Ubuntu 14.04 64-bit** and give it at least **2 GB**
of memory and **90 GB** of free disk space.

Node Setup
-----------

Once the server is provisioned and set up as above, you will need to install all of the necessary software and dependencies. We have an
installation script for this, that is fully automated **and installs ALL dependencies, including ``bitcoind`` and ``insight``**::

    cd && wget -qO setup_federated_node.py https://raw.github.com/CounterpartyXCP/counterpartyd_build/master/setup_federated_node.py
    sudo python3 setup_federated_node.py

Then just follow the on-screen prompts (choosing to build from *master* if you are building a production node,
or from *develop* **only** if you are a developer).

Once done, start up ``bitcoind`` daemon(s)::

    sudo service bitcoind start
    sudo service bitcoind-testnet start
    
    sudo tail -f ~xcp/.bitcoin/debug.log 

That last command will give you information on the Bitcoin blockchain download status. After the blockchain starts
downloading, you can launch the ``insight`` daemon(s)::

    sudo service insight start
    sudo service insight-testnet start
    
    sudo tail -f ~xcp/insight-api/insight.log 

As well as ``counterpartyd`` itself::

    sudo service counterpartyd start
    sudo service counterpartyd-testnet start
    
    sudo tail -f ~xcp/.config/counterpartyd/counterpartyd.log

Then, watching these log, wait for the insight sync (as well as the bitcoind sync and counterpartyd syncs) to finish,
which should take between 7 and 12 hours. After this is all done, reboot the box for the new services to
start (which includes both ``counterpartyd`` and ``counterblockd``).

``counterblockd``, after starting up must then sync to ``counterpartyd``. It will do this automatically, and the
process will take between 20 minutes to 1 hour most likely. You can check on the status of ``counterblockd``'s
sync using::

    sudo tail -f ~xcp/.config/counterblockd/counterblockd.log

Once it is fully synced up, you should be good to proceed. The next step is to simply open up a web browser, and
go to the IP address/hostname of the server. You will then be presented to accept your self-signed SSL certificate, and
after doing that, should see the Counterwallet login interface. From this point, you can proceed testing Counterblock/Counterwallet
functionality on your own system(s).


Getting a SSL Certificate
--------------------------

By default, the system is set up to use a self-signed SSL certificate. If you are hosting your services for others, 
you should get your own SSL certificate from your DNS registrar so that your users don't see a certificate warning when
they visit your site. Once you have that certificate, create a nginx-compatible ``.pem`` file, and place that
at ``/etc/ssl/certs/counterblockd.pem``. Then, place your SSL private key at ``/etc/ssl/private/counterblockd.key``.

After doing this, edit the ``/etc/nginx/sites-enabled/counterblock.conf`` file. Comment out the two development
SSL certificate lines, and uncomment the production SSL cert lines, like so::

    #SSL - For production use
    ssl_certificate      /etc/ssl/certs/counterblockd.pem;
    ssl_certificate_key  /etc/ssl/private/counterblockd.key;
  
    #SSL - For development use
    #ssl_certificate      /etc/ssl/certs/ssl-cert-snakeoil.pem;
    #ssl_certificate_key  /etc/ssl/private/ssl-cert-snakeoil.key;

Then restart nginx::

    sudo service nginx restart


Multi-Server Setups
------------------------------------

Counterwallet should work out-of-the-box in a scenario where you have a single Counterblock Federated Node that both hosts the
static site content, as well as the backend Counterblock API services. You will need to read and follow this section if any of the
following apply to your situation:

- You have more than one server hosting the content (i.e. javascript, html, css resources) and API services (backend ``counterblockd``, etc)
- Or, you have a different set of hosts hosting API services than those hosting the static site content
- Or, you are hosting the static site content on a CDN

In these situations, you need to create a small file called ``servers.json`` in the ``counterblock/`` directory.
This file will contain a valid JSON-formatted object, containing an array of all of your backend servers, as well as
a number of other site specific configuration properties. For example::

    { 
      "servers": [ "https://counterblock1.mydomain.com", "https://counterblock2.mydomain.com", "https://counterblock3.mydomain.com" ],
      "forceTestnet": true,
      "googleAnalyticsUA": "UA-48454783-2",
      "googleAnalyticsUA-testnet": "UA-48454783-4",
      "rollbarAccessToken": "39d23b5a512f4169c98fc922f0d1b121"
    }
  
As in the example above, each of the hosts in ``servers`` must have a "http://" or "https://" prefix (we strongly recommend using HTTPS),
and the strings must *not* end in a slash (just leave it off). The other properties are optional, and can be set if you
make use of these services.

Once done, save this file and make sure it exists on all servers you are hosting Counterwallet static content on. Now, when you go
to your Counterwallet site, the server will read in this file immediately after loading the page, and set the list of
backend API hosts from it automatically.


Troubleshooting
------------------------------------

If you experience issues with your Counterblock Federated Node, a good start is to check out the logs. Something like the following should work::

    #mainnet
    sudo tail -f ~xcp/.config/counterpartyd/counterpartyd.log
    sudo tail -f ~xcp/.config/counterblockd/countewalletd.log
    sudo tail -f ~xcp/.config/counterpartyd/api.error.log
    sudo tail -f ~xcp/.config/counterblockd/api.error.log

    #testnet
    sudo tail -f ~xcp/.config/counterpartyd-testnet/counterpartyd.log
    sudo tail -f ~xcp/.config/counterblockd-testnet/counterblockd.log
    sudo tail -f ~xcp/.config/counterpartyd-testnet/api.error.log
    sudo tail -f ~xcp/.config/counterblockd-testnet/api.error.log
    
    #relevant nginx logs
    sudo tail -f /var/log/nginx/counterblock.access.log
    sudo tail -f /var/log/nginx/counterblock.error.log

These logs should hopefully provide some useful information that will help you further diagnose your issue. You can also
keep tailing them (or use them with a log analysis tool like Splunk) to gain insight on the current
status of ``counterpartyd``/``counterblockd``.

Also, you can start up the daemons in the foreground, for easier debugging, using the following sets of commands::

    #mainnet
    sudo su -s /bin/bash -c 'counterpartyd --data-dir=/home/xcp/.config/counterpartyd' xcpd
    sudo su -s /bin/bash -c 'counterblockd --data-dir=/home/xcp/.config/counterblockd' xcpd
    
    #testnet
    sudo su -s /bin/bash -c 'counterpartyd --data-dir=/home/xcp/.config/counterpartyd-testnet --testnet' xcpd
    sudo su -s /bin/bash -c 'counterblockd --data-dir=/home/xcp/.config/counterblockd-testnet --testnet' xcpd

You can also run ``bitcoind`` commands directly, e.g.::

    #mainnet
    sudo su - xcpd -s /bin/bash -c "bitcoind -datadir=/home/xcp/.bitcoin getinfo"
    
    #testnet
    sudo su - xcpd -s /bin/bash -c "bitcoind -datadir=/home/xcp/.bitcoin-testnet getinfo"

Other Topics
--------------

User Configuration
^^^^^^^^^^^^^^^^^^^^

Note that when you set up a federated node, the script creates two new users on the system: ``xcp`` and ``xcpd``. (The
``xcp`` user also has an ``xcp`` group created for it as well.)

The script installs ``counterpartyd``, ``counterwallet``, etc into the home directory of the ``xcp`` user. This
user also owns all installed files. However, the daemons (i.e. ``bitcoind``, ``insight``, ``counterpartyd``,
``counterblockd``, and ``nginx``) are actually run as the ``xcpd`` user, which has no write access to the files
such as the ``counterwallet`` and ``counterpartyd`` source code files. The reason things are set up like this is so that
even if there is a horrible bug in one of the products that allows for a RCE (or Remote Control Exploit), where the attacker
would essentially be able to gain the ability to execute commands on the system as that user, two things should prevent this:

* The ``xcpd`` user doesn't actually have write access to any sensitive files on the server (beyond the log and database
  files for ``bitcoind``, ``counterpartyd``, etc.)
* The ``xcpd`` user uses ``/bin/false`` as its shell, which prevents the attacker from gaining shell-level access

This setup is such to minimize (and hopefully eliminate) the impact from any kind of potential system-level exploit.
 

Easy Updating
^^^^^^^^^^^^^^^^

To update the system with new ``counterpartyd``, ``counterblockd`` and ``counterwallet`` code releases, you simply need
to rerun the ``setup_federated_node`` script, like so::

    cd ~xcp/counterpartyd_build
    sudo ./setup_federated_node.py
    
As prompted, you should be able to choose just to Update, instead of to Rebuild. However, you would choose the Rebuild
option if there were updates to the ``counterpartyd_build`` system files for the federated node itself (such as the
``nginx`` configuration, or the init scripts) that you wanted/needed to apply. Otherwise, if there are just updates
to the daemons or ``counterwallet`` code itself, Update should be fine. 

Giving Op Chat Access
^^^^^^^^^^^^^^^^^^^^^^

Counterwallet has its own built-in chatbox. Users in the chat box are able to have operator (op) status, which allows them
to do things like ban or rename other users. Any op can give any other user op status via the ``/op`` command, typed into
the chat window. However, manual database-level intervention is required to give op status to the first op in the system.

Doing this, however, is simple. Here's an example that gives ``testuser1`` op access. It needs to be issued at the
command line for every node in the cluster::

    #mainnet
    mongo counterblockd
    db.chat_handles.update({handle: "testuser1"}, {$set: {op: true}})
    
    #testnet
    mongo counterblockd_testnet
    db.chat_handles.update({handle: "testuser1"}, {$set: {op: true}})

Monitoring the Server
----------------------

To monitor the server, you can use a 3rd-party service such as [Pingdom](http://www.pingdom.com) or [StatusCake](http://statuscake.com).
The federated node allows these (and any other monitoring service) to query the basic status of the server (e.g. the ``nginx``,
``counterblockd`` and ``counterpartyd`` services) via making a HTTP GET call to one of the following URLs:

* ``/_api/`` (for mainnet) 
* ``/_t_api/`` (for testnet)

If all services are up, a HTTP 200 response with the following data will be returned::

    {"counterpartyd": "OK", "counterblockd": "OK"}
    
If all services but ``counterpartyd`` are up, a HTTP 500 response with the following data will be returned::

    {"counterpartyd": "NOT OK", "counterblockd": "OK"}

If ``counterblockd`` is not working properly, ``nginx`` will return a HTTP 503 (Gateway unavailable) or 500 response.

If ``nginx`` is not working properly, either a HTTP 5xx response, or no response at all (i.e. timeout) will be returned.


MultiAPI specifics
-------------------

Counterwallet utilizes a sort of a "poor man's load balancing/failover" implementation called multiAPI (and implemented
[here](https://github.com/CounterpartyXCP/counterwallet/blob/master/src/js/util.api.js)). multiAPI can operate in a number of fashions.

**multiAPIFailover for Read API (``get_``) Operations**

*multiAPIFailover* functionality is currently used for all read API operations. In this model, the first Federated Node
on the shuffled list is called for the data, and if it returns an error or the request times out, the second one on the
list is called, and so on. The result of the first server to successfully return are used.

Here, a "hacked" server could be modified to return bogus data. As (until being discovered) the server would be in the
shuffled list, some clients may end up consulting it. However, as this functionality is essentially for data queries only,
the worse case result is that a Counterwallet client is shown incorrect/modified data which leads to misinformed actions
on the user's behalf. Moreover, the option always exists to move all read-queries to use multiAPIConsensus in the future should the need arise.

**multiAPIConsensus for Action/Write (``create_``) Operations**

Based on this multiAPI capability, the wallet itself consults more than one of these Federated Nodes via consensus especially
for all ``create_``-type operations. For example, if you send XCP, counterpartyd on each server is still composing and sending
back the unsigned raw transaction, but for data security, it compares the results returned from all servers, and will 
only sign and broadcast (both client-side) if all the results match). This is known as *multiAPIConsensus*.

The ultimate goal here is to have a federated net of semi-trusted backend servers not tied to any one country, provider, network or
operator/admin. Through requiring consensus on the unsigned transactions returned for all ``create_`` operations, 'semi-trust'
on a single server basis leads to an overall trustworthy network. Worst case, if backend server is hacked and owned
(and the counterpartyd code modified), then you may get some invalid read results, but it won't be rewriting your XCP send
destination address, for example. The attackers would have to hack the code on every single server in the same exact
way, undetected, to do that.

Moreover, the Counterwallet web client contains basic transaction validation code that will check that any unsigned Bitcoin
transaction returned from a Counterblock Federated Node contains expected inputs and outputs. This provides further
protection against potential attacks.

multiAPIConsensus actually helps discover any potential "hacked" servers as well, since a returned consensus set with
a divergent result will be rejected by the client, and thus trigger an examination of the root cause by the team.

**multiAPINewest for Redundant storage**

In the same way, these multiple servers are used to provide redundant storage of client-side preferences, to ensure we
have no single point of failure. In the case of the stored preferences for instance, when retrieved on login, the data from all servers
is taken in, and the newest result is used. This *multiAPINewest* functionality effectively makes a query across all available
Federated Nodes, and chooses the newest result (based on a "last updated"-type timestamp).

Note that with this, a "hacked" server could be modified to always return the latest timestamp, so that its results
were used. However, wallet preferences (and other data stored via this functionality) is non-sensitive, and thus user's
funds would not be at risk before the hacked server could be discovered and removed.

