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
import stat
import string
import random

try: #ignore import errors on windows
    import pwd
    import grp
except ImportError:
    pass

USERNAME = "xcp"
DAEMON_USERNAME = "xcpd"
REPO_COUNTERPARTYD_BUILD = "https://github.com/CounterpartyXCP/counterpartyd_build.git"
REPO_COUNTERWALLET = "https://github.com/CounterpartyXCP/counterwallet.git"

def pass_generator(size=14, chars=string.ascii_uppercase + string.ascii_lowercase + string.digits):
    return ''.join(random.choice(chars) for x in range(size))

def runcmd(command, abort_on_failure=True):
    logging.debug("RUNNING COMMAND: %s" % command)
    ret = os.system(command)
    if abort_on_failure and ret != 0:
        logging.error("Command failed: '%s'" % command)
        sys.exit(1) 

def modify_config(param_re, content_to_add, filenames, replace_if_exists=True, dotall=False, add_newline=True):
    if not isinstance(filenames, (list, tuple)):
        filenames = [filenames,]
        
    re_flags = re.MULTILINE | re.DOTALL if dotall else re.MULTILINE
        
    if add_newline and not content_to_add.endswith('\n'):
        content_to_add += '\n'

    for filename in filenames:
        f = open(filename, 'r')
        content = f.read()
        f.close()
        if content[-1] != '\n':
            content += '\n'
        if not re.search(param_re, content, re_flags): #missing; add to config 
            content += content_to_add 
        elif replace_if_exists: #replace in config
            content = re.sub(param_re, content_to_add, content, flags=re_flags)
        f = open(filename, 'w')
        f.write(content)
        f.close()

def modify_cp_config(param_re, content_to_add, replace_if_exists=True, config='counterpartyd', net='both'):
    assert config in ('counterpartyd', 'counterblockd', 'both')
    assert net in ('mainnet', 'testnet', 'both')
    cfg_filenames = []
    if config in ('counterpartyd', 'both'):
        if net in ('mainnet', 'both'):
            cfg_filenames.append(os.path.join(os.path.expanduser('~'+USERNAME), ".config", "counterpartyd", "counterpartyd.conf"))
        if net in ('testnet', 'both'):
            cfg_filenames.append(os.path.join(os.path.expanduser('~'+USERNAME), ".config", "counterpartyd-testnet", "counterpartyd.conf"))
    if config in ('counterblockd', 'both'):
        if net in ('mainnet', 'both'):
            cfg_filenames.append(os.path.join(os.path.expanduser('~'+USERNAME), ".config", "counterblockd", "counterblockd.conf"))
        if net in ('testnet', 'both'):
            cfg_filenames.append(os.path.join(os.path.expanduser('~'+USERNAME), ".config", "counterblockd-testnet", "counterblockd.conf"))
        
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
        
def git_repo_clone(branch, repo_dir, repo_url, run_as_user, hash=None):
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

    if hash:
        runcmd("cd ~%s/%s && git reset --hard %s" % (USERNAME, repo_dir, hash))
            
    runcmd("cd ~%s/%s && git config core.sharedRepository group && find ~%s/%s -type d -print0 | xargs -0 chmod g+s" % (
        USERNAME, repo_dir, USERNAME, repo_dir)) #to allow for group git actions 
    runcmd("chown -R %s:%s ~%s/%s" % (USERNAME, USERNAME, USERNAME, repo_dir))
    runcmd("chmod -R u+rw,g+rw,o+r,o-w ~%s/%s" % (USERNAME, repo_dir)) #just in case

def do_prerun_checks():
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
    if os.name == "posix" and "SUDO_USER" not in os.environ:
        logging.error("Please use `sudo` to run this script.")
        sys.exit(1)

def do_base_setup(run_as_user, branch, base_path, dist_path):
    """This creates the xcp and xcpd users and checks out the counterpartyd_build system from git"""
    #change time to UTC
    runcmd("ln -sf /usr/share/zoneinfo/UTC /etc/localtime")

    #install some necessary base deps
    runcmd("apt-get update")
    runcmd("apt-get -y install git-core software-properties-common python-software-properties build-essential ssl-cert ntp")
    runcmd("apt-get update")
    #node-gyp building for insight has ...issues out of the box on Ubuntu... use Chris Lea's nodejs build instead, which is newer
    runcmd("apt-get -y remove nodejs npm gyp")
    runcmd("add-apt-repository -y ppa:chris-lea/node.js")
    runcmd("apt-get update")
    runcmd("apt-get -y install nodejs") #includes npm
    
    #Create xcp user, under which the files will be stored, and who will own the files, etc
    try:
        pwd.getpwnam(USERNAME)
    except:
        logging.info("Creating user '%s' ..." % USERNAME)
        runcmd("adduser --system --disabled-password --shell /bin/false --group %s" % USERNAME)
        
    #Create xcpd user (to run counterpartyd, counterblockd, insight, bitcoind, nginx) if not already made
    try:
        pwd.getpwnam(DAEMON_USERNAME)
    except:
        logging.info("Creating user '%s' ..." % DAEMON_USERNAME)
        user_homedir = os.path.expanduser("~" + USERNAME)
        runcmd("adduser --system --disabled-password --shell /bin/false --ingroup nogroup --home %s %s" % (user_homedir, DAEMON_USERNAME))
    
    #add the run_as_user to the xcp group
    runcmd("adduser %s %s" % (run_as_user, USERNAME))
    
    #Check out counterpartyd-build repo under this user's home dir and use that for the build
    git_repo_clone(branch, "counterpartyd_build", REPO_COUNTERPARTYD_BUILD, run_as_user)

    #enhance fd limits for the xcpd user
    runcmd("cp -af %s/linux/other/xcpd_security_limits.conf /etc/security/limits.d/" % dist_path)

