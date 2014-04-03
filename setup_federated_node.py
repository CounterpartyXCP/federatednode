#! /usr/bin/env python3
"""
Sets up an Ubuntu 13.10 x64 server to be a counterwallet federated node.

NOTE: The system should be properly secured before running this script.

TODO: This is admittedly a (bit of a) hack. In the future, take this kind of functionality out to a .deb with
      a postinst script to do all of this, possibly.
"""
import os
import sys
import re
import getopt
import logging
import shutil
import urllib
import zipfile
import platform
import tempfile
import subprocess
import stat
import string
import random

try: #ignore import errors on windows
    import pwd
    import grp
except ImportError:
    pass

USERNAME = "xcp"

def pass_generator(size=14, chars=string.ascii_uppercase + string.ascii_lowercase + string.digits):
    return ''.join(random.choice(chars) for x in range(size))

def usage():
    print("SYNTAX: %s [-h]" % sys.argv[0])

def runcmd(command, abort_on_failure=True):
    logging.debug("RUNNING COMMAND: %s" % command)
    ret = os.system(command)
    if abort_on_failure and ret != 0:
        logging.error("Command failed: '%s'" % command)
        sys.exit(1) 
        
def git_repo_clone(branch, repo_dir, repo_url, run_as_user):
    if branch == 'AUTO':
        try:
            branch = subprocess.check_output("cd %s && git rev-parse --abbrev-ref HEAD" % (
                os.path.expanduser("~%s/%s" % (USERNAME, repo_dir))), shell=True).strip().decode('utf-8')
        except:
            raise Exception("Cannot get current get branch for %s." % repo_dir)
    logging.info("Checking out/updating %s:%s from git..." % (repo_dir, branch))
    
    if os.path.exists(os.path.expanduser("~%s/%s" % (USERNAME, repo_dir))):
        runcmd("cd ~%s/%s && git pull origin %s" % (USERNAME, repo_dir, branch))
    else:
        runcmd("git clone -b %s %s ~%s/%s" % (branch, repo_url, USERNAME, repo_dir))
    runcmd("chown -R %s:%s ~%s/%s" % (run_as_user, USERNAME, USERNAME, repo_dir))

def do_prerun_checks():
    #make sure this is running on a supported OS
    if os.name != "posix" or platform.dist()[0] != "Ubuntu" or platform.architecture()[0] != '64bit':
        logging.error("Only 64bit Ubuntu Linux is supported at this time")
        sys.exit(1)
    ubuntu_release = platform.linux_distribution()[1]
    if ubuntu_release != "13.10":
        logging.error("Only Ubuntu 13.10 supported for counterwalletd install.")
    #script must be run as root
    if os.geteuid() != 0:
        logging.error("This script must be run as root (use 'sudo' to run)")
        sys.exit(1)
    if os.name == "posix" and "SUDO_USER" not in os.environ:
        logging.error("Please use `sudo` to run this script.")

def do_base_setup(run_as_user, branch, base_path, dist_path):
    """This creates the xcp user and checks out the counterpartyd_build system from git"""
    #install some necessary base deps
    runcmd("apt-get update")
    runcmd("apt-get -y install git-core software-properties-common python-software-properties build-essential")
    runcmd("apt-get update")
    #node-gyp building for insight has ...issues out of the box on Ubuntu... use Chris Lea's nodejs build instead, which is newer
    runcmd("apt-get -y remove nodejs npm gyp")
    runcmd("add-apt-repository -y ppa:chris-lea/node.js")
    runcmd("apt-get update")
    runcmd("apt-get -y install nodejs") #includes npm

    #Create xcp user (to run bitcoind, counterpartyd, counterwalletd) if not already made
    try:
        pwd.getpwnam(USERNAME)
    except:
        logging.info("Creating user '%s' ..." % USERNAME)
        runcmd("adduser --system --disabled-password --shell /bin/bash --group %s" % USERNAME)
    #Check out counterpartyd-build repo under this user's home dir and use that for the build
    git_repo_clone(branch, "counterpartyd_build", "https://github.com/xnova/counterpartyd_build.git", run_as_user)

