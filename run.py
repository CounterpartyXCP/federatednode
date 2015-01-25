#! /usr/bin/env python3
"""
Sets up an Ubuntu 14.04 x64 server to be a Counterblock Federated Node.

NOTE: The system should be properly secured before running this script.

TODO: This is admittedly a (bit of a) hack. In the future, take this kind of functionality out to a .deb with
      a postinst script to do all of this, possibly.
"""
import os
import sys
import re
import time
import getopt
import logging
import shutil
import socket
import urllib
import zipfile
import platform
import collections
import tempfile
import subprocess

try: #ignore import errors on windows
    import pwd
    import grp
except ImportError:
    pass

from setup_util import *

USERNAME = "xcp"
DAEMON_USERNAME = "xcpd"
USER_HOMEDIR = "/home/xcp"
QUESTION_FLAGS = collections.OrderedDict({
    "op": ('u', 'r'),
    "role": ('counterwallet', 'counterparty-server_only', 'counterblock_basic'),
    "branch": ('master', 'develop'),
    "run_mode": ('t', 'm', 'b'),
    "security_hardening": ('y', 'n'),
    "counterparty-server_public": ('y', 'n'),
    "counterwallet_support_email": None,
    "autostart_services": ('y', 'n'),
})
PYTHON3_VER = None

def remove_old():
    "remove old things from the previous counterpartyd_build system"
    #program links/executiables
    runcmd("rm -f /usr/local/bin/counterpartyd /usr/local/bin/counterblockd /usr/local/bin/armory_utxsvr")
    #runit entries
    def remove_runit(service_name):
        runcmd("rm -f /etc/service/%s" % service_name)
        runcmd("rm -rf /etc/sv/%s" % service_name)
    for service_name in ("counterpartyd", "counterpartyd-testnet", "counterblockd",
                         "counterblockd-testnet", "armory_utxsvr", "armory_utxsvr-testnet"):
        remove_runit(service_name)

def get_base_paths():
    paths = {}
    paths['sys_python_path'] = os.path.dirname(sys.executable)
    paths['base_path'] = os.path.normpath(os.path.dirname(os.path.realpath(sys.argv[0])))
    #^ the dir of where counterparty source was downloaded to
    #find the location of the virtualenv command and make sure it exists
    paths['virtualenv_path'] = "/usr/bin/virtualenv"
    paths['virtualenv_args'] = "--system-site-packages --python=python%s" % PYTHON3_VER
    #compose the rest of the paths...
    paths['dist_path'] = os.path.join(paths['base_path'], "dist")
    paths['env_path'] = os.path.join(paths['base_path'], "env") # home for the virtual environment
    paths['bin_path'] = os.path.join(paths['base_path'], "bin")
    #the pip executable that we'll be using does not exist yet, but it will, once we've created the virtualenv
    paths['pip_path'] = os.path.join(paths['env_path'], "bin", "pip")
    paths['python_path'] = os.path.join(paths['env_path'], "bin", "python3")

    #for now, counterblockd currently uses Python 2.7 due to gevent-socketio's lack of support for Python 3
    #because of this, it needs its own virtual environment
    paths['virtualenv_args.counterblock'] = "--system-site-packages --python=python2.7"
    paths['env_path.counterblock'] = os.path.join(paths['base_path'], "env.counterblock") # home for the virtual environment
    paths['pip_path.counterblock'] = os.path.join(paths['env_path.counterblock'], "bin", "pip")
    paths['python_path.counterblock'] = os.path.join(paths['env_path.counterblock'], "bin", "python")
    
    return paths

def do_base_setup(run_as_user, branch):
    """This creates the xcp and xcpd users and checks out the counterpartyd_build system from git"""
    #change time to UTC
    runcmd("ln -sf /usr/share/zoneinfo/UTC /etc/localtime")

    #install some necessary base deps
    runcmd("apt-get update")
    runcmd("apt-get -y install git-core software-properties-common python-software-properties build-essential ssl-cert ntp runit curl")
    
    #install node-js
    #node-gyp building has ...issues out of the box on Ubuntu... use Chris Lea's nodejs build instead, which is newer
    runcmd("apt-get -y remove nodejs npm gyp")
    runcmd("add-apt-repository -y ppa:chris-lea/node.js")
    runcmd("apt-get update")
    runcmd("apt-get -y install nodejs") #includes npm
    gypdir = None
    try:
        import gyp
        gypdir = os.path.dirname(gyp.__file__)
    except:
        pass
    else:
        runcmd("mv %s %s_bkup" % (gypdir, gypdir))
        #^ fix for https://github.com/TooTallNate/node-gyp/issues/363

    #Create xcp user, under which the files will be stored, and who will own the files, etc
    try:
        pwd.getpwnam(USERNAME)
    except:
        logging.info("Creating user '%s' ..." % USERNAME)
        runcmd("adduser --system --disabled-password --shell /bin/false --group %s" % USERNAME)
    #Create xcpd user (to run counterpartyd, counterblockd, bitcoind, nginx) if not already made
    try:
        pwd.getpwnam(DAEMON_USERNAME)
    except:
        logging.info("Creating user '%s' ..." % DAEMON_USERNAME)
        runcmd("adduser --system --disabled-password --shell /bin/false --ingroup nogroup --home %s %s"
            % (USER_HOMEDIR, DAEMON_USERNAME))
    
    #add the run_as_user to the xcp group
    runcmd("adduser %s %s" % (run_as_user, USERNAME))
    
    #Check out counterpartyd-build repo under this user's home dir and use that for the build
    git_repo_clone("counterpartyd_build", "https://github.com/CounterpartyXCP/counterpartyd_build.git",
        os.path.join(USER_HOMEDIR, "counterpartyd_build"), branch, for_user=run_as_user)

    #enhance fd limits for the xcpd user
    runcmd("cp -af %s/linux/other/xcpd_security_limits.conf /etc/security/limits.d/" % dist_path)

