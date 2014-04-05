Setting up a Counterwallet Federated Node
==============================================

.. note::

    The Counterparty team itself operates the primary Counterwallet platform. However, as Counterwallet is open source
    software, it is possible to host your own site with Counterwallet site (for your personal use, or as an offering to
    others), or to even host your own Counterwallet servers to use with your own Counterparty wallet implementation.
    The Counterparty team supports this kind of activity, as it aids with reducing network centralization.
    
    Also note that due to the nature of Counterwallet being a deterministic wallet, users using one Counterwallet platform (i.e. the
    official one, for instance) have the flexibility to start using a different Counterwallet platform instead at any time,
    and as funds (i.e. private keys) are not stored on the server in any fashion, they will be able to see their funds on either.
    (Note that the only thing that will not migrate are saved preferences, such as address aliases, the theme setting, etc.)

    The above being said, this document walks one though some of the inner workings of Counterwallet, as well as describing
    how one can set up their own Counterwallet server (i.e. Counterwallet Federated Node). That being said, this document
    is primarily intended for system administrators and developers.

Introduction & Theory
----------------------

The Counterwallet web-wallet implementation can work against one or more back-end servers.
Each backend server runs ``bitcoind``, ``insight``, ``counterpartyd``, and ``counterwalletd``, and exists as a fully self-contained
node. Counterwallet has multiple servers listed (in ``counterwallet.js``) which it can utilize in making API calls either
sequentially (i.e. failover) or in parallel (i.e. consensus-based). When a user logs in, this list is shuffled so that,
in aggregate, user requests are effectively load-balanced across available servers.

The nodes used by Counterwallet in this way are referred to as Federated Nodes, because they are self-contained and
independent, but (though special "multiAPI" functionality client-side) work together to provide services to Counterwallet users.  

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
transaction returned from a Counterwallet Federated Node contains expected inputs and outputs. This provides further
protection against potential attacks.

multiAPIConsensus actually helps discover any potential "hacked" servers as well, since a returned consensus set with
a divergent result will be rejected by the client, and thus trigger an examination of the root cause by the team.

**multiAPIFailover for Read API (``get_``) Operations**

*multiAPIFailover* functionality is currently used for all read API operations. In this model, the first Federated Node
on the shuffled list is called for the data, and if it returns an error or the request times out, the second one on the
list is called, and so on. The result of the first server to successfully return are used.

Here, a "hacked" server could be modified to return bogus data. As (until being discovered) the server would be in the
shuffled list, some clients may end up consulting it. However, as this functionality is essentially for data queries only,
the worse case result is that a Counterwallet client is shown incorrect/modified data which leads to misinformed actions
on the user's behalf. Moreover, the option always exists to move all read-queries to use multiAPIConsensus in the future should the need arise.

**multiAPINewest for Redundant storage**

In the same way, these multiple servers are used to provide redundant storage of client-side preferences, to ensure we
have no single point of failure. In the case of the stored preferences for instance, when retrieved on login, the data from all servers
is taken in, and the newest result is used. This *multiAPINewest* functionality effectively makes a query across all available
Federated Nodes, and chooses the newest result (based on a "last updated"-type timestamp).

Note that with this, a "hacked" server could be modified to always return the latest timestamp, so that its results
were used. However, wallet preferences (and other data stored via this functionality) is non-sensitive, and thus user's
funds would not be at risk before the hacked server could be discovered and removed.


Node Provisioning
------------------

Production
^^^^^^^^^^^^

Here are the recommendations and/or requirements when setting up a production-grade Counterwallet server:

**Server Hardware/Network Recommendations:**

- Xeon E3+ or similar-class processor
- 16GB+ RAM (ECC)
- 2x SSD 120GB+ drives in RAID-0 (mirrored) configuration
- Hosted in a secure data center with physical security and access controls
- DDOS protection recommended if you will be offering your service to others

**Server Software:**

- Ubuntu 13.10 64-bit required

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
- The system should have a proper hostname (e.g. counterwallet.myorganization.org), and your DNS provider should be DDOS resistant
- System timezone should be set to UTC
- Enable Ubuntu's  `automated security updates <http://askubuntu.com/a/204>`__
- If running multiple servers, consider other tweaks on a per-server basis to reduce homogeneity.  


Testing / Development
^^^^^^^^^^^^^^^^^^^^^^

If you'd like to set up a Counterwallet system for testing and development, the requirements are minimal. Basically you
need to set up a Virtual Machine (VM) instance (or hardware) with **Ubuntu 13.10 64-bit** and give it at least **2 GB** of memory.


Node Setup
-----------