def do_bitcoind_setup(run_as_user, branch, base_path, dist_path, run_mode):
    """Installs and configures bitcoind"""
    user_homedir = os.path.expanduser("~" + USERNAME)
    bitcoind_rpc_password = pass_generator()
    bitcoind_rpc_password_testnet = pass_generator()
    
    #Install bitcoind
    runcmd("rm -rf /tmp/bitcoind.tar.gz /tmp/bitcoin-0.9.0-linux")
    runcmd("wget -O /tmp/bitcoind.tar.gz https://bitcoin.org/bin/0.9.0/bitcoin-0.9.0-linux.tar.gz")
    runcmd("tar -C /tmp -zxvf /tmp/bitcoind.tar.gz")
    runcmd("cp -af /tmp/bitcoin-0.9.0-linux/bin/64/bitcoind /usr/bin")
    runcmd("cp -af /tmp/bitcoin-0.9.0-linux/bin/64/bitcoin-cli /usr/bin")
    runcmd("rm -rf /tmp/bitcoind.tar.gz /tmp/bitcoin-0.9.0-linux")

    #Do basic inital bitcoin config (for both testnet and mainnet)
    runcmd("mkdir -p ~%s/.bitcoin ~%s/.bitcoin-testnet" % (USERNAME, USERNAME))
    if not os.path.exists(os.path.join(user_homedir, '.bitcoin', 'bitcoin.conf')):
        runcmd(r"""bash -c 'echo -e "rpcuser=rpc\nrpcpassword=%s\nserver=1\ndaemon=1\ntxindex=1" > ~%s/.bitcoin/bitcoin.conf'""" % (
            bitcoind_rpc_password, USERNAME))
    else: #grab the existing RPC password
        bitcoind_rpc_password = subprocess.check_output(
            r"""bash -c "cat ~%s/.bitcoin/bitcoin.conf | sed -n 's/.*rpcpassword=\([^ \n]*\).*/\1/p'" """ % USERNAME, shell=True).strip().decode('utf-8')
    if not os.path.exists(os.path.join(user_homedir, '.bitcoin-testnet', 'bitcoin.conf')):
        runcmd(r"""bash -c 'echo -e "rpcuser=rpc\nrpcpassword=%s\nserver=1\ndaemon=1\ntxindex=1\ntestnet=1" > ~%s/.bitcoin-testnet/bitcoin.conf'""" % (
            bitcoind_rpc_password_testnet, USERNAME))
    else:
        bitcoind_rpc_password_testnet = subprocess.check_output(
            r"""bash -c "cat ~%s/.bitcoin-testnet/bitcoin.conf | sed -n 's/.*rpcpassword=\([^ \n]*\).*/\1/p'" """
            % USERNAME, shell=True).strip().decode('utf-8')
    
    #Set up bitcoind startup scripts (will be disabled later from autostarting on system startup if necessary)
    runcmd("cp -af %s/linux/init/bitcoind.conf.template /etc/init/bitcoind.conf" % dist_path)
    runcmd("sed -ri \"s/\!RUN_AS_USER\!/%s/g\" /etc/init/bitcoind.conf" % USERNAME)
    runcmd("cp -af %s/linux/init/bitcoind-testnet.conf.template /etc/init/bitcoind-testnet.conf" % dist_path)
    runcmd("sed -ri \"s/\!RUN_AS_USER\!/%s/g\" /etc/init/bitcoind-testnet.conf" % USERNAME)
    
    #install logrotate file
    runcmd("cp -af %s/linux/logrotate/bitcoind /etc/logrotate.d/bitcoind" % dist_path)
    runcmd("sed -ri \"s/\!RUN_AS_USER_HOMEDIR\!/%s/g\" /etc/logrotate.d/bitcoind" % user_homedir.replace('/', '\/'))
    
    #disable upstart scripts from autostarting on system boot if necessary
    if run_mode == 't': #disable mainnet daemons from autostarting
        runcmd(r"""bash -c "echo 'manual' >> /etc/init/bitcoind.override" """)
    else:
        runcmd("rm -f /etc/init/bitcoind.override")
    if run_mode == 'm': #disable testnet daemons from autostarting
        runcmd(r"""bash -c "echo 'manual' >> /etc/init/bitcoind-testnet.override" """)
    else:
        runcmd("rm -f /etc/init/bitcoind-testnet.override")
    
    return bitcoind_rpc_password, bitcoind_rpc_password_testnet