def do_security_setup(run_as_user, branch, base_path, dist_path):
    """Some helpful security-related tasks, to tighten up the box"""
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
            f, dotall=True, add_newline=False)
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
    runcmd("service auditd restart")

    #iwatch
    runcmd("apt-get -y install iwatch")
    modify_config(r'^START_DAEMON=.*?$', 'START_DAEMON=true', '/etc/default/iwatch')
    runcmd("install -m 0644 -o root -g root -D %s/linux/other/iwatch.xml /etc/iwatch/iwatch.xml" % dist_path)
    modify_config(r'guard email="root@localhost"', 'guard email="noreply@%s"' % socket.gethostname(), '/etc/iwatch/iwatch.xml')
    runcmd("service iwatch restart")

def do_bitcoind_setup(run_as_user, branch, base_path, dist_path, run_mode):
    """Installs and configures bitcoind"""
    user_homedir = os.path.expanduser("~" + USERNAME)
    bitcoind_rpc_password = pass_generator()
    bitcoind_rpc_password_testnet = pass_generator()
    
    #Install bitcoind
    BITCOIND_VER = "0.9.2.1"
    runcmd("rm -rf /tmp/bitcoind.tar.gz /tmp/bitcoin-%s-linux" % BITCOIND_VER)
    runcmd("wget -O /tmp/bitcoind.tar.gz https://bitcoin.org/bin/%s/bitcoin-%s-linux.tar.gz" % (BITCOIND_VER, BITCOIND_VER))
    runcmd("tar -C /tmp -zxvf /tmp/bitcoind.tar.gz")
    runcmd("cp -af /tmp/bitcoin-%s-linux/bin/64/bitcoind /usr/bin" % BITCOIND_VER)
    runcmd("cp -af /tmp/bitcoin-%s-linux/bin/64/bitcoin-cli /usr/bin" % BITCOIND_VER)
    runcmd("rm -rf /tmp/bitcoind.tar.gz /tmp/bitcoin-%s-linux" % BITCOIND_VER)

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
    runcmd("rm -f /etc/init/bitcoin.conf /etc/init/bitcoin-testnet.conf")
    runcmd("cp -af %s/linux/init/bitcoind.conf.template /etc/init/bitcoind.conf" % dist_path)
    runcmd("sed -ri \"s/\!RUN_AS_USER\!/%s/g\" /etc/init/bitcoind.conf" % DAEMON_USERNAME)
    runcmd("sed -ri \"s/\!USER_HOMEDIR\!/%s/g\" /etc/init/bitcoind.conf" % user_homedir.replace('/', '\/'))
    runcmd("cp -af %s/linux/init/bitcoind-testnet.conf.template /etc/init/bitcoind-testnet.conf" % dist_path)
    runcmd("sed -ri \"s/\!RUN_AS_USER\!/%s/g\" /etc/init/bitcoind-testnet.conf" % DAEMON_USERNAME)
    runcmd("sed -ri \"s/\!USER_HOMEDIR\!/%s/g\" /etc/init/bitcoind-testnet.conf" % user_homedir.replace('/', '\/'))
    
    #install logrotate file
    runcmd("cp -af %s/linux/logrotate/bitcoind /etc/logrotate.d/bitcoind" % dist_path)
    runcmd("sed -ri \"s/\!USER_HOMEDIR\!/%s/g\" /etc/logrotate.d/bitcoind" % user_homedir.replace('/', '\/'))
    
    #disable upstart scripts from autostarting on system boot if necessary
    if run_mode == 't': #disable mainnet daemons from autostarting
        runcmd(r"""bash -c "echo 'manual' >> /etc/init/bitcoind.override" """)
    else:
        runcmd("rm -f /etc/init/bitcoind.override")
    if run_mode == 'm': #disable testnet daemons from autostarting
        runcmd(r"""bash -c "echo 'manual' >> /etc/init/bitcoind-testnet.override" """)
    else:
        runcmd("rm -f /etc/init/bitcoind-testnet.override")
        
    runcmd("chown -R %s:%s ~%s/.bitcoin ~%s/.bitcoin-testnet" % (DAEMON_USERNAME, USERNAME, USERNAME, USERNAME))
    
    return bitcoind_rpc_password, bitcoind_rpc_password_testnet