Once the server is provisioned and set up as above, you will need to install all of the necessary software and dependencies. We have an
installation script for this, that is fully automated **and installs ALL dependencies, including ``bitcoind`` and ``insight``**::

    cd && wget -qO setup_federated_node.py https://raw.github.com/xnova/counterpartyd_build/develop/setup_federated_node.py
    sudo python3 setup_federated_node.py

Then just follow the on-screen prompts (choosing to build from *master* if you are building a production node,
or from *develop* **only** if you are a developer).

Once done, start up ``bitcoind`` daemon(s)::

    sudo service bitcoind start
    sudo service bitcoind-testnet start
    
    sudo tail -f ~xcp/.bitcoin/debug.log 

That last command will give you information on the Bitcoin blockchain download status. While the blockchain is
downloading, you can launch the ``insight`` daemon(s)::

    sudo service insight start
    sudo service insight-testnet start
    
    sudo tail -f ~xcp/insight-api/insight.log 

Then, watching this log, wait for the insight sync (as well as the bitcoind sync) to finish, which should take between 7 and 12 hours.
After this is all done, reboot the box for the new services to start (which includes ``counterpartyd`` and ``counterwalletd``).

Then, check on the status of ``counterpartyd`` and ``counterwalletd``'s sync with the blockchain using::

    sudo tail -f ~xcp/.config/counterpartyd/counterpartyd.log
    sudo tail -f ~xcp/.config/counterwalletd/countewalletd.log

Once both are fully synced up, you should be good to proceed. The next step is to simply open up a web browser, and
go to the IP address/hostname of the server. You will then be presented to accept your self-signed SSL certificate, and
after doing that, should see the Counterwallet login interface. From this point, you can proceed testing Counterwallet
functionality on your own system(s).


Getting a SSL Certificate
--------------------------

By default, the system is set up to use a self-signed SSL certificate. If you are hosting your services for others, 
you should get your own SSL certificate from your DNS registrar so that your users don't see a certificate warning when
they visit your site. Once you have that certificate, create a nginx-compatible ``.pem`` file, and place that
at ``/etc/ssl/certs/counterwallet.pem``. Then, place your SSL private key at ``/etc/ssl/private/counterwallet.key``.

After doing this, edit the ``/etc/nginx/sites-enabled/counterwallet.conf`` file. Comment out the two development
SSL certificate lines, and uncomment the production SSL cert lines, like so::

    #SSL - For production use
    ssl_certificate      /etc/ssl/certs/counterwallet.pem;
    ssl_certificate_key  /etc/ssl/private/counterwallet.key;
  
    #SSL - For development use
    #ssl_certificate      /etc/ssl/certs/ssl-cert-snakeoil.pem;
    #ssl_certificate_key  /etc/ssl/private/ssl-cert-snakeoil.key;

Then restart nginx::

    sudo service nginx restart


Multi-Server Setups
------------------------------------

Counterwallet should work out-of-the-box in a scenario where you have a single Counterwallet server that both hosts the
static site content, as well as the backend API services. You will need to read and follow this section if any of the
following apply to your situation:

- You have more than one server hosting the content (i.e. javascript, html, css resources) and API services (backend ``counterwalletd``, etc)
- Or, you have a different set of hosts hosting API services than those hosting the static site content
- Or, you are hosting the static site content on a CDN

In these situations, you need to create a small file called ``servers.json`` in the ``counterwallet/`` directory.
This file will contain a valid JSON-formatted object, containing an array of all of your backend servers, as well as
a number of other site specific configuration properties. For example::

    { 
      "servers": [ "https://counterwallet1.mydomain.com", "https://counterwallet2.mydomain.com", "https://counterwallet3.mydomain.com" ],
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

If you experience issues with your Counterwallet server, a good start is to check out the logs. Something like the following should work::

    #if for mainnet
    sudo tail -f ~xcp/.config/counterpartyd/counterpartyd.log
    sudo tail -f ~xcp/.config/counterwalletd/countewalletd.log
    sudo tail -f ~xcp/.config/counterpartyd/api.error.log
    sudo tail -f ~xcp/.config/counterwalletd/api.error.log

    #if for testnet
    sudo tail -f ~xcp/.config/counterpartyd-testnet/counterpartyd.log
    sudo tail -f ~xcp/.config/counterwalletd-testnet/counterwalletd.log
    sudo tail -f ~xcp/.config/counterpartyd-testnet/api.error.log
    sudo tail -f ~xcp/.config/counterwalletd-testnet/api.error.log

These logs should hopefully provide some useful information that will help you further diagnose your issue. You can also
keep tailing them (or use them with a log analysis tool like Splunk) to gain insight on the current
status of ``counterpartyd``/``counterwalletd``.