def do_counterparty_setup(run_as_user, branch, base_path, dist_path, run_mode, bitcoind_rpc_password, bitcoind_rpc_password_testnet):
    """Installs and configures counterpartyd and counterwalletd"""
    counterpartyd_rpc_password = pass_generator()
    counterpartyd_rpc_password_testnet = pass_generator()
    
    #Run setup.py (as the XCP user, who runs it sudoed) to install and set up counterpartyd, counterwalletd
    # as -y is specified, this will auto install counterwalletd full node (mongo and redis) as well as setting
    # counterpartyd/counterwalletd to start up at startup for both mainnet and testnet (we will override this as necessary
    # based on run_mode later in this function)
    runcmd("~%s/counterpartyd_build/setup.py -y --with-counterwalletd --with-testnet --for-user=%s" % (USERNAME, USERNAME))
    runcmd("chown -R %s ~xcp/counterpartyd_build" % run_as_user) #hack

    #modify the default stored bitcoind passwords in counterpartyd.conf and counterwalletd.conf
    runcmd(r"""sed -ri "s/^bitcoind\-rpc\-password=.*?$/bitcoind-rpc-password=%s/g" ~%s/.config/counterpartyd/counterpartyd.conf""" % (
        bitcoind_rpc_password, USERNAME))
    runcmd(r"""sed -ri "s/^bitcoind\-rpc\-password=.*?$/bitcoind-rpc-password=%s/g" ~%s/.config/counterpartyd-testnet/counterpartyd.conf""" % (
        bitcoind_rpc_password_testnet, USERNAME))
    runcmd(r"""sed -ri "s/^bitcoind\-rpc\-password=.*?$/bitcoind-rpc-password=%s/g" ~%s/.config/counterwalletd/counterwalletd.conf""" % (
        bitcoind_rpc_password, USERNAME))
    runcmd(r"""sed -ri "s/^bitcoind\-rpc\-password=.*?$/bitcoind-rpc-password=%s/g" ~%s/.config/counterwalletd-testnet/counterwalletd.conf""" % (
        bitcoind_rpc_password_testnet, USERNAME))
    
    #modify the counterpartyd API rpc password in both counterpartyd and counterwalletd
    runcmd(r"""sed -ri "s/^rpc\-password=.*?$/rpc-password=%s/g" ~%s/.config/counterpartyd/counterpartyd.conf""" % (
        counterpartyd_rpc_password, USERNAME))
    runcmd(r"""sed -ri "s/^rpc\-password=.*?$/rpc-password=%s/g" ~%s/.config/counterpartyd-testnet/counterpartyd.conf""" % (
        counterpartyd_rpc_password_testnet, USERNAME))
    runcmd(r"""sed -ri "s/^counterpartyd\-rpc\-password=.*?$/counterpartyd-rpc-password=%s/g" ~%s/.config/counterwalletd/counterwalletd.conf""" % (
        counterpartyd_rpc_password, USERNAME))
    runcmd(r"""sed -ri "s/^counterpartyd\-rpc\-password=.*?$/counterpartyd-rpc-password=%s/g" ~%s/.config/counterwalletd-testnet/counterwalletd.conf""" % (
        counterpartyd_rpc_password_testnet, USERNAME))
    
    #disable upstart scripts from autostarting on system boot if necessary
    if run_mode == 't': #disable mainnet daemons from autostarting
        runcmd(r"""bash -c "echo 'manual' >> /etc/init/counterpartyd.override" """)
        runcmd(r"""bash -c "echo 'manual' >> /etc/init/counterwalletd.override" """)
    else:
        runcmd("rm -f /etc/init/counterpartyd.override /etc/init/counterwalletd.override")
    if run_mode == 'm': #disable testnet daemons from autostarting
        runcmd(r"""bash -c "echo 'manual' >> /etc/init/counterpartyd-testnet.override" """)
        runcmd(r"""bash -c "echo 'manual' >> /etc/init/counterwalletd-testnet.override" """)
    else:
        runcmd("rm -f /etc/init/counterpartyd-testnet.override /etc/init/counterwalletd-testnet.override")
    
    #append insight enablement params to counterpartyd's configs
    for cfgFilename in [
        os.path.join(os.path.expanduser('~'+USERNAME), ".config", "counterpartyd", "counterpartyd.conf"),
        os.path.join(os.path.expanduser('~'+USERNAME), ".config", "counterpartyd-testnet", "counterpartyd.conf") ]:
        f = open(cfgFilename, 'a+')
        content = f.read()
        if not re.search(r'^insight\-enable', content, re.MULTILINE):
            f.write('\ninsight-enable=1')
        if not re.search(r'^api\-num\-threads', content, re.MULTILINE):
            f.write('\napi-num-threads=100')
        if not re.search(r'^api\-request\-queue\-size', content, re.MULTILINE):
            f.write('\napi-request-queue-size=500')
        f.close()

    #change ownership
    runcmd("chown -R %s:%s ~%s/.bitcoin ~%s/.config/counterpartyd ~%s/.config/counterwalletd" % (
        USERNAME, USERNAME, USERNAME, USERNAME, USERNAME))
    runcmd("chown -R %s:%s ~%s/.bitcoin-testnet ~%s/.config/counterpartyd-testnet ~%s/.config/counterwalletd-testnet" % (
        USERNAME, USERNAME, USERNAME, USERNAME, USERNAME))