def do_backend_rpc_setup(run_as_user, branch, base_path, dist_path, run_mode):
    """Installs and configures bitcoind"""
    backend_rpc_password = pass_generator()
    backend_rpc_password_testnet = pass_generator()

    #Install deps (see https://help.ubuntu.com/community/bitcoin)
    runcmd("apt-get -y install build-essential libtool autotools-dev autoconf pkg-config libssl-dev libboost-dev libboost-all-dev software-properties-common checkinstall")
    runcmd("add-apt-repository -y ppa:bitcoin/bitcoin")
    runcmd("apt-get update")
    runcmd("apt-get -y install libdb4.8-dev libdb4.8++-dev")
    
    #Install bitcoind (btcbrak's 0.10.0 addrindex branch)
    BITCOIND_VERSION="0.10-rc2"
    BITCOIND_DEB_VERSION="0.10.0-2"
    runcmd("sudo apt-get -y remove bitcoin.addrindex", abort_on_failure=False) #remove old version if it exists
    runcmd("rm -rf /tmp/bitcoin-addrindex-%s" % BITCOIND_VERSION)
    runcmd("wget -O /tmp/bitcoin-addrindex-%s.tar.gz https://github.com/btcdrak/bitcoin/archive/addrindex-%s.tar.gz"
        % (BITCOIND_VERSION, BITCOIND_VERSION))
    runcmd("cd /tmp && tar -zxvf /tmp/bitcoin-addrindex-%s.tar.gz" % BITCOIND_VERSION)
    runcmd("cd /tmp/bitcoin-addrindex-%s && ./autogen.sh && ./configure --without-gui && make && sudo checkinstall -y -D --install --pkgversion=%s"
        % (BITCOIND_VERSION, BITCOIND_DEB_VERSION))
    runcmd("rm -rf /tmp/bitcoin-addrindex-%s" % BITCOIND_VERSION)
    runcmd("ln -sf /usr/local/bin/bitcoind /usr/bin/bitcoind && ln -sf /usr/local/bin/bitcoin-cli /usr/bin/bitcoin-cli")

    #Do basic inital bitcoin config (for both testnet and mainnet)
    runcmd("mkdir -p ~%s/.bitcoin ~%s/.bitcoin-testnet" % (USERNAME, USERNAME))
    if not os.path.exists(os.path.join(USER_HOMEDIR, '.bitcoin', 'bitcoin.conf')):
        runcmd(r"""bash -c 'echo -e "rpcuser=rpc\nrpcpassword=%s\nserver=1\ndaemon=1\nrpcthreads=1000\nrpctimeout=300\ntxindex=1\naddrindex=1" > ~%s/.bitcoin/bitcoin.conf'""" % (
            backend_rpc_password, USERNAME))
    else: #grab the existing RPC password
        backend_rpc_password = subprocess.check_output(
            r"""bash -c "cat ~%s/.bitcoin/bitcoin.conf | sed -n 's/.*rpcpassword=\([^ \n]*\).*/\1/p'" """ % USERNAME, shell=True).strip().decode('utf-8')
    if not os.path.exists(os.path.join(USER_HOMEDIR, '.bitcoin-testnet', 'bitcoin.conf')):
        runcmd(r"""bash -c 'echo -e "rpcuser=rpc\nrpcpassword=%s\nserver=1\ndaemon=1\nrpcthreads=1000\nrpctimeout=300\ntxindex=1\naddrindex=1\ntestnet=1" > ~%s/.bitcoin-testnet/bitcoin.conf'""" % (
            backend_rpc_password_testnet, USERNAME))
    else:
        backend_rpc_password_testnet = subprocess.check_output(
            r"""bash -c "cat ~%s/.bitcoin-testnet/bitcoin.conf | sed -n 's/.*rpcpassword=\([^ \n]*\).*/\1/p'" """
            % USERNAME, shell=True).strip().decode('utf-8')

    #remove pyrpcwallet startup scripts if present
    runcmd("rm -f /etc/service/pyrpcwallet /etc/service/pyrpcwallet-testnet")
    #install logrotate file
    runcmd("cp -dRf --preserve=mode %s/linux/logrotate/bitcoind /etc/logrotate.d/bitcoind" % dist_path)
    #set permissions
    runcmd("chown -R %s:%s ~%s/.bitcoin ~%s/.bitcoin-testnet" % (DAEMON_USERNAME, USERNAME, USERNAME, USERNAME))
    #set up runit startup scripts
    config_runit_for_service(dist_path, "bitcoind", enabled=run_mode in ['m', 'b'])
    config_runit_for_service(dist_path, "bitcoind-testnet", enabled=run_mode in ['t', 'b'])
    
    return backend_rpc_password, backend_rpc_password_testnet