def do_counterparty_setup(role, run_as_user, branch, base_path, dist_path, run_mode, bitcoind_rpc_password,
bitcoind_rpc_password_testnet, counterpartyd_public, counterwallet_support_email):
    """Installs and configures counterpartyd and counterblockd"""
    user_homedir = os.path.expanduser("~" + USERNAME)
    counterpartyd_rpc_password = '1234' if role == 'counterpartyd_only' and counterpartyd_public == 'y' else pass_generator()
    counterpartyd_rpc_password_testnet = '1234' if role == 'counterpartyd_only' and counterpartyd_public == 'y' else pass_generator()
    
    #Run setup.py (as the XCP user, who runs it sudoed) to install and set up counterpartyd, counterblockd
    # as -y is specified, this will auto install counterblockd full node (mongo and redis) as well as setting
    # counterpartyd/counterblockd to start up at startup for both mainnet and testnet (we will override this as necessary
    # based on run_mode later in this function)
    runcmd("~%s/counterpartyd_build/setup.py -y %s --with-testnet --for-user=%s" % (
        USERNAME, '--with-counterblockd' if role != 'counterpartyd_only' else '', USERNAME))
    runcmd("cd ~%s/counterpartyd_build && git config core.sharedRepository group && find ~%s/counterpartyd_build -type d -print0 | xargs -0 chmod g+s" % (
        USERNAME, USERNAME)) #to allow for group git actions 
    runcmd("chown -R %s:%s ~%s/counterpartyd_build" % (USERNAME, USERNAME, USERNAME)) #just in case
    runcmd("chmod -R u+rw,g+rw,o+r,o-w ~%s/counterpartyd_build" % USERNAME) #just in case
    
    #now change the counterpartyd directories to be owned by the xcpd user (and the xcp group),
    # so that the xcpd account can write to the database, saved image files (counterblockd), log files, etc
    runcmd("mkdir -p ~%s/.config/counterpartyd ~%s/.config/counterpartyd-testnet" % (USERNAME, USERNAME))    
    runcmd("chown -R %s:%s ~%s/.config/counterpartyd ~%s/.config/counterpartyd-testnet" % (
        DAEMON_USERNAME, USERNAME, USERNAME, USERNAME))
    runcmd("sed -ri \"s/USER=%s/USER=%s/g\" /etc/init/counterpartyd.conf /etc/init/counterpartyd-testnet.conf" % (
        USERNAME, DAEMON_USERNAME))

    #modify the default stored bitcoind passwords in counterpartyd.conf
    modify_cp_config(r'^(backend|bitcoind)\-rpc\-password=.*?$',
        'backend-rpc-password=%s' % bitcoind_rpc_password, config='counterpartyd', net='mainnet')
    modify_cp_config(r'^(backend|bitcoind)\-rpc\-password=.*?$',
        'backend-rpc-password=%s' % bitcoind_rpc_password_testnet, config='counterpartyd', net='testnet')

    #modify the counterpartyd API rpc password in counterpartyd.conf
    modify_cp_config(r'^rpc\-password=.*?$', 'rpc-password=%s' % counterpartyd_rpc_password,
        config='counterpartyd', net='mainnet')
    modify_cp_config(r'^rpc\-password=.*?$', 'rpc-password=%s' % counterpartyd_rpc_password_testnet,
        config='counterpartyd', net='testnet')

    if role == 'counterpartyd_only' and counterpartyd_public == 'y':
        modify_cp_config(r'^rpc\-host=.*?$', 'rpc-host=0.0.0.0', config='counterpartyd')
    
    #disable upstart scripts from autostarting on system boot if necessary
    if run_mode == 't': #disable mainnet daemons from autostarting
        runcmd(r"""bash -c "echo 'manual' >> /etc/init/counterpartyd.override" """)
    else:
        runcmd("rm -f /etc/init/counterpartyd.override")
    if run_mode == 'm': #disable testnet daemons from autostarting
        runcmd(r"""bash -c "echo 'manual' >> /etc/init/counterpartyd-testnet.override" """)
    else:
        runcmd("rm -f /etc/init/counterpartyd-testnet.override")
        
    if role != 'counterpartyd_only':
        #now change the counterblockd directories to be owned by the xcpd user (and the xcp group),
        runcmd("mkdir -p ~%s/.config/counterblockd ~%s/.config/counterblockd-testnet" % (USERNAME, USERNAME))    
        runcmd("chown -R %s:%s ~%s/.config/counterblockd ~%s/.config/counterblockd-testnet" % (
            DAEMON_USERNAME, USERNAME, USERNAME, USERNAME))
        runcmd("sed -ri \"s/USER=%s/USER=%s/g\" /etc/init/counterblockd.conf /etc/init/counterblockd-testnet.conf" % (
            USERNAME, DAEMON_USERNAME))
        
        #modify the default stored bitcoind passwords in counterblockd.conf
        modify_cp_config(r'^(backend|bitcoind)\-rpc\-password=.*?$',
            'backend-rpc-password=%s' % bitcoind_rpc_password, config='counterblockd', net='mainnet')
        modify_cp_config(r'^(backend|bitcoind)\-rpc\-password=.*?$',
            'backend-rpc-password=%s' % bitcoind_rpc_password_testnet, config='counterblockd', net='testnet')
    
        #modify the counterpartyd API rpc password in counterblockd.conf
        modify_cp_config(r'^counterpartyd\-rpc\-password=.*?$',
            'counterpartyd-rpc-password=%s' % counterpartyd_rpc_password, config='counterblockd', net='mainnet')
        modify_cp_config(r'^counterpartyd\-rpc\-password=.*?$',
            'counterpartyd-rpc-password=%s' % counterpartyd_rpc_password_testnet, config='counterblockd', net='testnet')
        
        #role-specific counterblockd.conf values
        modify_cp_config(r'^auto\-btc\-escrow\-enable=.*?$', 'auto-btc-escrow-enable=%s' %
            '1' if role == 'btcpayescrow' else '0', config='counterblockd')
        modify_cp_config(r'^armory\-utxsvr\-enable=.*?$', 'armory-utxsvr-enable=%s' % 
            '1' if role == 'counterwallet' else '0', config='counterblockd')
        if role == 'counterwallet':
            modify_cp_config(r'^support\-email=.*?$', 'support-email=%s' % counterwallet_support_email,
                config='counterblockd') #may be blank string

        #disable upstart scripts from autostarting on system boot if necessary
        if run_mode == 't': #disable mainnet daemons from autostarting
            runcmd(r"""bash -c "echo 'manual' >> /etc/init/counterblockd.override" """)
        else:
            runcmd("rm -f /etc/init/counterblockd.override")
        if run_mode == 'm': #disable testnet daemons from autostarting
            runcmd(r"""bash -c "echo 'manual' >> /etc/init/counterblockd-testnet.override" """)
        else:
            runcmd("rm -f /etc/init/counterblockd-testnet.override")