def do_insight_setup(run_as_user, base_path, dist_path, run_mode):
    """This installs and configures insight"""
    user_homedir = os.path.expanduser("~" + USERNAME)
    gypdir = None
    try:
        import gyp
        gypdir = os.path.dirname(gyp.__file__)
    except:
        pass
    else:
        runcmd("mv %s %s_bkup" % (gypdir, gypdir))
        #^ fix for https://github.com/TooTallNate/node-gyp/issues/363
    git_repo_clone("master", "insight-api", "https://github.com/bitpay/insight-api.git", run_as_user)
    runcmd("rm -rf ~%s/insight-api/node-modules && cd ~%s/insight-api && npm install" % (USERNAME, USERNAME))
    #Set up insight startup scripts (will be disabled later from autostarting on system startup if necessary)
    runcmd("cp -af %s/linux/init/insight.conf.template /etc/init/insight.conf" % dist_path)
    runcmd("sed -ri \"s/\!RUN_AS_USER\!/%s/g\" /etc/init/insight.conf" % USERNAME)
    runcmd("cp -af %s/linux/init/insight-testnet.conf.template /etc/init/insight-testnet.conf" % dist_path)
    runcmd("sed -ri \"s/\!RUN_AS_USER\!/%s/g\" /etc/init/insight-testnet.conf" % USERNAME)
    #install logrotate file
    runcmd("cp -af %s/linux/logrotate/insight /etc/logrotate.d/insight" % dist_path)
    runcmd("sed -ri \"s/\!RUN_AS_USER\!/%s/g\" /etc/logrotate.d/insight" % USERNAME)
    runcmd("sed -ri \"s/\!RUN_AS_USER_HOMEDIR\!/%s/g\" /etc/logrotate.d/insight" % user_homedir.replace('/', '\/'))

    runcmd("chown -R %s:%s ~%s/insight-api" % (USERNAME, USERNAME, USERNAME))
    
    #disable upstart scripts from autostarting on system boot if necessary
    if run_mode == 't': #disable mainnet daemons from autostarting
        runcmd(r"""bash -c "echo 'manual' >> /etc/init/insight.override" """)
    else:
        runcmd("rm -f /etc/init/insight.override")
    if run_mode == 'm': #disable testnet daemons from autostarting
        runcmd(r"""bash -c "echo 'manual' >> /etc/init/insight-testnet.override" """)
    else:
        runcmd("rm -f /etc/init/insight-testnet.override")

def do_nginx_setup(run_as_user, base_path, dist_path):
    #Build and install nginx (openresty) on Ubuntu
    #Most of these build commands from http://brian.akins.org/blog/2013/03/19/building-openresty-on-ubuntu/
    OPENRESTY_VER = "1.5.8.1"

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
&& install -m 0755 -D %s/linux/nginx/nginx.init /tmp/openresty/etc/init.d/nginx \
&& install -m 0755 -D %s/linux/nginx/nginx.conf /tmp/openresty/etc/nginx/nginx.conf \
&& install -m 0755 -D %s/linux/nginx/counterwallet.conf /tmp/openresty/etc/nginx/sites-enabled/counterwallet.conf \
&& install -m 0755 -D %s/linux/nginx/cw_api.inc /tmp/openresty/etc/nginx/sites-enabled/cw_api.inc \
&& install -m 0755 -D %s/linux/nginx/cw_api_cache.inc /tmp/openresty/etc/nginx/sites-enabled/cw_api_cache.inc \
&& install -m 0755 -D %s/linux/nginx/cw_socketio.inc /tmp/openresty/etc/nginx/sites-enabled/cw_socketio.inc \
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
--config-files /etc/nginx/sites-enabled/counterwallet.conf \
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
    runcmd("apt-get install libxslt1.1 libgeoip1 geoip-database libpcre3")
    runcmd("dpkg -i /tmp/nginx-openresty_%s-1_amd64.deb" % OPENRESTY_VER)
    #clean up after ourselves
    runcmd("rm -rf /tmp/openresty /tmp/ngx_openresty-* /tmp/nginx-openresty.tar.gz /tmp/nginx-openresty*.deb")
    runcmd("update-rc.d nginx defaults")
    