def do_counterparty_setup(role, run_as_user, branch, base_path, dist_path, run_mode, backend_rpc_password,
backend_rpc_password_testnet, counterparty-server_public, counterwallet_support_email):
    """Installs and configures counterpartyd and counterblockd"""
    
    paths = get_base_paths()
    with_counterblock = role != "counterparty-server_only"
    with_mainnet = run_mode in ['m', 'b']
    with_testnet = run_mode in ['t', 'b']
    
    def install_dependencies():
        assert os.name == "posix" and platform.dist()[0] == "Ubuntu" and ubuntu_release == "14.04"
        ubuntu_release = platform.linux_distribution()[1]
        logging.info("UBUNTU LINUX %s: Installing Required Packages..." % ubuntu_release) 
        runcmd("apt-get -y update")
        runcmd("apt-get -y install runit software-properties-common python-software-properties git-core wget \
        python3 python3-setuptools python3-dev python3-pip build-essential python3-sphinx python-virtualenv libsqlite3-dev python3-apsw python3-zmq")
        
        if with_counterblock:
            #counterblockd currently uses Python 2.7 due to gevent-socketio's lack of support for Python 3
            runcmd("apt-get -y install python python-dev python-setuptools python-pip python-sphinx python-zmq libzmq3 libzmq3-dev libxml2-dev libxslt-dev zlib1g-dev libimage-exiftool-perl libevent-dev cython")
    
            #install mongo-10gen (newer than what ubuntu has), pegged to a specific version
            MONGO_VERSION = "2.6.6"
            runcmd("apt-get -y remove mongodb mongodb-server") #remove ubuntu stock packages, if installed
            runcmd("apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv 7F0CEB10")
            runcmd("/bin/bash -c \"echo 'deb http://downloads-distro.mongodb.org/repo/ubuntu-upstart dist 10gen' | sudo tee /etc/apt/sources.list.d/mongodb.list\"")
            runcmd("apt-get update")
            runcmd("apt-get -y --force-yes install mongodb-org=%s mongodb-org-server=%s mongodb-org-shell=%s mongodb-org-mongos=%s mongodb-org-tools=%s" % (
                MONGO_VERSION, MONGO_VERSION, MONGO_VERSION, MONGO_VERSION, MONGO_VERSION))
            for p in ('mongodb-org', 'mongodb-org-server', 'mongodb-org-shell', 'mongodb-org-mongos', 'mongodb-org-tools'):
                runcmd("echo \"%s hold\" | sudo dpkg --set-selections" % p)
            #replace use of mongo init script with our runit version
            runcmd("""bash -c "echo 'manual' > /etc/init/mongod.override" """)
            runcmd("service mongod stop", abort_on_failure=False)
            config_runit_for_service(paths['dist_path'], "mongod", manual_control=False)
    
            #also install redis
            runcmd("apt-get -y install redis-server")
        #install sqlite utilities (not technically required, but nice to have)
        runcmd("apt-get -y install sqlite sqlite3 libleveldb-dev")
        #now that pip is installed, install necessary deps outside of the virtualenv (e.g. for this script)
        runcmd("pip3 install appdirs==1.4.0 progressbar33")
    
    def create_virtualenv():
        def create_venv(env_path, pip_path, python_path, virtualenv_args, delete_if_exists=True):
            if paths['virtualenv_path'] is None or not os.path.exists(paths['virtualenv_path']):
                logging.debug("ERROR: virtualenv missing (%s)" % (paths['virtualenv_path'],))
                sys.exit(1)
            
            if delete_if_exists and os.path.exists(env_path):
                logging.warning("Deleting existing virtualenv...")
                rmtree(env_path)
            assert not os.path.exists(os.path.join(env_path, 'bin'))
            logging.info("Creating virtualenv at '%s' ..." % env_path)
            runcmd("%s %s %s" % (paths['virtualenv_path'], virtualenv_args, env_path))
            
            #pip should now exist
            if not os.path.exists(pip_path):
                logging.error("pip does not exist at path '%s'" % pip_path)
                sys.exit(1)
    
        create_venv(paths['env_path'], paths['pip_path'], paths['python_path'], paths['virtualenv_args']) 
        if with_counterblock:
            #as counterblockd uses python 2.x, it needs its own virtualenv
            runcmd("rm -rf %s && mkdir -p %s" % (paths['env_path.counterblock'], paths['env_path.counterblock']))
            create_venv(paths['env_path.counterblock'], paths['pip_path.counterblock'], paths['python_path.counterblock'],
                paths['virtualenv_args.counterblock'], delete_if_exists=False)   
    
    def install_via_pip():
        #pip install counterparty-cli, counterparty-lib and (optionally) counterblock for the chosen branch
        PIP_COUNTERPARTY_LIB = "https://github.com/CounterpartyXCP/counterpartyd/archive/%s.zip" % branch
        PIP_COUNTERPARTY_CLI = "https://github.com/CounterpartyXCP/counterparty-cli/archive/%s.zip" % branch  
        PIP_COUNTERBLOCK = "https://github.com/CounterpartyXCP/counterblock/archive/%s.zip" % branch
        runcmd("sudo su -s /bin/bash -c '%s install %s' %s" % (paths['pip_path'], PIP_COUNTERPARTY_LIB, DAEMON_USERNAME))
        runcmd("sudo su -s /bin/bash -c '%s install %s' %s" % (paths['pip_path'], PIP_COUNTERPARTY_CLI, DAEMON_USERNAME))
        if with_counterblock:
            runcmd("sudo su -s /bin/bash -c '%s install %s' %s" % (paths['pip_path.counterblockd'], PIP_COUNTERBLOCK, DAEMON_USERNAME))

    def create_default_config(with_bootstrap_db):
        DEFAULT_CONFIG = "[Default]\nbackend-connect=localhost\nbackend-port=8332\nbackend-user=rpc\nbackend-password=1234\nrpc-host=localhost\nrpc-port=4000\nrpc-user=rpc\nrpc-password=xcppw1234\n"
        DEFAULT_CONFIG_TESTNET = "[Default]\nbackend-connect=localhost\nbackend-port=18332\nbackend-user=rpc\nbackend-password=1234\nrpc-host=localhost\nrpc-port=14000\nrpc-user=rpc\nrpc-password=xcppw1234\ntestnet=1\n"
        DEFAULT_CONFIG_COUNTERBLOCK = "[Default]\nbackend-connect=localhost\nbackend-port=8332\nbackend-user=rpc\nbackend-password=1234\ncounterparty-host=localhost\ncounterparty-port=4000\ncounterparty-user=rpc\ncounterparty-password=xcppw1234\nrpc-host=0.0.0.0\nsocketio-host=0.0.0.0\nsocketio-chat-host=0.0.0.0\nredis-enable-apicache=0\n"
        DEFAULT_CONFIG_COUNTERBLOCK_TESTNET = "[Default]\nbackend-connect=localhost\nbackend-port=18332\nbackend-user=rpc\nbackend-password=1234\ncounterparty-host=localhost\ncounterparty-port=14000\ncounterparty-user=rpc\ncounterparty-password=xcppw1234\nrpc-host=0.0.0.0\nsocketio-host=0.0.0.0\nsocketio-chat-host=0.0.0.0\nredis-enable-apicache=0\ntestnet=1\n"
    
        def create_config(appname, default_config):
            import appdirs #installed earlier
            cfg_dir = appdirs.user_config_dir(appauthor='Counterparty', appname='counterparty-server', roaming=True)
            cfg_path = os.path.join(cfg_dir, 'counterparty-server.conf')
    
            if not os.path.exists(cfg_dir):
                os.makedirs(cfg_dir)
            
            cfg_missing = not os.path.exists(cfg_path)
            if not os.path.exists(cfg_path):
                logging.info("Creating new configuration file at: %s" % cfg_path)
                #create a default config file
                cfg = open(cfg_path, 'w')
                cfg.write(default_config)
                cfg.close()
                #set permissions
                uid = pwd.getpwnam(run_as_user).pw_uid
                gid = grp.getgrnam(run_as_user).gr_gid    
                #set directory ownership
                os.chown(cfg_dir, uid, gid)
                #set proper file ownership and mode
                os.chown(cfg_path, uid, gid)
                os.chmod(cfg_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP) #660
                logging.info("NOTE: %s config file has been created at '%s'" % (appname, cfg_path))
            else:
                logging.info("%s config file already exists at: '%s'" % (appname, cfg_path))
                
            if appname in ("counterpartyd", "counterpartyd-testnet") and cfg_missing and with_bootstrap_db:
                fetch_counterpartyd_bootstrap_db(cfg_dir, testnet=appname=="counterpartyd-testnet")
        
        create_config('counterparty', DEFAULT_CONFIG)
        if with_testnet:
            create_config('counterparty-testnet', DEFAULT_CONFIG_TESTNET)
        if with_counterblockd:
            create_config('counterblock', DEFAULT_CONFIG_COUNTERBLOCK)
            if with_testnet:
                create_config('counterblock-testnet', DEFAULT_CONFIG_COUNTERBLOCK_TESTNET)

    def alter_config():
        #modify out configuration values as necessary
        counterpartyd_rpc_password = '1234' if role == 'counterparty-server_only' and counterparty-server_public == 'y' else pass_generator()
        counterpartyd_rpc_password_testnet = '1234' if role == 'counterparty-server_only' and counterparty-server_public == 'y' else pass_generator()
        for net, backend_password, cp_password in (
            ('mainnet', backend_rpc_password, counterpartyd_rpc_password),
            ('testnet', backend_rpc_password_testnet, counterpartyd_rpc_password_testnet)):
            #modify the default stored bitcoind passwords in counterparty conf
            modify_cp_config(r'^(backend\-rpc|backend)\-password=.*?$',
                'backend-rpc-password=%s' % backend_password, config='counterpartyd', net=net, for_user=USERNAME)
            #modify the counterpartyd API rpc password in counterparty conf
            modify_cp_config(r'^rpc\-password=.*?$', 'rpc-password=%s' % cp_password,
                config='counterpartyd', net=net, for_user=USERNAME)
            #backend for counterpartyd should be addrindex
            modify_cp_config(r'^(blockchain\-service|backend)\-name=.*?$', 'backend-name=addrindex',
                config='counterpartyd', net=net, for_user=USERNAME)
    
            if role == 'counterparty-server_only' and counterparty-server_public == 'y':
                modify_cp_config(r'^rpc\-host=.*?$', 'rpc-host=0.0.0.0', config='counterpartyd', net=net, for_user=USERNAME)
                
            if with_counterblock:
                modify_cp_config(r'^(backend\-rpc|backend)\-password=.*?$',
                    'backend-password=%s' % backend_password, config='counterblockd', net=net, for_user=USERNAME)
                #modify the counterpartyd API rpc password in counterblockd.conf
                modify_cp_config(r'^counterparty\-password=.*?$',
                    'counterparty-password=%s' % cp_password, config='counterblockd', net=net, for_user=USERNAME)
            
                #role-specific counterblockd.conf values
                modify_cp_config(r'^armory\-utxsvr\-enable=.*?$', 'armory-utxsvr-enable=%s' % 
                    ('1' if role == 'counterwallet' else '0'), config='counterblockd', for_user=USERNAME)
                if role == 'counterwallet':
                    modify_cp_config(r'^support\-email=.*?$', 'support-email=%s' % counterwallet_support_email,
                        config='counterblockd', for_user=USERNAME) #may be blank string

    def configure_startup(start_on_boot):
        #link over counterparty and counterblock script
        runcmd("ln -sf %s/bin/counterparty-server /usr/local/bin/counterparty-server" % paths['env_path'])
        runcmd("ln -sf %s/bin/counterparty-cli /usr/local/bin/counterparty-cli" % paths['env_path'])
        if with_counterblock:
            runcmd("ln -sf %s/bin/counterblock /usr/local/bin/counterblock" % paths['env_path.counterblock'])
    
            #create armory_utxsvr script
            f = open("/usr/local/bin/armory_utxsvr", 'w')
            f.write("#!/bin/sh\nDISPLAY=localhost:1.0 xvfb-run --auto-servernum %s/bin/armory_utxsvr \"$@\""
                % paths['env_path.counterblock'])
            f.close()
            runcmd("chmod +x /usr/local/bin/armory_utxsvr")

        config_runit_for_service(paths['dist_path'], "counterparty", manual_control=not start_on_boot)
        config_runit_for_service(paths['dist_path'], "counterparty-testnet",
            enabled=with_testnet, manual_control=not start_on_boot)
        config_runit_for_service(paths['dist_path'], "counterblock", enabled=with_counterblock,
            manual_control=not start_on_boot)
        config_runit_for_service(paths['dist_path'], "counterblock-testnet",
            enabled=with_counterblock and with_testnet, manual_control=not start_on_boot)

        #disable upstart scripts from autostarting on system boot if necessary
        if not with_mainnet:
            runcmd("rm -f /etc/service/counterpartyd")
        if not with_testnet:
            runcmd("rm -f /etc/service/counterpartyd-testnet")
        if with_counterblock and not with_mainnet:
           runcmd("rm -f /etc/service/counterblockd")
        if with_counterblock and not with_testnet:
           runcmd("rm -f /etc/service/counterblockd-testnet")
           
    install_dependencies()
    create_virtualenv()
    install_via_pip()
    create_default_config(True)
    alter_config()
    configure_startup(answered_questions['autostart_services'] == 'y')