def do_blockchain_service_setup(run_as_user, base_path, dist_path, run_mode, blockchain_service):
    def do_insight_setup():
        """This installs and configures insight"""
        assert blockchain_service
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
        git_repo_clone("master", "insight-api", "https://github.com/bitpay/insight-api.git",
            run_as_user, hash="c05761b98b70886d0700563628a510f89f87c03e") #insight 0.2.7
        runcmd("rm -rf ~%s/insight-api/node-modules && cd ~%s/insight-api && npm install" % (USERNAME, USERNAME))
        #Set up insight startup scripts (will be disabled later from autostarting on system startup if necessary)
        
        runcmd("rm -f /etc/init/insight.conf /etc/init/insight-testnet.conf")
        runcmd("cp -af %s/linux/init/insight.conf.template /etc/init/insight.conf" % dist_path)
        runcmd("sed -ri \"s/\!RUN_AS_USER\!/%s/g\" /etc/init/insight.conf" % DAEMON_USERNAME)
        runcmd("sed -ri \"s/\!USER_HOMEDIR\!/%s/g\" /etc/init/insight.conf" % user_homedir.replace('/', '\/'))
        runcmd("cp -af %s/linux/init/insight-testnet.conf.template /etc/init/insight-testnet.conf" % dist_path)
        runcmd("sed -ri \"s/\!RUN_AS_USER\!/%s/g\" /etc/init/insight-testnet.conf" % DAEMON_USERNAME)
        runcmd("sed -ri \"s/\!USER_HOMEDIR\!/%s/g\" /etc/init/insight-testnet.conf" % user_homedir.replace('/', '\/'))
        #install logrotate file
        runcmd("cp -af %s/linux/logrotate/insight /etc/logrotate.d/insight" % dist_path)
        runcmd("sed -ri \"s/\!RUN_AS_USER\!/%s/g\" /etc/logrotate.d/insight" % DAEMON_USERNAME)
        runcmd("sed -ri \"s/\!USER_HOMEDIR\!/%s/g\" /etc/logrotate.d/insight" % user_homedir.replace('/', '\/'))
    
        runcmd("mkdir -p ~%s/insight-api/db" % USERNAME)
        runcmd("chown -R %s:%s ~%s/insight-api" % (USERNAME, USERNAME, USERNAME))
        runcmd("chown -R %s:%s ~%s/insight-api/db" % (DAEMON_USERNAME, USERNAME, USERNAME))
        modify_cp_config(r'^blockchain\-service\-name=.*?$', 'blockchain-service-name=insight', config='both')
        
    def do_blockr_setup():
        modify_cp_config(r'^blockchain\-service\-name=.*?$', 'blockchain-service-name=blockr', config='both')
    
    #disable upstart scripts from autostarting on system boot if necessary
    if blockchain_service == 'i':
        do_insight_setup()
        if run_mode == 't': #disable mainnet daemons from autostarting
            runcmd(r"""bash -c "echo 'manual' >> /etc/init/insight.override" """)
        else:
            runcmd("rm -f /etc/init/insight.override")
        if run_mode == 'm': #disable testnet daemons from autostarting
            runcmd(r"""bash -c "echo 'manual' >> /etc/init/insight-testnet.override" """)
        else:
            runcmd("rm -f /etc/init/insight-testnet.override")
    else: #insight not being used as blockchain service
        runcmd("rm -f /etc/init/insight.override /etc/init/insight-testnet.override")
        #^ so insight doesn't start if it was in use before
        do_blockr_setup()

