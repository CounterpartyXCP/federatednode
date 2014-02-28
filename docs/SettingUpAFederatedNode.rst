Setting up a Counterwallet Federated Node
==============================================

.. note::

    This document is intended for system and network administrators who would like to set up their own Counterwallet
    node to add to the Counterwallet federated backend network. This is not something that end users will ever need to do.
    
    If you would like to host a Federated Node, please contact `dev@counterwallet.co <dev@counterwallet.co>`__
    **before** doing so to get pre-approved. Pre-approval will be granted on a case-by-case basis and depend on a
    variety of factors, such as trustworthyness, network and server infrastructure capabilities, level of comittment,
    country of residence, and more.
    

Introduction
-------------

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

To set up a Federated Node, we require the following:

**Server Hardware/Network:**

- Xeon E5+ or similar-class processor
- 64GB+ RAM (ECC)
- 2x SSD 120GB+ drives in RAID-0 (mirrored) configuration
- Hosted in a secure data center with physical security and access controls
- DDOS protection (1gbps absolute minimum) required, via reverse proxy, GRE tunnel, or other means

**Server Software:**

- Ubuntu 13.10 64-bit

**Server Security:**

`This link <http://www.thefanclub.co.za/how-to/how-secure-ubuntu-1204-lts-server-part-1-basics>`__ is a good starting point
Specifically, see steps 1 through 5, 7, 12, and 13 though 17.

Some notes:

- SSH should run on a different port, with root access disabled
- Use iptables/ufw (software firewall) in addition to any hardware firewalls
- Utilize ``fail2ban``, ``psad``, ``chkrootkit`` and ``rkhunter``
- Utilize modified ``sysctl`` settings for improved security and DDOS protection 
- Only one or two trusted individuals should have access to the box. All root access through ``sudo``.
- The system should have a proper hostname (e.g. counterwallet.myorganization.org), and your DNS provider should be DDOS resistant. 


Node Setup
-----------

Once the server is provisioned and secured as above, you will need to set it up as a Federated Node. We have an automated
installation script for this::

    wget -qO setup_federated_node.py https://raw.github.com/xnova/counterpartyd_build/master/setup_federated_node.py
    sudo python3 setup_federated_node.py
    
    #or, if running the develop branch:
    wget -qO setup_federated_node.py https://raw.github.com/xnova/counterpartyd_build/develop/setup_federated_node.py
    sudo python3 setup_federated_node.py -b develop

The script is fully automated. Once done, reboot the box for the new services to start.


Getting a SSL Certificate
--------------------------

By default, the system is set up to use a self-signed SSL certificate. If you'd like your server to be listed as a
Counterwallet Federated Node, you will need to purchase a SSL certificate. Once you have that certificate, create an
Nginx-compatible ``.pem`` file, and place that at ``/etc/ssl/certs/counterwallet.pem``. Then, place your SSL private key
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


Getting Your Node Listed
---------------------------

Contact `dev@counterwallet.co <dev@counterwallet.co>`__, we will examine your server setup and place you on the 
Federated Node list in Counterwallet if everything checks out.

In order to keep your Federated Node in the list, you will need to:

- Remain in good standing as an honest member of the community
- Maintain your server and server infrastructure
- Install any necessary updates you are notified about in a timely manner
- Demonstrate a high level of uptime and availability