def do_nginx_setup(run_as_user, base_path, dist_path, enable=True):
    if not enable:
        runcmd("apt-get -y remove nginx-openresty", abort_on_failure=False)
        return
    
    #Build and install nginx (openresty) on Ubuntu
    #Most of these build commands from http://brian.akins.org/blog/2013/03/19/building-openresty-on-ubuntu/
    OPENRESTY_VER = "1.7.7.1"

    #uninstall nginx if already present
    runcmd("apt-get -y remove nginx")
    #install deps
    runcmd("apt-get -y install make ruby1.9.1 ruby1.9.1-dev git-core libpcre3-dev libxslt1-dev libgd2-xpm-dev libgeoip-dev unzip zip build-essential libssl-dev")
    runcmd("gem install fpm")
    #grab openresty and compile
    runcmd("rm -rf /tmp/openresty /tmp/ngx_openresty-* /tmp/nginx-openresty.tar.gz /tmp/nginx-openresty*.deb")
    runcmd('''wget -O /tmp/nginx-openresty.tar.gz http://openresty.org/download/ngx_openresty-%s.tar.gz''' % OPENRESTY_VER)
    runcmd("tar -C /tmp -zxvf /tmp/nginx-openresty.tar.gz")
    runcmd('''cd /tmp/ngx_openresty-%s && ./configure \
--with-luajit \
--sbin-path=/usr/sbin/nginx \
--conf-path=/etc/nginx/nginx.conf \
--error-log-path=/var/log/nginx/error.log \
--http-client-body-temp-path=/var/lib/nginx/body \
--http-fastcgi-temp-path=/var/lib/nginx/fastcgi \
--http-log-path=/var/log/nginx/access.log \
--http-proxy-temp-path=/var/lib/nginx/proxy \
--http-scgi-temp-path=/var/lib/nginx/scgi \
--http-uwsgi-temp-path=/var/lib/nginx/uwsgi \
--lock-path=/var/lock/nginx.lock \
--pid-path=/var/run/nginx.pid \
--with-http_geoip_module \
--with-http_gzip_static_module \
--with-http_realip_module \
--with-http_ssl_module \
--with-http_sub_module \
--with-http_xslt_module \
--with-ipv6 \
--with-sha1=/usr/include/openssl \
--with-md5=/usr/include/openssl \
--with-http_stub_status_module \
--with-http_secure_link_module \
--with-http_sub_module && make''' % OPENRESTY_VER)
    #set up the build environment
    runcmd('''cd /tmp/ngx_openresty-%s && make install DESTDIR=/tmp/openresty \
&& mkdir -p /tmp/openresty/var/lib/nginx \
&& install -m 0755 -D %s/linux/runit/nginx/run /tmp/openresty/etc/sv/nginx/run \
&& install -m 0755 -D %s/linux/nginx/nginx.conf /tmp/openresty/etc/nginx/nginx.conf \
&& install -m 0755 -D %s/linux/nginx/counterblock.conf /tmp/openresty/etc/nginx/sites-enabled/counterblock.conf \
&& install -m 0755 -D %s/linux/nginx/counterblock_api.inc /tmp/openresty/etc/nginx/sites-enabled/counterblock_api.inc \
&& install -m 0755 -D %s/linux/nginx/counterblock_api_cache.inc /tmp/openresty/etc/nginx/sites-enabled/counterblock_api_cache.inc \
&& install -m 0755 -D %s/linux/nginx/counterblock_socketio.inc /tmp/openresty/etc/nginx/sites-enabled/counterblock_socketio.inc \
&& install -m 0755 -D %s/linux/logrotate/nginx /tmp/openresty/etc/logrotate.d/nginx''' % (
    OPENRESTY_VER, dist_path, dist_path, dist_path, dist_path, dist_path, dist_path, dist_path))
    #package it up using fpm
    runcmd('''cd /tmp && fpm -s dir -t deb -n nginx-openresty -v %s --iteration 1 -C /tmp/openresty \
--description "openresty %s" \
--conflicts nginx \
--conflicts nginx-common \
-d libxslt1.1 \
-d libgeoip1 \
-d geoip-database \
-d libpcre3 \
--config-files /etc/nginx/nginx.conf \
--config-files /etc/nginx/sites-enabled/counterblock.conf \
--config-files /etc/nginx/fastcgi.conf.default \
--config-files /etc/nginx/win-utf \
--config-files /etc/nginx/fastcgi_params \
--config-files /etc/nginx/nginx.conf \
--config-files /etc/nginx/koi-win \
--config-files /etc/nginx/nginx.conf.default \
--config-files /etc/nginx/mime.types.default \
--config-files /etc/nginx/koi-utf \
--config-files /etc/nginx/uwsgi_params \
--config-files /etc/nginx/uwsgi_params.default \
--config-files /etc/nginx/fastcgi_params.default \
--config-files /etc/nginx/mime.types \
--config-files /etc/nginx/scgi_params.default \
--config-files /etc/nginx/scgi_params \
--config-files /etc/nginx/fastcgi.conf \
etc usr var''' % (OPENRESTY_VER, OPENRESTY_VER))
    #now install the .deb package that was created (along with its deps)
    runcmd("apt-get -y install libxslt1.1 libgeoip1 geoip-database libpcre3")
    runcmd("dpkg -i /tmp/nginx-openresty_%s-1_amd64.deb" % OPENRESTY_VER)
    #remove any .dpkg-old or .dpkg-dist files that might have been installed out of the nginx config dir
    runcmd("rm -f /etc/nginx/sites-enabled/*.dpkg-old /etc/nginx/sites-enabled/*.dpkg-dist")
    #clean up after ourselves
    runcmd("rm -rf /tmp/openresty /tmp/ngx_openresty-* /tmp/nginx-openresty.tar.gz /tmp/nginx-openresty*.deb")
    #set up init
    runcmd("ln -sf /etc/sv/nginx /etc/service/")