def do_nginx_setup(run_as_user, base_path, dist_path):
    #Build and install nginx (openresty) on Ubuntu
    #Most of these build commands from http://brian.akins.org/blog/2013/03/19/building-openresty-on-ubuntu/
    OPENRESTY_VER = "1.7.0.1"

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
    runcmd("update-rc.d nginx defaults")

def do_armory_utxsvr_setup(run_as_user, base_path, dist_path, run_mode, enable=True):
    user_homedir = os.path.expanduser("~" + USERNAME)
    
    runcmd("apt-get -y install xvfb python-qt4 python-twisted python-psutil xdg-utils")
    runcmd("rm -f /tmp/armory.deb")
    runcmd("wget -O /tmp/armory.deb https://s3.amazonaws.com/bitcoinarmory-releases/armory_0.92.1_ubuntu-64bit.deb")
    runcmd("mkdir -p /usr/share/desktop-directories/") #bug fix (see http://askubuntu.com/a/406015)
    runcmd("dpkg -i /tmp/armory.deb")
    runcmd("rm -f /tmp/armory.deb")

    runcmd("mkdir -p ~%s/.armory" % USERNAME)
    runcmd("chown -R %s:%s ~%s/.armory" % (DAEMON_USERNAME, USERNAME, USERNAME))
    
    runcmd("sudo ln -sf ~%s/.bitcoin-testnet/testnet3 ~%s/.bitcoin/" % (USERNAME, USERNAME))
    #^ ghetto hack, as armory has hardcoded dir settings in certain place
    
    #make a short script to launch armory_utxsvr
    f = open("/usr/local/bin/armory_utxsvr", 'w')
    f.write("#!/bin/sh\n%s/run.py armory_utxsvr \"$@\"" % base_path)
    f.close()
    runcmd("chmod +x /usr/local/bin/armory_utxsvr")

    #Set up upstart scripts (will be disabled later from autostarting on system startup if necessary)
    if enable:
        runcmd("rm -f /etc/init/armory_utxsvr.conf /etc/init/armory_utxsvr-testnet.conf")
        runcmd("cp -af %s/linux/init/armory_utxsvr.conf.template /etc/init/armory_utxsvr.conf" % dist_path)
        runcmd("sed -ri \"s/\!RUN_AS_USER\!/%s/g\" /etc/init/armory_utxsvr.conf" % DAEMON_USERNAME)
        runcmd("sed -ri \"s/\!USER_HOMEDIR\!/%s/g\" /etc/init/armory_utxsvr.conf" % user_homedir.replace('/', '\/'))
        runcmd("cp -af %s/linux/init/armory_utxsvr-testnet.conf.template /etc/init/armory_utxsvr-testnet.conf" % dist_path)
        runcmd("sed -ri \"s/\!RUN_AS_USER\!/%s/g\" /etc/init/armory_utxsvr-testnet.conf" % DAEMON_USERNAME)
        runcmd("sed -ri \"s/\!USER_HOMEDIR\!/%s/g\" /etc/init/armory_utxsvr-testnet.conf" % user_homedir.replace('/', '\/'))
    else: #disable
        runcmd("rm -f /etc/init/armory_utxsvr.conf /etc/init/armory_utxsvr-testnet.conf")

    #disable upstart scripts from autostarting on system boot if necessary
    if run_mode == 't': #disable mainnet daemons from autostarting
        runcmd(r"""bash -c "echo 'manual' >> /etc/init/armory_utxsvr.override" """)
    else:
        runcmd("rm -f /etc/init/armory_utxsvr.override")
    if run_mode == 'm': #disable testnet daemons from autostarting
        runcmd(r"""bash -c "echo 'manual' >> /etc/init/armory_utxsvr-testnet.override" """)
    else:
        runcmd("rm -f /etc/init/armory_utxsvr-testnet.override")

def do_counterwallet_setup(run_as_user, branch, updateOnly=False):
    #check out counterwallet from git
    git_repo_clone(branch, "counterwallet", REPO_COUNTERWALLET, run_as_user)
    if not updateOnly:
        runcmd("npm install -g grunt-cli bower")
    runcmd("cd ~%s/counterwallet/src && bower --allow-root --config.interactive=false install" % USERNAME)
    runcmd("cd ~%s/counterwallet && npm install" % USERNAME)
    runcmd("cd ~%s/counterwallet && grunt build" % USERNAME) #will generate the minified site
    runcmd("chown -R %s:%s ~%s/counterwallet" % (USERNAME, USERNAME, USERNAME)) #just in case
    runcmd("chmod -R u+rw,g+rw,o+r,o-w ~%s/counterwallet" % USERNAME) #just in case

