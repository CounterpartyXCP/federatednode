Setting up a Counterwallet Federated Node
==============================================

.. note::

    The Counterparty team itself operates the primary Counterwallet website. However, as Counterwallet is open source
    software, it is possible to host your own Counterwallet-derived site, or host your own Counterwallet servers
    to use from your own Counterparty wallet implementation. 

    That being said, this document is intended for system administrators and developers who would like to do this.
    Suffice it to say, this is not something that normal end users will ever need to do.
    

Introduction & Theory
----------------------

Counterwallet (the primary Counterparty web-wallet implementation), can work against one or more back-end servers.
Each backend server runs ``bitcoind``, ``counterpartyd``, and ``counterwalletd``, and exists as a fully self-contained
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

The goal here is to have a federated net of semi-trusted backend servers not tied to any one country, provider, network or
operator/admin. Through requiring consensus on the unsigned transactions returned for all ``create_`` operations, 'semi-trust'
on a single server basis leads to an overall trustworthy network. Worst case, if backend server is hacked and owned
(and the counterpartyd code modified), then you may get some invalid read results, but it won't be rewriting your XCP send
destination address, for example. The attackers would have to hack the code on every single server in the same exact
way, undetected, to do that.

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

Here are the recommendations and/or requirements when setting up a Counterwallet server:

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
- The system should have a proper hostname (e.g. counterwallet.myorganization.org), and your DNS provider should be DDOS resistant
- System timezone should be set to UTC 


Node Setup
-----------

Once the server is provisioned and secured as above, you will need to install all of the necessary software. We have an
installation script for this, that is fully automated **and installs ALL dependencies, including ``bitcoind`` and ``insight``**::

    cd && wget -qO setup_federated_node.py https://raw.github.com/xnova/counterpartyd_build/master/setup_federated_node.py
    sudo python3 setup_federated_node.py

Then just follow the on-screen prompts, and once done, start up ``bitcoind`` daemon(s)::

    sudo service bitcoind start
    sudo service bitcoind-testnet start
    
    sudo tail -f ~xcp/.bitcoin/debug.log 

Watching the debug log, wait for the blockchain sync to complete. Once done, launch the ``insight`` daemon(s)::

    sudo service insight start
    sudo service insight-testnet start
    
    sudo tail -f ~xcp/insight-api/insight.log 

Then, watching this log, wait for the insight sync to finish. After this, reboot the box for the new services to start
(which will include ``counterpartyd`` and ``counterwalletd``).


Getting a SSL Certificate
--------------------------

By default, the system is set up to use a self-signed SSL certificate. If you are hosting your services for others, 
you should get your own SSL certificate from your DNS registrar (so that your users don't see a certificate warning when
they visit your site). Once you have that certificate, create a
nginx-compatible ``.pem`` file, and place that at ``/etc/ssl/certs/counterwallet.pem``. Then, place your SSL private key
at ``/etc/ssl/private/counterwallet.key``.

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


Connecting with Counterwallet
------------------------------------

For now, to run Counterwallet against your new servers, you will need to modify the `counterwallet.js <https://github.com/xnova/counterwallet/blob/develop/src/js/counterwallet.js>`__ file.
Search for the line that sets ``counterwalletd_urls`` for production mode (``!IS_DEV``) and modify to use your own hostnames.
Note that we recommend that you use hostnames so that the API communications can be SSL encrypted (since it appears that
IP address-based SSL certificates are being phased out).