def do_armory_utxsvr_setup(run_as_user, base_path, dist_path, run_mode, enable=True):
    runcmd("apt-get -y install xvfb python-qt4 python-twisted python-psutil xdg-utils hicolor-icon-theme")
    ARMORY_VERSION = "0.92.3_ubuntu-64bit"
    if not os.path.exists("/tmp/armory_%s.deb" % ARMORY_VERSION):
        runcmd("wget -O /tmp/armory_%s.deb https://s3.amazonaws.com/bitcoinarmory-releases/armory_%s.deb"
            % (ARMORY_VERSION, ARMORY_VERSION))
    runcmd("mkdir -p /usr/share/desktop-directories/") #bug fix (see http://askubuntu.com/a/406015)
    runcmd("dpkg -i /tmp/armory_%s.deb" % ARMORY_VERSION)

    runcmd("mkdir -p ~%s/.armory ~%s/.armory/log ~%s/.armory/log-testnet" % (USERNAME, USERNAME, USERNAME))
    runcmd("chown -R %s:%s ~%s/.armory" % (DAEMON_USERNAME, USERNAME, USERNAME))
    
    runcmd("sudo ln -sf ~%s/.bitcoin-testnet/testnet3 ~%s/.bitcoin/" % (USERNAME, USERNAME))
    #^ ghetto hack, as armory has hardcoded dir settings in certain place
    
    #make a short script to launch armory_utxsvr
    f = open("/usr/local/bin/armory_utxsvr", 'w')
    f.write("#!/bin/sh\n%s/run.py armory_utxsvr \"$@\"" % base_path)
    f.close()
    runcmd("chmod +x /usr/local/bin/armory_utxsvr")

    #Set up upstart scripts (will be disabled later from autostarting on system startup if necessary)
    config_runit_for_service(dist_path, "armory_utxsvr", enabled=enable and run_mode in ['m', 'b'])
    config_runit_for_service(dist_path, "armory_utxsvr-testnet", enabled=enable and run_mode in ['t', 'b'])