def do_newrelic_setup(run_as_user, base_path, dist_path, run_mode):
    ##
    ## NOTE: NEW RELIC DAEMON CAUSES ISSUES WITH COUNTERBLOCKD (SOCKETS STICKING IN CLOSE_WAIT STATE)
    ##  -- DO NOT USE IT FOR COUNTERBLOCKD MONITORING
    ##
    NR_PREFS_LICENSE_KEY_PATH = "/etc/newrelic/LICENSE_KEY"
    NR_PREFS_HOSTNAME_PATH = "/etc/newrelic/HOSTNAME"
    
    runcmd("mkdir -p /etc/newrelic /var/log/newrelic /var/run/newrelic")
    runcmd("chown %s:%s /etc/newrelic /var/log/newrelic /var/run/newrelic" % (DAEMON_USERNAME, USERNAME))
    
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
            nr_license_key_confirm = ask_question("You entererd '%s', is that right? (Y/n): " % nr_license_key, ('y', 'n'), 'y') 
            if nr_license_key_confirm == 'y': break
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
            nr_hostname_confirm = ask_question("You entererd '%s', is that right? (Y/n): " % nr_hostname, ('y', 'n'), 'y')
            if nr_hostname_confirm == 'y': break
        open(NR_PREFS_HOSTNAME_PATH, 'w').write(nr_hostname)
    assert nr_hostname
    logging.info("NewRelic hostname/app prefix: %s" % nr_hostname)

    #install some deps...
    runcmd("sudo apt-get -y install libyaml-dev")
    
    #install/setup python agent for both counterpartyd and counterblockd
    #counterpartyd
    runcmd("%s/env/bin/pip install newrelic" % base_path)
    runcmd("cp -af %s/linux/newrelic/nr_counterpartyd.ini.template /etc/newrelic/nr_counterpartyd.ini" % dist_path)
    runcmd("sed -ri \"s/\!LICENSE_KEY\!/%s/g\" /etc/newrelic/nr_counterpartyd.ini" % nr_license_key)
    runcmd("sed -ri \"s/\!HOSTNAME\!/%s/g\" /etc/newrelic/nr_counterpartyd.ini" % nr_hostname)
    #counterblockd
    runcmd("%s/env.counterblockd/bin/pip install newrelic" % base_path)
    runcmd("cp -af %s/linux/newrelic/nr_counterblockd.ini.template /etc/newrelic/nr_counterblockd.ini" % dist_path)
    runcmd("sed -ri \"s/\!LICENSE_KEY\!/%s/g\" /etc/newrelic/nr_counterblockd.ini" % nr_license_key)
    runcmd("sed -ri \"s/\!HOSTNAME\!/%s/g\" /etc/newrelic/nr_counterblockd.ini" % nr_hostname)
    #install init scripts (overwrite the existing ones for now at least)
    runcmd("cp -af %s/linux/newrelic/init/nr-counterpartyd.conf /etc/init/counterpartyd.conf" % dist_path) #overwrite
    #runcmd("cp -af %s/linux/newrelic/init/nr-counterblockd.conf /etc/init/counterblockd.conf" % dist_path) #overwrite
    runcmd("cp -af %s/linux/newrelic/init/nr-counterpartyd-testnet.conf /etc/init/counterpartyd-testnet.conf" % dist_path) #overwrite
    #runcmd("cp -af %s/linux/newrelic/init/nr-counterblockd-testnet.conf /etc/init/counterblockd-testnet.conf" % dist_path) #overwrite
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
    runcmd("pip install newrelic_plugin_agent pymongo")
    runcmd("cp -af %s/linux/newrelic/newrelic-plugin-agent.cfg.template /etc/newrelic/newrelic-plugin-agent.cfg" % dist_path)
    runcmd("sed -ri \"s/\!LICENSE_KEY\!/%s/g\" /etc/newrelic/newrelic-plugin-agent.cfg" % nr_license_key)
    runcmd("sed -ri \"s/\!HOSTNAME\!/%s/g\" /etc/newrelic/newrelic-plugin-agent.cfg" % nr_hostname)
    runcmd("ln -sf %s/linux/newrelic/init/newrelic-plugin-agent /etc/init.d/newrelic-plugin-agent" % dist_path)
    runcmd("update-rc.d newrelic-plugin-agent defaults")
    runcmd("/etc/init.d/newrelic-plugin-agent restart")
    
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
    
