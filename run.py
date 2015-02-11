#! /usr/bin/env python3
"""
Sets up an Ubuntu 14.04 x64 server to be a Counterblock Federated Node.

NOTE: The system should be properly secured before running this script.

This is admittedly a (bit of a) hack. In the future, most likely
utilize a cleaner, docker-based approach.
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
import tarfile
import random
import string
import subprocess

try: #ignore import errors on windows
    import pwd
    import grp
except ImportError:
    pass

REPO_NAME = "federatednode_build"
REPO_URL = "https://github.com/CounterpartyXCP/federatednode_build.git"
USERNAME = "xcp"
DAEMON_USERNAME = "xcpd"
USER_HOMEDIR = "/home/xcp"
PYTHON2_VER = "2.7" #Ubuntu 14.04 uses python2.7
PYTHON3_VER = "3.4" #Ubuntu 14.04 uses python3.4
paths = None
questions = None

###
### UTILITY METHODS
###
def pass_generator(size=14, chars=string.ascii_uppercase + string.ascii_lowercase + string.digits):
    return ''.join(random.choice(chars) for x in range(size))

def runcmd(command, abort_on_failure=True):
    logging.debug("RUNNING COMMAND: %s" % command)
    ret = os.system(command)
    if abort_on_failure and ret != 0:
        logging.error("Command failed: '%s'" % command)
        sys.exit(1) 
                
def modify_config(param_re, content_to_add, filenames, replace_if_exists=True, dotall=False):
    if not isinstance(filenames, (list, tuple)):
        filenames = [filenames,]
        
    re_flags = re.MULTILINE | re.DOTALL if dotall else re.MULTILINE
        
    for filename in filenames:
        f = open(filename, 'r')
        content = f.read()
        f.close()
        if not re.search(param_re, content, re_flags): #missing; add to config 
            if content[-1] != '\n': content += '\n'
            content += content_to_add 
        elif replace_if_exists: #replace in config
            content = re.sub(param_re, content_to_add, content, flags=re_flags)
        f = open(filename, 'w')
        f.write(content)
        f.close()

def modify_cp_config(param_re, content_to_add, replace_if_exists=True, config='counterpartyd', net='both'):
    assert config in ('counterparty', 'counterblock', 'both')
    assert net in ('mainnet', 'testnet', 'both')
    cfg_filenames = []
    if config in ('counterparty', 'both'):
        if net in ('mainnet', 'both'):
            cfg_filenames.append(os.path.join(paths['config_path.template'] % "counterparty", "server.conf"))
        if net in ('testnet', 'both'):
            cfg_filenames.append(os.path.join(paths['config_path.template'] % "counterparty", "server.testnet.conf"))
    if config in ('counterblock', 'both'):
        if net in ('mainnet', 'both'):
            cfg_filenames.append(os.path.join(paths['config_path.template'] % "counterblock", "server.conf"))
        if net in ('testnet', 'both'):
            cfg_filenames.append(os.path.join(paths['config_path.template'] % "counterblock", "server.testnet.conf"))
    modify_config(param_re, content_to_add, cfg_filenames, replace_if_exists=replace_if_exists)

def ask_question(question, options, default_option):
    assert isinstance(options, (list, tuple))
    assert default_option in options
    answer = None
    while True:
        answer = input(question + ": ")
        answer = answer.lower()
        if answer and answer not in options:
            logging.error("Please enter one of: " + ', '.join(options))
        else:
            if answer == '': answer = default_option
            break
    return answer
        
def git_repo_clone(repo_name, repo_url, repo_dest_dir, branch="AUTO", for_user="xcp", for_group="xcp", hash=None):
    if branch == 'AUTO':
        try:
            branch = subprocess.check_output("cd %s && git rev-parse --abbrev-ref HEAD"
                % repo_dest_dir, shell=True).strip().decode('utf-8')
        except:
            branch = "master" #branch doesn't exist, default to master
    logging.info("Checking out/updating %s:%s from git..." % (repo_name, branch))
    
    if os.path.exists(repo_dest_dir):
        runcmd("cd %s && git pull origin %s" % (repo_dest_dir, branch))
    else:
        runcmd("git clone -b %s %s %s" % (branch, repo_url, repo_dest_dir))

    if hash:
        runcmd("cd %s && git reset --hard %s" % (repo_dest_dir, hash))
            
    runcmd("cd %s && git config core.sharedRepository group && find %s -type d -print0 | xargs -0 chmod g+s" % (
        repo_dest_dir, repo_dest_dir)) #to allow for group git actions 
    runcmd("chown -R %s:%s %s" % (for_user, for_group, repo_dest_dir))
    runcmd("chmod -R u+rw,g+rw,o+r,o-w %s" % (repo_dest_dir,)) #just in case

def config_runit_for_service(dist_path, service_name, enabled=True, manual_control=True):
    assert os.path.exists("%s/linux/runit/%s" % (dist_path, service_name))
    
    #stop old upstart service and remove old upstart init scripts (if present)
    if os.path.exists("/etc/init/%s.conf" % service_name):
        runcmd("service %s stop" % service_name, abort_on_failure=False)
    runcmd("rm -f /etc/init/%s.conf /etc/init/%s.conf.override" % (service_name, service_name))
    
    runcmd("cp -dRf --preserve=mode %s/linux/runit/%s /etc/sv/" % (dist_path, service_name))

    if manual_control:
        runcmd("touch /etc/sv/%s/down" % service_name)
    else:
        runcmd("rm -f /etc/sv/%s/down" % service_name)
    
    if enabled:
        runcmd("ln -sf /etc/sv/%s /etc/service/" % service_name)
        #runcmd("sv stop %s" % service_name) #prevent service from starting automatically
    else:
        runcmd("rm -f /etc/service/%s" % service_name) #service will automatically be stopped within 5 seconds

def config_runit_disable_manual_control(service_name):
    runcmd("rm -f /etc/service/%s/down" % service_name)


###
### PRIMARY FUNCTIONS
###
def do_federated_node_prerun_checks(require_sudo=True):
    #make sure this is running on a supported OS
    if os.name != "posix" or platform.dist()[0] != "Ubuntu" or platform.architecture()[0] != '64bit':
        logging.error("Only 64bit Ubuntu Linux is supported at this time")
        sys.exit(1)
    ubuntu_release = platform.linux_distribution()[1]
    if ubuntu_release != "14.04":
        logging.error("Only Ubuntu 14.04 supported for Counterblock Federated Node install.")
        sys.exit(1)
    #script must be run as root
    if os.geteuid() != 0:
        logging.error("This script must be run as root (use 'sudo' to run)")
        sys.exit(1)
    assert os.name == "posix"
    if require_sudo and "SUDO_USER" not in os.environ:
        logging.error("Please use `sudo` to run this script.")
        sys.exit(1)
      
def get_base_paths():
    paths = {}
    paths['sys_python_path'] = os.path.dirname(sys.executable)
    paths['base_path'] = os.path.join(USER_HOMEDIR, REPO_NAME)
    #^ the dir of where counterparty source was downloaded to
    #find the location of the virtualenv command and make sure it exists
    paths['virtualenv_path'] = "/usr/bin/virtualenv"
    paths['virtualenv_args'] = "--python=python%s" % PYTHON3_VER
    #compose the rest of the paths...
    paths['dist_path'] = os.path.join(paths['base_path'], "dist")
    paths['env_path'] = os.path.join(paths['base_path'], "env") # home for the virtual environment
    #the pip executable that we'll be using does not exist yet, but it will, once we've created the virtualenv
    paths['pip_path'] = os.path.join(paths['env_path'], "bin", "pip")
    paths['python_path'] = os.path.join(paths['env_path'], "bin", "python3")

    #for now, counterblockd currently uses Python 2.7 due to gevent-socketio's lack of support for Python 3
    #because of this, it needs its own virtual environment
    paths['virtualenv_args.counterblock'] = "--system-site-packages --python=python2.7"
    paths['env_path.counterblock'] = os.path.join(paths['base_path'], "env.counterblock") # home for the virtual environment
    paths['pip_path.counterblock'] = os.path.join(paths['env_path.counterblock'], "bin", "pip")
    paths['python_path.counterblock'] = os.path.join(paths['env_path.counterblock'], "bin", "python")
    
    #user paths
    paths['log_path.template'] = os.path.join(USER_HOMEDIR, ".cache", "%s", "log")
    paths['config_path.template'] = os.path.join(USER_HOMEDIR, ".config", "%s")
    paths['data_path.template'] = os.path.join(USER_HOMEDIR, ".local", "share", "%s")
    
    return paths

def remove_old():
    "remove old things from the previous counterpartyd_build system"
    #program links/executiables
    runcmd("rm -f /usr/local/bin/counterpartyd /usr/local/bin/counterblockd /usr/local/bin/armory_utxsvr")
    #remove any insight stuff...
    runcmd("rm -rf /etc/sv/insight /etc/sv/insight-testnet /etc/service/insight /etc/service/insight-testnet")
    #runit entries
    def remove_runit(service_name):
        runcmd("rm -f /etc/service/%s" % service_name)
        runcmd("rm -rf /etc/sv/%s" % service_name)
    for service_name in ("bitcoind", "bitcoind-testnet",
    "counterpartyd", "counterpartyd-testnet", "counterblockd", "counterblockd-testnet"):
        remove_runit(service_name)
        
def do_base_setup(run_as_user):
    """This creates the xcp and xcpd users and checks out the federatednode_build system from git"""
    #change time to UTC
    runcmd("ln -sf /usr/share/zoneinfo/UTC /etc/localtime")

    #install some necessary base deps
    runcmd("apt-key update && apt-get update")
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
    #Create xcpd user (to run counterparty, counterblock, bitcoind, nginx) if not already made
    try:
        pwd.getpwnam(DAEMON_USERNAME)
    except:
        logging.info("Creating user '%s' ..." % DAEMON_USERNAME)
        runcmd("adduser --system --disabled-password --shell /bin/false --ingroup nogroup --home %s %s"
            % (USER_HOMEDIR, DAEMON_USERNAME))

    #add the run_as_user to the xcp group
    runcmd("adduser %s %s" % (run_as_user, USERNAME))
    
    #Check out federatednode_build repo under this user's home dir and use that for the build
    git_repo_clone(REPO_NAME, REPO_URL, paths['base_path'], questions.branch, for_user=run_as_user)

    #enhance fd limits for the xcpd user
    runcmd("cp -af %s/linux/other/xcpd_security_limits.conf /etc/security/limits.d/" % paths['dist_path'])

def do_backend_rpc_setup():
    """Installs and configures bitcoind"""
    
    def install_from_source():
        #Install bitcoind (btcbrak's 0.10.0 addrindex branch)
        BITCOIND_VERSION="0.10-rc2"
        BITCOIND_DEB_VERSION="0.10.0-2"

        #Install deps (see https://help.ubuntu.com/community/bitcoin)
        runcmd("apt-get -y install build-essential libtool autotools-dev autoconf pkg-config libssl-dev libboost-dev libboost-all-dev software-properties-common checkinstall")
        runcmd("add-apt-repository -y ppa:bitcoin/bitcoin")
        runcmd("apt-get update")
        runcmd("apt-get -y install libdb4.8-dev libdb4.8++-dev")
        
        runcmd("apt-get -y remove bitcoin.addrindex", abort_on_failure=False) #remove old version if it exists
        
        runcmd("rm -rf /tmp/bitcoin-addrindex-%s" % BITCOIND_VERSION)
        runcmd("wget -O /tmp/bitcoin-addrindex-%s.tar.gz https://github.com/btcdrak/bitcoin/archive/addrindex-%s.tar.gz"
            % (BITCOIND_VERSION, BITCOIND_VERSION))
        runcmd("cd /tmp && tar -zxvf /tmp/bitcoin-addrindex-%s.tar.gz" % BITCOIND_VERSION)
        runcmd("cd /tmp/bitcoin-addrindex-%s && ./autogen.sh && ./configure --without-gui && make && checkinstall -y -D --install --pkgversion=%s"
            % (BITCOIND_VERSION, BITCOIND_DEB_VERSION))
        runcmd("rm -rf /tmp/bitcoin-addrindex-%s" % BITCOIND_VERSION)
        runcmd("ln -sf /usr/local/bin/bitcoind /usr/bin/bitcoind && ln -sf /usr/local/bin/bitcoin-cli /usr/bin/bitcoin-cli")
    
    def install_binaries():
        BITCOIND_URL="https://github.com/btcdrak/bitcoin/releases/download/addrindex-0.10-rc2/bitcoin-addrindex-0.10.0-rc2-linux64.tar.gz"
        BITCOIND_FILENAME="bitcoin-addrindex-0.10.0-rc2-linux64.tar.gz"
        BITCOIND_DIRNAME="bitcoin-0.10.0"
        BITCOIND_SHA256_HASH="6ec320e8c8514bc76a538afd299f2f0a3b8dd13075a73220e8f4dfb04eeaadbf"

        runcmd("apt-get -y remove bitcoin.addrindex bitcoin-addrindex-0.10", abort_on_failure=False) #remove old versions
        
        if not os.path.exists("/tmp/%s" % BITCOIND_DIRNAME):
            runcmd("wget -O /tmp/%s %s" % (BITCOIND_FILENAME, BITCOIND_URL))
            runcmd('bash -c "echo \"%s /tmp/%s\" | sha256sum -c"' % (BITCOIND_SHA256_HASH, BITCOIND_FILENAME))
            runcmd("tar -C /tmp -zxvf /tmp/%s" % BITCOIND_FILENAME)
        #dont install libbitcoinconsensus.so for now on the system...not needed
        runcmd("install -C --backup=off -m 755 -o root -g root /tmp/%s/bin/* /usr/local/bin/" % BITCOIND_DIRNAME)
        runcmd("ln -sf /usr/local/bin/bitcoind /usr/bin/bitcoind && ln -sf /usr/local/bin/bitcoin-cli /usr/bin/bitcoin-cli")
    
    DEFAULT_CONFIG = "rpcuser=rpc\nrpcpassword=%s\nserver=1\ndaemon=1\nrpcthreads=1000\nrpctimeout=300\ntxindex=1\naddrindex=1"
    DEFAULT_CONFIG_TESTNET = DEFAULT_CONFIG + "\ntestnet=1"
    backend_rpc_password = pass_generator()
    backend_rpc_password_testnet = pass_generator()

    #would prefer to compile from source, but there are issues with openssl version in use
    # on ubuntu 14.04 that cause issues with bitcoind. using binaries is more deterministic
    # for now...
    install_binaries()

    #Do basic inital bitcoin config (for both testnet and mainnet)
    runcmd("mkdir -p ~%s/.bitcoin" % (USERNAME,))
    if not os.path.exists(os.path.join(USER_HOMEDIR, '.bitcoin', 'bitcoin.conf')):
        runcmd(r"""bash -c 'echo -e "%s" > ~%s/.bitcoin/bitcoin.conf'""" % (
            DEFAULT_CONFIG % backend_rpc_password, USERNAME))
    else: #grab the existing RPC password
        backend_rpc_password = subprocess.check_output(
            r"""bash -c "cat ~%s/.bitcoin/bitcoin.conf | sed -n 's/.*rpcpassword=\([^ \n]*\).*/\1/p'" """ % USERNAME, shell=True).strip().decode('utf-8')
    
    if not os.path.exists(os.path.join(USER_HOMEDIR, '.bitcoin', 'bitcoin.testnet.conf')):
        runcmd(r"""bash -c 'echo -e "%s" > ~%s/.bitcoin/bitcoin.testnet.conf'""" % (
            DEFAULT_CONFIG_TESTNET % backend_rpc_password_testnet, USERNAME))
    else:
        backend_rpc_password_testnet = subprocess.check_output(
            r"""bash -c "cat ~%s/.bitcoin/bitcoin.testnet.conf | sed -n 's/.*rpcpassword=\([^ \n]*\).*/\1/p'" """
            % USERNAME, shell=True).strip().decode('utf-8')
    #set permissions
    runcmd("chown -R %s:%s ~%s/.bitcoin" % (DAEMON_USERNAME, USERNAME, USERNAME,))
    
    #install logrotate file
    runcmd("cp -dRf --preserve=mode %s/linux/logrotate/bitcoind /etc/logrotate.d/bitcoind" % paths['dist_path'])

    #set up runit startup scripts
    config_runit_for_service(paths['dist_path'], "bitcoin", enabled=questions.with_mainnet)
    config_runit_for_service(paths['dist_path'], "bitcoin-testnet", enabled=questions.with_testnet)
    
    return backend_rpc_password, backend_rpc_password_testnet

def do_counterparty_setup(run_as_user, backend_rpc_password, backend_rpc_password_testnet):
    """Installs and configures counterparty-server and counterblock"""
    
    username_uid = pwd.getpwnam(USERNAME).pw_uid
    username_gid = grp.getgrnam(USERNAME).gr_gid
    daemon_username_uid = pwd.getpwnam(DAEMON_USERNAME).pw_uid
    
    def install_dependencies():
        runcmd("apt-get -y update")
        runcmd("apt-get -y install runit software-properties-common python-software-properties git-core wget \
        python3 python3-setuptools python3-dev python3-pip build-essential python3-sphinx python-virtualenv libsqlite3-dev python3-apsw python3-zmq")
        
        if questions.with_counterblock:
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
            if os.path.exists("/etc/init.d/mongod"):
                runcmd("""bash -c "echo 'manual' > /etc/init/mongod.override" """)
                runcmd("service mongod stop", abort_on_failure=False)
            config_runit_for_service(paths['dist_path'], "mongod", manual_control=False)
    
            #also install redis
            runcmd("apt-get -y install redis-server")
        #install sqlite utilities (not technically required, but nice to have)
        runcmd("apt-get -y install sqlite sqlite3 libleveldb-dev")
    
    def create_virtualenv():
        def create_venv(env_path, pip_path, python_path, virtualenv_args, delete_if_exists=True):
            if paths['virtualenv_path'] is None or not os.path.exists(paths['virtualenv_path']):
                logging.debug("ERROR: virtualenv missing (%s)" % (paths['virtualenv_path'],))
                sys.exit(1)
            
            if delete_if_exists and os.path.exists(env_path):
                logging.warning("Deleting existing virtualenv...")
                shutil.rmtree(env_path)
            assert not os.path.exists(os.path.join(env_path, 'bin'))
            logging.info("Creating virtualenv at '%s' ..." % env_path)
            runcmd("%s %s %s" % (paths['virtualenv_path'], virtualenv_args, env_path))
            #group should be xcp and have write permissions
            runcmd("chown -R %s:%s %s && chmod -R g+w %s" % (run_as_user, USERNAME, env_path, env_path))
            
            #pip should now exist
            if not os.path.exists(pip_path):
                logging.error("pip does not exist at path '%s'" % pip_path)
                sys.exit(1)
    
        create_venv(paths['env_path'], paths['pip_path'], paths['python_path'], paths['virtualenv_args']) 
        if questions.with_counterblock:
            #as counterblockd uses python 2.x, it needs its own virtualenv
            runcmd("rm -rf %s && mkdir -p %s" % (paths['env_path.counterblock'], paths['env_path.counterblock']))
            create_venv(paths['env_path.counterblock'], paths['pip_path.counterblock'], paths['python_path.counterblock'],
                paths['virtualenv_args.counterblock'], delete_if_exists=False)   
    
    def create_default_dirs():
        for dir_base in ["counterparty", "counterblock"]:
            for dir in [paths['log_path.template'] % dir_base, paths['config_path.template'] % dir_base, paths['data_path.template'] % dir_base]:
                if not os.path.exists(dir):
                    os.makedirs(dir)
                os.chown(dir, daemon_username_uid, username_gid)
                os.chmod(dir, 0o775)   
        
    def create_default_config():
        DEFAULT_CONFIG = "[Default]\nbackend-user=rpc\nbackend-password=1234\nrpc-password=xcppw1234\n"
        DEFAULT_CONFIG_TESTNET = DEFAULT_CONFIG + "\ntestnet=1\n"
        DEFAULT_CONFIG_COUNTERBLOCK = "[Default]\nbackend-user=rpc\nbackend-password=1234\ncounterparty-password=xcppw1234\nrpc-host=0.0.0.0\nsocketio-host=0.0.0.0\nsocketio-chat-host=0.0.0.0\nredis-enable-apicache=0\n"
        DEFAULT_CONFIG_COUNTERBLOCK_TESTNET = DEFAULT_CONFIG_COUNTERBLOCK + "\ntestnet=1\n"

        def create_config(dir_base, cfg_name, default_config):
            cfg_path = os.path.join(paths['config_path.template'] % dir_base, cfg_name)
            cfg_missing = not os.path.exists(cfg_path)
            if not os.path.exists(cfg_path):
                logging.info("Creating new configuration file at: %s" % cfg_path)
                #create a default config file
                cfg = open(cfg_path, 'w')
                cfg.write(default_config)
                cfg.close()
                logging.info("%s config file has been created at '%s'" % (dir_base, cfg_path))
            else:
                logging.info("%s config file already exists at: '%s'" % (dir_base, cfg_path))
            #set/reset proper file ownership and mode
            os.chown(cfg_path, daemon_username_uid, username_gid)
            os.chmod(cfg_path, 0o660)
                
        create_config('counterparty', 'server.conf', DEFAULT_CONFIG)
        if questions.with_testnet:
            create_config('counterparty', 'server.testnet.conf', DEFAULT_CONFIG_TESTNET)
        if questions.with_counterblock:
            create_config('counterblock', 'server.conf', DEFAULT_CONFIG_COUNTERBLOCK)
            if questions.with_testnet:
                create_config('counterblock', 'server.testnet.conf', DEFAULT_CONFIG_COUNTERBLOCK_TESTNET)

    def alter_config():
        #modify out configuration values as necessary
        counterparty_rpc_password = '1234' if questions.role in ['counterparty-server_only', 'counterblock_basic'] \
            and questions.server_public == 'y' else pass_generator()
        counterparty_rpc_password_testnet = '1234' if questions.role in ['counterparty-server_only', 'counterblock_basic'] \
            and questions.server_public == 'y' else pass_generator()
        for net, backend_password, cp_password in (
            ('mainnet', backend_rpc_password, counterparty_rpc_password),
            ('testnet', backend_rpc_password_testnet, counterparty_rpc_password_testnet)):
            # Check if the config was chosen to be replaced. Prevents accessing non-existing files.
            if (net == 'testnet' and not questions.with_testnet) \
               or (net == 'mainnet' and not questions.with_mainnet):
                continue

            #modify the default stored bitcoind passwords in counterparty conf
            modify_cp_config(r'^backend-password=.*?$', 'backend-password=%s' % backend_password,
                config='counterparty', net=net)
            #modify the counterparty API rpc password in counterparty conf
            modify_cp_config(r'^rpc\-password=.*?$', 'rpc-password=%s' % cp_password,
                config='counterparty', net=net)
            #backend for counterpartyd should be addrindex
            modify_cp_config(r'^backend\-name=.*?$', 'backend-name=addrindex',
                config='counterparty', net=net)
    
            if questions.role in ['counterparty-server_only', 'counterblock_basic'] and questions.server_public == 'y':
                modify_cp_config(r'^rpc\-host=.*?$', 'rpc-host=0.0.0.0', config='counterparty', net=net)
                
            if questions.with_counterblock:
                modify_cp_config(r'^(backend\-rpc|backend)\-password=.*?$',
                    'backend-password=%s' % backend_password, config='counterblock', net=net)
                #modify the counterparty API rpc password in counterblockd.conf
                modify_cp_config(r'^counterparty\-password=.*?$',
                    'counterparty-password=%s' % cp_password, config='counterblock', net=net)
            
                #role-specific counterblockd.conf values
                modify_cp_config(r'^armory\-utxsvr\-enable=.*?$', 'armory-utxsvr-enable=%s' % 
                    ('1' if questions.role == 'counterwallet' else '0'), config='counterblock')
                if questions.role == 'counterwallet':
                    modify_cp_config(r'^support\-email=.*?$',
                        'support-email=%s' % questions.counterwallet_support_email, config='counterblock') #may be blank string

                if questions.role == 'counterblock_basic' and questions.server_public == 'y':
                    modify_cp_config(r'^rpc\-host=.*?$', 'rpc-host=0.0.0.0', config='counterblock', net=net)

    def configure_startup():
        #link over counterparty and counterblock script
        runcmd("ln -sf %s/bin/counterparty-server /usr/local/bin/counterparty-server" % paths['env_path'])
        runcmd("ln -sf %s/bin/counterparty-client /usr/local/bin/counterparty-client" % paths['env_path'])
        if questions.with_counterblock:
            runcmd("ln -sf %s/bin/counterblock /usr/local/bin/counterblock" % paths['env_path.counterblock'])
    
        if questions.with_mainnet:
            config_runit_for_service(paths['dist_path'], "counterparty", manual_control=not questions.start_on_boot)
        else:
            runcmd("rm -f /etc/service/counterparty")
        if questions.with_testnet:
            config_runit_for_service(paths['dist_path'], "counterparty-testnet",
                enabled=questions.with_testnet, manual_control=not questions.start_on_boot)
        else:
            runcmd("rm -f /etc/service/counterparty-testnet")
        if questions.with_counterblock and questions.with_mainnet:
            config_runit_for_service(paths['dist_path'], "counterblock", enabled=questions.with_counterblock,
                manual_control=not questions.start_on_boot)
        else:
            runcmd("rm -f /etc/service/counterblock")
        if questions.with_counterblock and questions.with_testnet:
            config_runit_for_service(paths['dist_path'], "counterblock-testnet",
                enabled=questions.with_counterblock and questions.with_testnet, manual_control=not questions.start_on_boot)
        else:
            runcmd("rm -f /etc/service/counterblock-testnet")
           
    install_dependencies()
    create_virtualenv()
    create_default_dirs()
    create_default_config()
    alter_config()
    install_base_via_pip(questions.branch)
    configure_startup()

def install_base_via_pip(branch="AUTO"):
    COUNTERPARTY_LIB_DIST_PATH = os.path.join(paths['dist_path'], "counterparty-lib")
    COUNTERPARTY_CLI_DIST_PATH = os.path.join(paths['dist_path'], "counterparty-cli")
    COUNTERBLOCK_DIST_PATH = os.path.join(paths['dist_path'], "counterblock")
    BRANCH_SETTINGS_PATH = os.path.join(paths['base_path'], ".base_branch")
    found_counterblock = os.path.exists(paths['env_path.counterblock'])
    
    if branch == "AUTO": #used with updates
        assert os.path.exists(BRANCH_SETTINGS_PATH)
        f = open(BRANCH_SETTINGS_PATH, 'r')
        branch = f.read()
        f.close()
        assert branch != "AUTO"

    PIP_COUNTERPARTY_LIB = "https://github.com/CounterpartyXCP/counterpartyd/archive/%s.zip#egg=counterpartylib" % branch
    PIP_COUNTERPARTY_CLI = "https://github.com/CounterpartyXCP/counterparty-cli/archive/%s.zip#egg=counterpartycli" % branch  
    PIP_COUNTERBLOCK = "https://github.com/CounterpartyXCP/counterblock/archive/%s.zip#egg=counterblock" % branch

    #pip install counterparty-cli, counterparty-lib and (optionally) counterblock for the chosen branch
    #only do this if there's not a directory there (this allows people to check out the repo and put it at that path)
    do_bootstrap = not os.path.exists(COUNTERPARTY_LIB_DIST_PATH)
    if not os.path.exists(COUNTERPARTY_LIB_DIST_PATH) or os.path.islink(COUNTERPARTY_LIB_DIST_PATH):
        runcmd("sudo su -s /bin/bash -c '%s install --upgrade %s' %s"
            % (paths['pip_path'], PIP_COUNTERPARTY_LIB, USERNAME))
        runcmd("ln -sf %s %s" % ( #create symlink
            os.path.join(paths['env_path'], "lib", "python" + PYTHON3_VER, "site-packages", "counterpartylib"),
            COUNTERPARTY_LIB_DIST_PATH))
    else:
        assert os.path.exists(os.path.join(COUNTERPARTY_LIB_DIST_PATH, "setup.py"))
        runcmd("%s %s install" % (paths['python_path'], os.path.join(COUNTERPARTY_LIB_DIST_PATH, "setup.py")))

    if not os.path.exists(COUNTERPARTY_CLI_DIST_PATH) or os.path.islink(COUNTERPARTY_CLI_DIST_PATH):
        runcmd("sudo su -s /bin/bash -c '%s install --upgrade %s' %s" % (paths['pip_path'], PIP_COUNTERPARTY_CLI, USERNAME))
        runcmd("ln -sf %s %s" % ( #create symlink
            os.path.join(paths['env_path'], "lib", "python" + PYTHON3_VER, "site-packages", "counterpartycli"),
            COUNTERPARTY_CLI_DIST_PATH))
    else:
        assert os.path.exists(os.path.join(COUNTERPARTY_CLI_DIST_PATH, "setup.py"))
        runcmd("%s %s install" % (paths['python_path'], os.path.join(COUNTERPARTY_CLI_DIST_PATH, "setup.py")))

    #install bootstrap
    if do_bootstrap:
        xcp_user_data_dir = os.path.join(USER_HOMEDIR, ".local/share")
        runcmd("bash -c 'XDG_DATA_HOME=%s %s bootstrap' %s"
            % (xcp_user_data_dir, os.path.join(paths['env_path'], "bin", "counterparty-server"), DAEMON_USERNAME))
    runcmd("chown -R %s:%s %s" % (DAEMON_USERNAME, USERNAME, os.path.join(xcp_user_data_dir, "counterparty")))
        
    if found_counterblock:
        if not os.path.exists(COUNTERBLOCK_DIST_PATH) or os.path.islink(COUNTERBLOCK_DIST_PATH):
            runcmd("sudo su -s /bin/bash -c '%s install --upgrade %s' %s"
                % (paths['pip_path.counterblock'], PIP_COUNTERBLOCK, USERNAME))
            runcmd("ln -sf %s %s" % (
                os.path.join(paths['env_path.counterblock'], "lib", "python" + PYTHON2_VER, "site-packages", "counterblock"),
                COUNTERBLOCK_DIST_PATH))
        else:
            assert os.path.exists(os.path.join(COUNTERBLOCK_DIST_PATH, "setup.py"))
            runcmd("%s %s install" % (paths['python_path.counterblock'], os.path.join(COUNTERBLOCK_DIST_PATH, "setup.py")))
            
    if branch != "AUTO":
        f = open(BRANCH_SETTINGS_PATH, 'w')
        f.write(branch)
        f.close()
        
def do_nginx_setup(run_as_user, enable=True):
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
    OPENRESTY_VER, paths['dist_path'], paths['dist_path'], paths['dist_path'], paths['dist_path'], paths['dist_path'], paths['dist_path'], paths['dist_path']))
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

def do_armory_utxsvr_setup(run_as_user, enable=True):
    runcmd("apt-get -y install xvfb python-qt4 python-twisted python-psutil xdg-utils hicolor-icon-theme")
    ARMORY_VERSION = "0.92.3_ubuntu-64bit"
    if not os.path.exists("/tmp/armory_%s.deb" % ARMORY_VERSION):
        runcmd("wget -O /tmp/armory_%s.deb https://s3.amazonaws.com/bitcoinarmory-releases/armory_%s.deb"
            % (ARMORY_VERSION, ARMORY_VERSION))
    runcmd("mkdir -p /usr/share/desktop-directories/") #bug fix (see http://askubuntu.com/a/406015)
    runcmd("dpkg -i /tmp/armory_%s.deb" % ARMORY_VERSION)

    runcmd("mkdir -p ~%s/.armory ~%s/.armory/log ~%s/.armory/log-testnet" % (USERNAME, USERNAME, USERNAME))
    runcmd("chown -R %s:%s ~%s/.armory" % (DAEMON_USERNAME, USERNAME, USERNAME))
    
    #create armory_utxsvr script
    f = open("/usr/local/bin/armory_utxsvr", 'w')
    f.write("#!/bin/sh\nDISPLAY=localhost:1.0 xvfb-run --auto-servernum %s/bin/armory_utxsvr \"$@\""
        % paths['env_path.counterblock'])
    f.close()
    runcmd("chmod +x /usr/local/bin/armory_utxsvr")
    
    #Set up upstart scripts (will be disabled later from autostarting on system startup if necessary)
    config_runit_for_service(paths['dist_path'], "armory_utxsvr", enabled=enable and questions.with_mainnet)
    config_runit_for_service(paths['dist_path'], "armory_utxsvr-testnet", enabled=enable and questions.with_testnet)

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
    
def do_security_setup(run_as_user, branch, enable=True):
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
    runcmd("install -m 0644 -o root -g root -D %s/linux/other/sysctl_rules.conf /etc/sysctl.d/60-tweaks.conf" % paths['dist_path'])

    #set up fail2ban
    runcmd("apt-get -y install fail2ban")
    runcmd("install -m 0644 -o root -g root -D %s/linux/other/fail2ban.jail.conf /etc/fail2ban/jail.d/counterblock.conf" % paths['dist_path'])
    runcmd("service fail2ban restart")
    
    #set up psad (this will install postfix, which will prompt the user)
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
    runcmd("install -m 0640 -o root -g root -D %s/linux/other/audit.rules /etc/audit/rules.d/counterblock.rules" % paths['dist_path'])
    modify_config(r'^USE_AUGENRULES=.*?$', 'USE_AUGENRULES="yes"', '/etc/default/auditd')
    runcmd("service auditd restart")

    #iwatch
    runcmd("apt-get -y install iwatch")
    modify_config(r'^START_DAEMON=.*?$', 'START_DAEMON=true', '/etc/default/iwatch')
    runcmd("install -m 0644 -o root -g root -D %s/linux/other/iwatch.xml /etc/iwatch/iwatch.xml" % paths['dist_path'])
    modify_config(r'guard email="root@localhost"', 'guard email="noreply@%s"' % socket.gethostname(), '/etc/iwatch/iwatch.xml')
    runcmd("service iwatch restart")

def find_configured_services():
    services = ["bitcoin", "bitcoin-testnet", "counterparty", "counterparty-testnet",
        "counterblock", "counterblock-testnet", "armory_utxsvr", "armory_utxsvr-testnet"]
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

class BuildQuestions:
    VALID = collections.OrderedDict({
        "op": ('u', 'r'),
        "role": ('counterwallet', 'counterparty-server_only', 'counterblock_basic'),
        "branch": ('master', 'develop'),
        "net": ('t', 'm', 'b'),
        "security_hardening": ('y', 'n'),
        "server_public": ('y', 'n'),
        "counterwallet_support_email": None,
        "autostart_services": ('y', 'n'),
    })
    
    def __init__(self):
        self.op = None
        self.role = None
        self.branch = None
        self.net = None
        self.security_hardening = None
        self.server_public = None
        self.counterwallet_support_email = None
        self.autostart_services = None
        
    def gather(self, noninteractive):
        if not questions.role and noninteractive:
            self.role = '1' 
        elif not self.role:
            role = ask_question("Enter the number for the role you want to build:\n"
                    + "\t1: Counterwallet server\n\t2: counterparty-server only\n\t3: counterblock basic (no Counterwallet)\n"
                    + "Your choice",
                ('1', '2', '3'), '1')
            if role == '1':
                role = 'counterwallet'
                role_desc = "Counterwallet server"
            elif role == '2':
                role = 'counterparty-server_only'
                role_desc = "counterparty-server only"
            elif role == '3':
                role = 'counterblock_basic'
                role_desc = "Basic counterblock server"
            print("\tBuilding a %s" % role_desc)
            self.role = role
        assert self.role in self.VALID['role']
    
        if not self.branch and noninteractive:
            self.branch = 'master' 
        elif not self.branch:
            branch = ask_question("Build from branch (M)aster or (d)evelop? (M/d)", ('m', 'd'), 'm')
            if branch == 'm': branch = 'master'
            elif branch == 'd': branch = 'develop'
            print("\tWorking with branch: %s" % branch)
            self.branch = branch
        assert self.branch in self.VALID['branch']
    
        if not self.net and noninteractive:
            self.net = 'b' 
        elif not self.net:
            self.net = ask_question(
                "Run as (t)estnet node, (m)ainnet node, or (B)oth? (t/m/B)", ('t', 'm', 'b'), 'b')
            print("\tSetting up to run on %s" % ('testnet' if self.net.lower() == 't' 
                else ('mainnet' if self.net.lower() == 'm' else 'testnet and mainnet')))
        assert self.net in self.VALID['net']
    
        if self.role in ['counterparty-server_only', 'counterblock_basic']:
            if not self.server_public and noninteractive:
                self.server_public = 'y' 
            elif not self.server_public:
                self.server_public = ask_question(
                    "Enable public setup (listen on all network interfaces) (Y/n)", ('y', 'n'), 'y')
            else:
                self.server_public = getattr(self, 'server_public', 'n') #does not apply
            assert self.server_public in self.VALID['server_public']
        else: self.server_public = None
    
        if self.role == 'counterwallet':
            counterwallet_support_email = None
            if not self.counterwallet_support_email and noninteractive:
                self.counterwallet_support_email = '' 
            elif not self.counterwallet_support_email:
                while True:
                    counterwallet_support_email = input("Email address where support cases should go (blank to disable): ")
                    counterwallet_support_email = getattr(self, counterwallet_support_email, '').strip()
                    if counterwallet_support_email:
                        counterwallet_support_email_confirm = ask_question(
                            "You entered '%s', is that right? (Y/n): " % counterwallet_support_email, ('y', 'n'), 'y') 
                        if counterwallet_support_email_confirm == 'y': break
                    else: break
                self.counterwallet_support_email = counterwallet_support_email
            else:
                self.counterwallet_support_email = self.counterwallet_support_email.strip()
        else: self.counterwallet_support_email = None 
    
        if not self.security_hardening and noninteractive:
            self.security_hardening = 'y' 
        elif not self.security_hardening:
            self.security_hardening = ask_question("Set up security hardening? (Y/n)", ('y', 'n'), 'y')
        assert self.security_hardening in self.VALID['security_hardening']
        
        if not self.autostart_services and noninteractive:
            self.autostart_services = 'n' 
        elif not self.autostart_services:
            self.autostart_services = ask_question("Autostart services (including on boot)? (y/N)", ('y', 'n'), 'n')
        assert self.autostart_services in self.VALID['autostart_services']
        
    def _with_mainnet(self):
        return self.net in ['m', 'b']
    with_mainnet = property(_with_mainnet)
        
    def _with_testnet(self):
        return self.net in ['t', 'b']
    with_testnet = property(_with_testnet)
        
    def _with_counterblock(self):
        return self.role != 'counterparty-server_only'
    with_counterblock = property(_with_counterblock)
    
    def _start_on_boot(self):
        return self.autostart_services == 'y'
    start_on_boot = property(_start_on_boot)
    
def usage():
    print("SYNTAX: %s [-h] [--noninteractive] %s" % (
        sys.argv[0], ' '.join([('[--%s=%s]' % (q, '|'.join(v) if v else '')) for q, v in BuildQuestions.VALID.items()])))

def main():
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s|%(levelname)s: %(message)s')
    
    do_federated_node_prerun_checks()
    run_as_user = os.environ["SUDO_USER"]
    assert run_as_user

    global paths
    paths = get_base_paths()

    global questions
    questions = BuildQuestions() #don't gather yet

    #parse any command line objects
    noninteractive = False
    try:
        opts, args = getopt.getopt(sys.argv[1:], "h", ["help", "noninteractive"] + ['%s=' % q for q in BuildQuestions.VALID.keys()])
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
            setattr(questions, o.lstrip('-'), a)
        else:
            assert False, "Unhandled or unimplemented switch or option"

    #Detect if we should ask the user if they just want to update the source and not do a rebuild
    do_rebuild = 'r'
    try:
        pwd.getpwnam(USERNAME) #hacky check ...as this user is created by the script
    except:
        questions.op = 'r' #do a build
    else: #setup has already been run at least once
        if questions.op not in BuildQuestions.VALID['op']:
            questions.op = ask_question(
                "It appears this setup has been run already or has another instance of counterpartyd or Federated Node. (r)ebuild node, or just (U)pdate from git? (r/U)",
                ('r', 'u'), 'u')
            assert questions.op in BuildQuestions.VALID['op']

    if os.path.exists("/etc/init.d/iwatch"):
        runcmd("service iwatch stop", abort_on_failure=False)

    if questions.op == 'u': #just refresh counterpartyd, counterblockd, and counterwallet, etc. from github
        #refresh this repo
        git_repo_clone(REPO_NAME, REPO_URL, paths['base_path'], for_user=USERNAME)        
        
        #refresh counterparty-server, counterparty-cli and counterblock (if available)
        install_base_via_pip()
        
        #refresh counterwallet (if available)
        if os.path.exists(os.path.expanduser("~%s/counterwallet" % USERNAME)):
            do_counterwallet_setup(run_as_user, "AUTO", updateOnly=True)
        
        #offer to restart services
        restarted = command_services("restart", prompt=not noninteractive)
        if not restarted and os.path.exists("/etc/init.d/iwatch"):
            runcmd("service iwatch start", abort_on_failure=False)
    else:
        assert questions.op == 'r'
        #If here, a) federated node has not been set up yet or b) the user wants a rebuild
        questions.gather(noninteractive)        
        command_services("stop")
    
        remove_old()
        do_base_setup(run_as_user)  
        
        backend_rpc_password, backend_rpc_password_testnet = do_backend_rpc_setup()
        
        do_counterparty_setup(run_as_user, backend_rpc_password, backend_rpc_password_testnet)
        
        do_nginx_setup(run_as_user,
            enable=questions.role not in ["counterparty-server_only", "counterblock_basic"])
        
        do_armory_utxsvr_setup(run_as_user, enable=questions.role == 'counterwallet')
        
        if questions.role == 'counterwallet':
            do_counterwallet_setup(run_as_user, questions.branch)
        
        do_security_setup(run_as_user, questions.branch, enable=questions.security_hardening == 'y')
        
        logging.info("Counterblock Federated Node Build Complete (whew).")
        
        if questions.start_on_boot:
            configured_services = find_configured_services()
            for s in configured_services:
                config_runit_disable_manual_control(s)
    
        if os.path.exists("/etc/init.d/iwatch"):
            runcmd("service iwatch start", abort_on_failure=False)

if __name__ == "__main__":
    main()