def do_counterwallet_setup(run_as_user, branch, updateOnly=False):
    #check out counterwallet from git
    git_repo_clone("counterwallet", "https://github.com/CounterpartyXCP/counterwallet.git",
        os.path.join(USER_HOMEDIR, "counterwallet"), branch, for_user=run_as_user)
    if not updateOnly:
        runcmd("npm install -g grunt-cli bower")
    runcmd("cd ~%s/counterwallet/src && bower --allow-root --config.interactive=false install" % USERNAME)
    runcmd("cd ~%s/counterwallet && npm install" % USERNAME)
    runcmd("cd ~%s/counterwallet && grunt build --force" % USERNAME) #will generate the minified site
    runcmd("chown -R %s:%s ~%s/counterwallet" % (USERNAME, USERNAME, USERNAME)) #just in case
    runcmd("chmod -R u+rw,g+rw,o+r,o-w ~%s/counterwallet" % USERNAME) #just in case
    
def do_security_setup(run_as_user, branch, base_path, dist_path, enable=True):
    """Some helpful security-related tasks, to tighten up the box"""
    
    if not enable:
        #disable security setup if enabled
        runcmd("apt-get -y remove unattended-upgrades fail2ban psad rkhunter chkrootkit logwatch apparmor auditd iwatch")
        return
    
    #modify host.conf
    modify_config(r'^nospoof on$', 'nospoof on', '/etc/host.conf')
    
    #enable automatic security updates
    runcmd("apt-get -y install unattended-upgrades")
    runcmd('''bash -c "echo -e 'APT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";' > /etc/apt/apt.conf.d/20auto-upgrades" ''')
    runcmd("dpkg-reconfigure -fnoninteractive -plow unattended-upgrades")
    
    #sysctl
    runcmd("install -m 0644 -o root -g root -D %s/linux/other/sysctl_rules.conf /etc/sysctl.d/60-tweaks.conf" % dist_path)

    #set up fail2ban
    runcmd("apt-get -y install fail2ban")
    runcmd("install -m 0644 -o root -g root -D %s/linux/other/fail2ban.jail.conf /etc/fail2ban/jail.d/counterblock.conf" % dist_path)
    runcmd("service fail2ban restart")
    
    #set up psad
    runcmd("apt-get -y install psad")
    modify_config(r'^ENABLE_AUTO_IDS\s+?N;$', 'ENABLE_AUTO_IDS\tY;', '/etc/psad/psad.conf')
    modify_config(r'^ENABLE_AUTO_IDS_EMAILS\s+?Y;$', 'ENABLE_AUTO_IDS_EMAILS\tN;', '/etc/psad/psad.conf')
    for f in ['/etc/ufw/before.rules', '/etc/ufw/before6.rules']:
        modify_config(r'^# End required lines.*?# allow all on loopback$',
            '# End required lines\n\n#CUSTOM: for psad\n-A INPUT -j LOG\n-A FORWARD -j LOG\n\n# allow all on loopback',
            f, dotall=True)
    runcmd("psad -R && psad --sig-update")
    runcmd("service ufw restart")
    runcmd("service psad restart")
    
    #set up chkrootkit, rkhunter
    runcmd("apt-get -y install rkhunter chkrootkit")
    runcmd('bash -c "rkhunter --update; exit 0"')
    runcmd("rkhunter --propupd")
    runcmd('bash -c "rkhunter --check --sk; exit 0"')
    runcmd("rkhunter --propupd")
    
    #logwatch
    runcmd("apt-get -y install logwatch libdate-manip-perl")
    
    #apparmor
    runcmd("apt-get -y install apparmor apparmor-profiles")
    
    #auditd
    #note that auditd will need a reboot to fully apply the rules, due to it operating in "immutable mode" by default
    runcmd("apt-get -y install auditd audispd-plugins")
    runcmd("install -m 0640 -o root -g root -D %s/linux/other/audit.rules /etc/audit/rules.d/counterblock.rules" % dist_path)
    modify_config(r'^USE_AUGENRULES=.*?$', 'USE_AUGENRULES="yes"', '/etc/default/auditd')
    runcmd("service auditd restart")

    #iwatch
    runcmd("apt-get -y install iwatch")
    modify_config(r'^START_DAEMON=.*?$', 'START_DAEMON=true', '/etc/default/iwatch')
    runcmd("install -m 0644 -o root -g root -D %s/linux/other/iwatch.xml /etc/iwatch/iwatch.xml" % dist_path)
    modify_config(r'guard email="root@localhost"', 'guard email="noreply@%s"' % socket.gethostname(), '/etc/iwatch/iwatch.xml')
    runcmd("service iwatch restart")