def command_services(command, prompt=False):
    assert command in ("stop", "restart")
    
    if prompt:
        confirmation = ask_question("%s services? (y/N)" % command.capitalize(), ('y', 'n',), 'n')
        if confirmation == 'n':
            return False
    
    #restart/shutdown services if they may be running on the box
    if os.path.exists("/etc/init.d/iwatch"):
        runcmd("service iwatch %s" % command, abort_on_failure=False)
    if os.path.exists("/etc/init/counterpartyd.conf"):
        logging.warn("STOPPING SERVICES" if command == 'stop' else "RESTARTING SERVICES")
        runcmd("service bitcoind %s" % command, abort_on_failure=False)
        runcmd("service bitcoind-testnet %s" % command, abort_on_failure=False)
        
        if os.path.exists("/etc/init/insight.conf"):
            if command == "restart":
                logging.info("Waiting 45 seconds before starting insight, to allow bitcoind to fully initialize...")
                time.sleep(45)
            runcmd("service insight %s" % command, abort_on_failure=False)
            runcmd("service insight-testnet %s" % command, abort_on_failure=False)
        
        runcmd("service counterpartyd %s" % command, abort_on_failure=False)
        runcmd("service counterpartyd-testnet %s" % command, abort_on_failure=False)
        runcmd("service counterblockd %s" % command, abort_on_failure=False)
        runcmd("service counterblockd-testnet %s" % command, abort_on_failure=False)
        if os.path.exists("/etc/init/armory_utxsvr.conf"):
            runcmd("service armory_utxsvr %s" % command, abort_on_failure=False)
            runcmd("service armory_utxsvr-testnet %s" % command, abort_on_failure=False)
        return True

QUESTION_FLAGS = collections.OrderedDict({
    "op": ('u', 'r'),
    "role": ('counterwallet', 'vendingmachine', 'blockexplorer', 'counterpartyd_only', 'btcpayescrow'),
    "branch": ('master', 'develop'),
    "run_mode": ('t', 'm', 'b'),
    "blockchain_service": ('b', 'i'),
    "security_hardening": ('y', 'n'),
    "counterpartyd_public": ('y', 'n'),
    "counterwallet_support_email": None
})

def gather_build_questions(answered_questions):
    if 'role' not in answered_questions:
        role = ask_question("Enter the number for the role you want to build:\n"
                + "\t1: Counterwallet server\n\t2: Vending machine\n\t3: Blockexplorer server\n"
                + "\t4: counterpartyd-only\n\t5: BTCPay Escrow Server\n"
                + "Your choice",
            ('1', '2', '3', '4', '5'), '1')
        if role == '1':
            role = 'counterwallet'
            role_desc = "Counterwallet server"
        elif role == '2':
            role = 'vendingmachine'
            role_desc = "Vending machine/gateway"
        elif role == '3':
            role = 'blockexplorer'
            role_desc = "Block explorer server"
        elif role == '4':
            role = 'counterpartyd_only'
            role_desc = "Counterpartyd server"
        elif role == '5':
            role = 'btcpayescrow'
            role_desc = "BTCPay escrow server"
        print("\tBuilding a %s" % role_desc)
        answered_questions['role'] = role
    assert answered_questions['role'] in QUESTION_FLAGS['role']
    if answered_questions['role'] in ('vendingmachine', 'blockexplorer'):
        raise NotImplementedError("This role not implemented yet...")

    if 'branch' not in answered_questions:
        branch = ask_question("Build from branch (M)aster or (d)evelop? (M/d)", ('m', 'd'), 'm')
        if branch == 'm': branch = 'master'
        elif branch == 'd': branch = 'develop'
        print("\tWorking with branch: %s" % branch)
        answered_questions['branch'] = branch
    assert answered_questions['branch'] in QUESTION_FLAGS['branch']

    if 'run_mode' not in answered_questions:
        answered_questions['run_mode'] = ask_question("Run as (t)estnet node, (m)ainnet node, or (B)oth? (t/m/B)", ('t', 'm', 'b'), 'b')
        print("\tSetting up to run on %s" % ('testnet' if answered_questions['run_mode'].lower() == 't' 
            else ('mainnet' if answered_questions['run_mode'].lower() == 'm' else 'testnet and mainnet')))
    assert answered_questions['run_mode'] in QUESTION_FLAGS['run_mode']

    if 'blockchain_service' not in answered_questions:
        answered_questions['blockchain_service'] = ask_question("Blockchain services, use (B)lockr.io (remote) or (i)nsight (local)? (B/i)", ('b', 'i'), 'b')
        print("\tUsing %s" % ('blockr.io' if answered_questions['blockchain_service'] == 'b' else 'insight'))
    assert answered_questions['blockchain_service'] in QUESTION_FLAGS['blockchain_service']
    
    if role == 'counterpartyd_only' and 'counterpartyd_public' not in answered_questions:
        answered_questions['counterpartyd_public'] = ask_question(
            "Enable public Counterpartyd setup (listen on all hosts w/ rpc/1234 user) (Y/n)", ('y', 'n'), 'y')
    else:
        answered_questions['counterpartyd_public'] = answered_questions.get('counterpartyd_public', 'n') #does not apply
    assert answered_questions['counterpartyd_public'] in QUESTION_FLAGS['counterpartyd_public']

    counterwallet_support_email = None
    if role == 'counterwallet' and 'counterwallet_support_email' not in answered_questions:
        while True:
            counterwallet_support_email = input("Email address where support cases should go (blank to disable): ")
            counterwallet_support_email = counterwallet_support_email.strip()
            if counterwallet_support_email:
                counterwallet_support_email_confirm = ask_question(
                    "You entererd '%s', is that right? (Y/n): " % counterwallet_support_email, ('y', 'n'), 'y') 
                if counterwallet_support_email_confirm == 'y': break
            else: break
        answered_questions['counterwallet_support_email'] = counterwallet_support_email
    else:
        answered_questions['counterwallet_support_email'] = answered_questions.get('counterwallet_support_email', '') 

    if 'security_hardening' not in answered_questions:
        answered_questions['security_hardening'] = ask_question("Set up security hardening? (Y/n)", ('y', 'n'), 'y')
    assert answered_questions['security_hardening'] in QUESTION_FLAGS['security_hardening']
    return answered_questions