def do_counterwallet_setup(run_as_user, branch):
    #check out counterwallet from git
    git_repo_clone(branch, "counterwallet", "https://github.com/xnova/counterwallet.git", run_as_user)
    runcmd("npm install -g grunt-cli bower")
    runcmd("cd ~xcp/counterwallet/src && bower install")
    runcmd("cd ~xcp/counterwallet && npm install") #will generate the minified site
    runcmd("chown -R %s ~xcp/counterwallet" % run_as_user) #just in case

def do_newrelic_setup(run_as_user, base_path, dist_path, run_mode):
    NR_PREFS_LICENSE_KEY_PATH = "/etc/newrelic/LICENSE_KEY"
    NR_PREFS_HOSTNAME_PATH = "/etc/newrelic/HOSTNAME"
    
    runcmd("mkdir -p /etc/newrelic /var/log/newrelic /var/run/newrelic")
    runcmd("chown xcp /etc/newrelic /var/log/newrelic /var/run/newrelic")
    
    #try to find existing license key
    nr_license_key = None
    if os.path.exists(NR_PREFS_LICENSE_KEY_PATH):
        nr_license_key = open(NR_PREFS_LICENSE_KEY_PATH).read().strip()
    else:
        while True:
            nr_license_key = input("Enter New Relic license key (or blank to not setup New Relic): ") #gather license key
            nr_license_key = nr_license_key.strip()
            if not nr_license_key:
                return #skipping new relic
            nr_license_key_confirm = input("You entererd '%s', is that right? (Y/n): " % nr_license_key)
            nr_license_key_confirm = nr_license_key_confirm.lower()
            if nr_license_key_confirm not in ('y', 'n', ''):
                logging.error("Please enter 'y' or 'n'")
            else:
                if nr_license_key_confirm in ['', 'y']: break
        open(NR_PREFS_LICENSE_KEY_PATH, 'w').write(nr_license_key)
    assert nr_license_key
    logging.info("NewRelic license key: %s" % nr_license_key)

    #try to find existing app prefix
    nr_hostname = None
    if os.path.exists(NR_PREFS_HOSTNAME_PATH):
        nr_hostname = open(NR_PREFS_HOSTNAME_PATH).read().strip()
    else:
        while True:
            nr_hostname = input("Enter newrelic hostname/app prefix (e.g. 'cw01'): ") #gather app prefix
            nr_hostname = nr_hostname.strip()
            nr_hostname_confirm = input("You entererd '%s', is that right? (Y/n): " % nr_hostname)
            nr_hostname_confirm = nr_hostname_confirm.lower()
            if nr_hostname_confirm not in ('y', 'n', ''):
                logging.error("Please enter 'y' or 'n'")
            else:
                if nr_hostname_confirm in ['', 'y']: break
        open(NR_PREFS_HOSTNAME_PATH, 'w').write(nr_hostname)
    assert nr_hostname
    logging.info("NewRelic hostname/app prefix: %s" % nr_hostname)

    #install some deps...
    runcmd("sudo apt-get -y install libyaml-dev")
    
    #install/setup python agent for both counterpartyd and counterwalletd
    #counterpartyd
    runcmd("%s/env/bin/pip install newrelic" % base_path)
    runcmd("cp -af %s/linux/newrelic/nr_counterpartyd.ini.template /etc/newrelic/nr_counterpartyd.ini" % dist_path)
    runcmd("sed -ri \"s/\!LICENSE_KEY\!/%s/g\" /etc/newrelic/nr_counterpartyd.ini" % nr_license_key)
    runcmd("sed -ri \"s/\!HOSTNAME\!/%s/g\" /etc/newrelic/nr_counterpartyd.ini" % nr_hostname)
    #counterwalletd
    runcmd("%s/env.cwalletd/bin/pip install newrelic" % base_path)
    runcmd("cp -af %s/linux/newrelic/nr_counterwalletd.ini.template /etc/newrelic/nr_counterwalletd.ini" % dist_path)
    runcmd("sed -ri \"s/\!LICENSE_KEY\!/%s/g\" /etc/newrelic/nr_counterwalletd.ini" % nr_license_key)
    runcmd("sed -ri \"s/\!HOSTNAME\!/%s/g\" /etc/newrelic/nr_counterwalletd.ini" % nr_hostname)
    #install init scripts (overwrite the existing ones for now at least)
    runcmd("cp -af %s/linux/newrelic/init/nr-counterpartyd.conf /etc/init/counterpartyd.conf" % dist_path) #overwrite
    runcmd("cp -af %s/linux/newrelic/init/nr-counterwalletd.conf /etc/init/counterwalletd.conf" % dist_path) #overwrite
    runcmd("cp -af %s/linux/newrelic/init/nr-counterpartyd-testnet.conf /etc/init/counterpartyd-testnet.conf" % dist_path) #overwrite
    runcmd("cp -af %s/linux/newrelic/init/nr-counterwalletd-testnet.conf /etc/init/counterwalletd-testnet.conf" % dist_path) #overwrite
    #upstart enablement (overrides) should be fine as established in do_counterparty_setup...

    #install/setup server agent
    runcmd("add-apt-repository \"deb http://apt.newrelic.com/debian/ newrelic non-free\"")
    runcmd("wget -O- https://download.newrelic.com/548C16BF.gpg | apt-key add -")
    runcmd("apt-get update")
    runcmd("apt-get -y install newrelic-sysmond")
    runcmd("cp -af %s/linux/newrelic/nrsysmond.cfg.template /etc/newrelic/nrsysmond.cfg" % dist_path)
    runcmd("sed -ri \"s/\!LICENSE_KEY\!/%s/g\" /etc/newrelic/nrsysmond.cfg" % nr_license_key)
    runcmd("sed -ri \"s/\!HOSTNAME\!/%s/g\" /etc/newrelic/nrsysmond.cfg" % nr_hostname)
    runcmd("/etc/init.d/newrelic-sysmond restart")
    
    #install/setup meetme agent (mongo, redis)
    runcmd("pip install newrelic-plugin-agent pymongo")
    runcmd("cp -af %s/linux/newrelic/newrelic_plugin_agent.cfg.template /etc/newrelic/newrelic_plugin_agent.cfg" % dist_path)
    runcmd("sed -ri \"s/\!LICENSE_KEY\!/%s/g\" /etc/newrelic/newrelic_plugin_agent.cfg" % nr_license_key)
    runcmd("sed -ri \"s/\!HOSTNAME\!/%s/g\" /etc/newrelic/newrelic_plugin_agent.cfg" % nr_hostname)
    runcmd("ln -sf %s/linux/newrelic/init/newrelic_plugin_agent /etc/init.d/newrelic_plugin_agent" % dist_path)
    runcmd("update-rc.d newrelic_plugin_agent defaults")
    runcmd("/etc/init.d/newrelic_plugin_agent restart")
    
    #install/setup nginx agent
    runcmd("sudo apt-get -y install ruby ruby-bundler")
    runcmd("rm -rf /tmp/newrelic_nginx_agent.tar.gz /opt/newrelic_nginx_agent")
    #runcmd("wget -O /tmp/newrelic_nginx_agent.tar.gz http://nginx.com/download/newrelic/newrelic_nginx_agent.tar.gz")
    #runcmd("tar -C /opt -zxvf /tmp/newrelic_nginx_agent.tar.gz")
    runcmd("git clone https://github.com/crowdlab-uk/newrelic-nginx-agent.git /opt/newrelic_nginx_agent")
    runcmd("cd /opt/newrelic_nginx_agent && bundle install")
    runcmd("cp -af %s/linux/newrelic/newrelic_nginx_plugin.yml.template /opt/newrelic_nginx_agent/config/newrelic_plugin.yml" % dist_path)
    runcmd("sed -ri \"s/\!LICENSE_KEY\!/%s/g\" /opt/newrelic_nginx_agent/config/newrelic_plugin.yml" % nr_license_key)
    runcmd("sed -ri \"s/\!HOSTNAME\!/%s/g\" /opt/newrelic_nginx_agent/config/newrelic_plugin.yml" % nr_hostname)
    runcmd("ln -sf /opt/newrelic_nginx_agent/newrelic_nginx_agent.daemon /etc/init.d/newrelic_nginx_agent")
    runcmd("update-rc.d newrelic_nginx_agent defaults")
    runcmd("/etc/init.d/newrelic_nginx_agent restart")
    