def find_configured_services():
    services = ["bitcoind", "bitcoind-testnet", "counterpartyd", "counterpartyd-testnet",
        "counterblockd", "counterblockd-testnet", "armory_utxsvr", "armory_utxsvr-testnet"]
    configured_services = []
    for s in services:
        if os.path.exists("/etc/service/%s" % s):
            configured_services.append(s)
    return configured_services

def command_services(command, prompt=False):
    assert command in ("stop", "restart")
    
    if prompt:
        confirmation = ask_question("%s services? (y/N)" % command.capitalize(), ('y', 'n',), 'n')
        if confirmation == 'n':
            return False
    
    logging.warn("STOPPING SERVICES" if command == 'stop' else "RESTARTING SERVICES")
    
    if os.path.exists("/etc/init.d/iwatch"):
        runcmd("service iwatch %s" % command, abort_on_failure=False)
        
    configured_services = find_configured_services()
    for s in configured_services:
        runcmd("sv %s %s" % (command, s), abort_on_failure=False)
    return True

def gather_build_questions(answered_questions, noninteractive):
    if 'role' not in answered_questions and noninteractive:
        answered_questions['role'] = '1' 
    elif 'role' not in answered_questions:
        role = ask_question("Enter the number for the role you want to build:\n"
                + "\t1: Counterwallet server\n\t2: counterpartyd-only\n\t3: counterblockd basic (no Counterwallet)\n"
                + "Your choice",
            ('1', '2', '3'), '1')
        if role == '1':
            role = 'counterwallet'
            role_desc = "Counterwallet server"
        elif role == '2':
            role = 'counterparty-server_only'
            role_desc = "Counterpartyd server"
        elif role == '3':
            role = 'counterblock_basic'
            role_desc = "Basic counterblockd server"
        print("\tBuilding a %s" % role_desc)
        answered_questions['role'] = role
    assert answered_questions['role'] in QUESTION_FLAGS['role']

    if 'branch' not in answered_questions and noninteractive:
        answered_questions['branch'] = 'master' 
    elif 'branch' not in answered_questions:
        branch = ask_question("Build from branch (M)aster or (d)evelop? (M/d)", ('m', 'd'), 'm')
        if branch == 'm': branch = 'master'
        elif branch == 'd': branch = 'develop'
        print("\tWorking with branch: %s" % branch)
        answered_questions['branch'] = branch
    assert answered_questions['branch'] in QUESTION_FLAGS['branch']

    if 'run_mode' not in answered_questions and noninteractive:
        answered_questions['run_mode'] = 'b' 
    elif 'run_mode' not in answered_questions:
        answered_questions['run_mode'] = ask_question(
            "Run as (t)estnet node, (m)ainnet node, or (B)oth? (t/m/B)", ('t', 'm', 'b'), 'b')
        print("\tSetting up to run on %s" % ('testnet' if answered_questions['run_mode'].lower() == 't' 
            else ('mainnet' if answered_questions['run_mode'].lower() == 'm' else 'testnet and mainnet')))
    assert answered_questions['run_mode'] in QUESTION_FLAGS['run_mode']

    if answered_questions['role'] == 'counterparty-server_only':
        if 'counterparty-server_public' not in answered_questions and noninteractive:
            answered_questions['counterparty-server_public'] = 'y' 
        elif 'counterparty-server_public' not in answered_questions:
            answered_questions['counterparty-server_public'] = ask_question(
                "Enable public Counterpartyd setup (listen on all network interfaces w/ rpc/1234 user) (Y/n)", ('y', 'n'), 'y')
        else:
            answered_questions['counterparty-server_public'] = answered_questions.get('counterparty-server_public', 'n') #does not apply
        assert answered_questions['counterparty-server_public'] in QUESTION_FLAGS['counterparty-server_public']
    else: answered_questions['counterparty-server_public'] = None

    if answered_questions['role'] == 'counterwallet':
        counterwallet_support_email = None
        if 'counterwallet_support_email' not in answered_questions and noninteractive:
            answered_questions['counterwallet_support_email'] = '' 
        elif 'counterwallet_support_email' not in answered_questions:
            while True:
                counterwallet_support_email = input("Email address where support cases should go (blank to disable): ")
                counterwallet_support_email = counterwallet_support_email.strip()
                if counterwallet_support_email:
                    counterwallet_support_email_confirm = ask_question(
                        "You entered '%s', is that right? (Y/n): " % counterwallet_support_email, ('y', 'n'), 'y') 
                    if counterwallet_support_email_confirm == 'y': break
                else: break
            answered_questions['counterwallet_support_email'] = counterwallet_support_email
        else:
            answered_questions['counterwallet_support_email'] = answered_questions.get('counterwallet_support_email', '').strip()
    else: answered_questions['counterwallet_support_email'] = None 

    if 'security_hardening' not in answered_questions and noninteractive:
        answered_questions['security_hardening'] = 'y' 
    elif 'security_hardening' not in answered_questions:
        answered_questions['security_hardening'] = ask_question("Set up security hardening? (Y/n)", ('y', 'n'), 'y')
    assert answered_questions['security_hardening'] in QUESTION_FLAGS['security_hardening']
    
    if 'autostart_services' not in answered_questions and noninteractive:
        answered_questions['autostart_services'] = 'n' 
    elif 'autostart_services' not in answered_questions:
        answered_questions['autostart_services'] = ask_question("Autostart services (including on boot)? (y/N)", ('y', 'n'), 'n')
    assert answered_questions['autostart_services'] in QUESTION_FLAGS['autostart_services']

    logging.debug("answered_questions: %s" % answered_questions)
    return answered_questions