def usage():
    print("SYNTAX: %s [-h] %s" % (sys.argv[0], ' '.join([('[-%s=%s]' % (q, '|'.join(v) if v else '')) for q, v in QUESTION_FLAGS.items()])))

def main():
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s|%(levelname)s: %(message)s')
    do_prerun_checks()
    run_as_user = os.environ["SUDO_USER"]
    assert run_as_user
    answered_questions = {}

    #parse any command line objects
    branch = "master"
    try:
        opts, args = getopt.getopt(sys.argv[1:], "h", ["help",] + ['%s=' % q for q in QUESTION_FLAGS.keys()])
    except getopt.GetoptError as err:
        usage()
        sys.exit(2)
    for o, a in opts:
        if o in ("-h", "--help"):
            usage()
            sys.exit()
        elif o in ['--%s' % q for q in QUESTION_FLAGS.keys()]: #process flags for non-interactivity
            answered_questions[o.lstrip('-')] = a
        else:
            assert False, "Unhandled or unimplemented switch or option"

    base_path = os.path.expanduser("~%s/counterpartyd_build" % USERNAME)
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
                "It appears this setup has been run already. (r)ebuild node, or just (U)pdate from git? (r/U)",
                ('r', 'u'), 'u')
            assert answered_questions['op'] in QUESTION_FLAGS['op']

    if answered_questions['op'] == 'u': #just refresh counterpartyd, counterblockd, and counterwallet, etc. from github
        if os.path.exists("/etc/init.d/iwatch"):
            runcmd("service iwatch stop", abort_on_failure=False)
        
        #refresh counterpartyd_build, counterpartyd and counterblockd (if available)
        runcmd("%s/setup.py %s --for-user=xcp update" % (base_path,
            '--with-counterblockd' if os.path.exists(os.path.join(dist_path, "counterblockd")) else ''))
        
        #refresh counterwallet (if available)
        if os.path.exists(os.path.exists(os.path.expanduser("~%s/counterwallet" % USERNAME))):
            do_counterwallet_setup(run_as_user, "AUTO", updateOnly=True)

        #offer to restart services
        restarted = command_services("restart", prompt=True)
        if not restarted and os.path.exists("/etc/init.d/iwatch"):
            runcmd("service iwatch start", abort_on_failure=False)
        sys.exit(0) #all done

    #If here, a) federated node has not been set up yet or b) the user wants a rebuild
    answered_questions = gather_build_questions(answered_questions)
    
    command_services("stop")

    do_base_setup(run_as_user, answered_questions['branch'], base_path, dist_path)
    
    bitcoind_rpc_password, bitcoind_rpc_password_testnet \
        = do_bitcoind_setup(run_as_user, answered_questions['branch'], base_path, dist_path, answered_questions['run_mode'])
    
    do_counterparty_setup(answered_questions['role'], run_as_user, answered_questions['branch'], base_path, dist_path, answered_questions['run_mode'],
        bitcoind_rpc_password, bitcoind_rpc_password_testnet,
        answered_questions['counterpartyd_public'], answered_questions['counterwallet_support_email'])
    
    do_blockchain_service_setup(run_as_user, base_path, dist_path,
        answered_questions['run_mode'], answered_questions['blockchain_service'])
    
    if answered_questions['role'] != "counterpartyd_only":
        do_nginx_setup(run_as_user, base_path, dist_path)
    
    do_armory_utxsvr_setup(run_as_user, base_path, dist_path,
        answered_questions['run_mode'], enable=answered_questions['role']=='counterwallet')
    if answered_questions['role'] == 'counterwallet':
        do_counterwallet_setup(run_as_user, answered_questions['branch'])

    do_newrelic_setup(run_as_user, base_path, dist_path, answered_questions['run_mode']) #optional
    
    if answered_questions['security_hardening']:
        do_security_setup(run_as_user, answered_questions['branch'], base_path, dist_path)
    
    logging.info("Counterblock Federated Node Build Complete (whew).")
    command_services("restart", prompt=True)


if __name__ == "__main__":
    main()