def main():
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s|%(levelname)s: %(message)s')
    do_prerun_checks()
    run_as_user = os.environ["SUDO_USER"]
    assert run_as_user

    #parse any command line objects
    branch = "master"
    try:
        opts, args = getopt.getopt(sys.argv[1:], "h", ["help",])
    except getopt.GetoptError as err:
        usage()
        sys.exit(2)
    for o, a in opts:
        if o in ("-h", "--help"):
            usage()
            sys.exit()
        else:
            assert False, "Unhandled or unimplemented switch or option"

    base_path = os.path.expanduser("~%s/counterpartyd_build" % USERNAME)
    dist_path = os.path.join(base_path, "dist")

    #Detect if we should ask the user if they just want to update the source and not do a rebuild
    do_rebuild = None
    try:
        pwd.getpwnam(USERNAME) #hacky check ...as this user is created by the script
    except:
        pass
    else: #setup has already been run at least once
        while True:
            do_rebuild = input("It appears this setup has been run already. (r)ebuild node, or just refresh from (g)it? (r/G): ")
            do_rebuild = do_rebuild.lower()
            if do_rebuild not in ('r', 'g', ''):
                logging.error("Please enter 'r' or 'g'")
            else:
                if do_rebuild == '': do_rebuild = 'g'
                break
    if do_rebuild == 'g': #just refresh counterpartyd, counterwalletd, and counterwallet from github
        runcmd("%s/setup.py --with-counterwalletd --for-user=xcp update" % base_path)
        assert(os.path.exists(os.path.expanduser("~%s/counterwallet" % USERNAME)))
        git_repo_clone("AUTO", "counterwallet", "https://github.com/xnova/counterwallet.git", run_as_user)
        sys.exit(0) #all done

    #If here, a) federated node has not been set up yet or b) the user wants a rebuild
    branch = None
    while True:
        branch = input("Build from branch (m)aster or (d)evelop? (M/d): ")
        branch = branch.lower()
        if branch not in ('m', 'd', ''):
            logging.error("Please enter 'm' or 'd'")
        else:
            if branch == '': branch = 'm'
            break
    if branch == 'm': branch = 'master'
    elif branch == 'd': branch = 'develop'
    logging.info("Working with branch: %s" % branch)

    run_mode = None
    while True:
        run_mode = input("Run as (t)estnet node, (m)ainnet node, or (b)oth? (t/m/B): ")
        run_mode = run_mode.lower()
        if run_mode.lower() not in ('t', 'm', 'b', ''):
            logging.error("Please enter 't' or 'm' or 'b'")
        else:
            if run_mode == '': run_mode = 'b'
            break
    logging.info("Setting up to run on %s" % ('testnet' if run_mode.lower() == 't' else ('mainnet' if run_mode.lower() == 'm' else 'testnet and mainnet')))

    #shutdown services if they may be running on the box
    if os.path.exists("/etc/init/counterpartyd.conf"):
        runcmd("service bitcoind stop", abort_on_failure=False)
        runcmd("service bitcoind-testnet stop", abort_on_failure=False)
        runcmd("service insight stop", abort_on_failure=False)
        runcmd("service insight-testnet stop", abort_on_failure=False)
        runcmd("service counterpartyd stop", abort_on_failure=False)
        runcmd("service counterpartyd-testnet stop", abort_on_failure=False)
        runcmd("service counterwalletd stop", abort_on_failure=False)
        runcmd("service counterwalletd-testnet stop", abort_on_failure=False)
    
    do_base_setup(run_as_user, branch, base_path, dist_path)
    
    bitcoind_rpc_password, bitcoind_rpc_password_testnet \
        = do_bitcoind_setup(run_as_user, branch, base_path, dist_path, run_mode)
    
    do_counterparty_setup(run_as_user, branch, base_path, dist_path, run_mode, bitcoind_rpc_password, bitcoind_rpc_password_testnet)
    
    do_insight_setup(run_as_user, base_path, dist_path, run_mode)
    
    do_nginx_setup(run_as_user, base_path, dist_path)
    
    do_counterwallet_setup(run_as_user, branch)

    do_newrelic_setup(run_as_user, base_path, dist_path, run_mode) #optional
    
    logging.info("Counterwallet Federated Node Build Complete (whew).")


if __name__ == "__main__":
    main()