def usage():
    print("SYNTAX: %s [-h] [--noninteractive] %s" % (
        sys.argv[0], ' '.join([('[--%s=%s]' % (q, '|'.join(v) if v else '')) for q, v in QUESTION_FLAGS.items()])))

def main():
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s|%(levelname)s: %(message)s')
    do_federated_node_prerun_checks()
    run_as_user = os.environ["SUDO_USER"]
    assert run_as_user
    answered_questions = {}

    #parse any command line objects
    noninteractive = False
    try:
        opts, args = getopt.getopt(sys.argv[1:], "h", ["help", "noninteractive"] + ['%s=' % q for q in QUESTION_FLAGS.keys()])
    except getopt.GetoptError as err:
        usage()
        sys.exit(2)
    for o, a in opts:
        if o in ("-h", "--help"):
            usage()
            sys.exit()
        elif o == "--noninteractive":
            noninteractive = True
        elif o in ['--%s' % q for q in QUESTION_FLAGS.keys()]: #process flags for non-interactivity
            answered_questions[o.lstrip('-')] = a
        else:
            assert False, "Unhandled or unimplemented switch or option"

    base_path = os.path.join(USER_HOMEDIR, "counterpartyd_build")
    dist_path = os.path.join(base_path, "dist")

    #Detect if we should ask the user if they just want to update the source and not do a rebuild
    do_rebuild = 'r'
    try:
        pwd.getpwnam(USERNAME) #hacky check ...as this user is created by the script
    except:
        answered_questions['op'] = 'r' #do a build
    else: #setup has already been run at least once
        if not (answered_questions.get('op', None) in QUESTION_FLAGS['op']):
            answered_questions['op'] = ask_question(
                "It appears this setup has been run already or has another instance of counterpartyd or Federated Node. (r)ebuild node, or just (U)pdate from git? (r/U)",
                ('r', 'u'), 'u')
            assert answered_questions['op'] in QUESTION_FLAGS['op']

    if os.path.exists("/etc/init.d/iwatch"):
        runcmd("service iwatch stop", abort_on_failure=False)

    if answered_questions['op'] == 'u': #just refresh counterpartyd, counterblockd, and counterwallet, etc. from github
        #refresh counterpartyd_build, counterpartyd and counterblockd (if available)
        runcmd("%s/setup.py --noninteractive --branch=AUTO --for-user=xcp %s update" % (base_path,
            '--with-counterblockd' if os.path.exists(os.path.join(dist_path, "counterblockd")) else ''))
        
        #refresh counterwallet (if available)
        if os.path.exists(os.path.expanduser("~%s/counterwallet" % USERNAME)):
            do_counterwallet_setup(run_as_user, "AUTO", updateOnly=True)

        #offer to restart services
        restarted = command_services("restart", prompt=not noninteractive)
        if not restarted and os.path.exists("/etc/init.d/iwatch"):
            runcmd("service iwatch start", abort_on_failure=False)
    else:
        assert answered_questions['op'] == 'r'
        #If here, a) federated node has not been set up yet or b) the user wants a rebuild
        answered_questions = gather_build_questions(answered_questions, noninteractive)
        command_services("stop")
    
        do_base_setup(run_as_user, answered_questions['branch'], base_path, dist_path)
        
        backend_rpc_password, backend_rpc_password_testnet \
            = do_backend_rpc_setup(run_as_user, answered_questions['branch'], base_path, dist_path,
                answered_questions['run_mode'])
        
        do_counterparty_setup(answered_questions['role'], run_as_user, answered_questions['branch'],
            base_path, dist_path, answered_questions['run_mode'],
            backend_rpc_password, backend_rpc_password_testnet,
            answered_questions['counterparty-server_public'], answered_questions['counterwallet_support_email'])
        
        runcmd("rm -rf /etc/sv/insight /etc/sv/insight-testnet /etc/service/insight /etc/service/insight-testnet") # so insight doesn't start if it was in use before
        
        do_nginx_setup(run_as_user, base_path, dist_path, enable=answered_questions['role'] not in ["counterparty-server_only", "counterblock_basic"])
        
        do_armory_utxsvr_setup(run_as_user, base_path, dist_path,
            answered_questions['run_mode'], enable=answered_questions['role'] == 'counterwallet')
        if answered_questions['role'] == 'counterwallet':
            do_counterwallet_setup(run_as_user, answered_questions['branch'])
        
        do_security_setup(run_as_user, answered_questions['branch'], base_path, dist_path,
            enable=answered_questions['security_hardening'] == 'y')
        
        logging.info("Counterblock Federated Node Build Complete (whew).")
        
        if answered_questions['autostart_services'] == 'y':
            configured_services = find_configured_services()
            for s in configured_services:
                config_runit_disable_manual_control(s)
    
        if os.path.exists("/etc/init.d/iwatch"):
            runcmd("service iwatch start", abort_on_failure=False)

if __name__ == "__main__":
    main()
