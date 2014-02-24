#! /usr/bin/env python3
"""
Sets up an Ubuntu 13.10 x64 server to be a counterwallet federated node.

NOTE: The system should be properly secured before running this script.

TODO: This is admittedly a (bit of a) hack. In the future, take this kind of functionality out to a .deb with
      a postinst script to do all of this, possibly.
"""
import os
import sys
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

def do_setup(branch):
    user_homedir = os.path.expanduser("~" + USERNAME)
    bitcoind_rpc_password = pass_generator()
    bitcoind_rpc_password_testnet = pass_generator()
    counterpartyd_rpc_password = pass_generator()
    counterpartyd_rpc_password_testnet = pass_generator()
    
    while True:
        run_mode = input("Run as (t)estnet node, (m)ainnet node, or (b)oth? (t/m/b): ")
        if run_mode.lower() not in ('t', 'm', 'b'):
            logging.error("Please enter 't' or 'm' or 'b'")
        else:
            break
    
    #Install bitcoind
    runcmd("sudo apt-get -y install git-core software-properties-common python-software-properties")
    runcmd("sudo add-apt-repository -y ppa:bitcoin/bitcoin")
    runcmd("sudo apt-get update")
    runcmd("sudo apt-get -y install bitcoind")
    
    #Create xcp user (to run bitcoind, counterpartyd, counterwalletd)
    try:
        pwd.getpwnam(USERNAME)
    except:
        logging.info("Creating user '%s' ..." % USERNAME)
        runcmd("sudo adduser --system --disabled-password --shell /bin/bash --group %s" % USERNAME)

    #Do basic inital bitcoin config (for both testnet and mainnet)
    runcmd("sudo mkdir -p ~%s/.bitcoin ~%s/.bitcoin-testnet" % (USERNAME, USERNAME))
    if not os.path.exists(os.path.join(user_homedir, '.bitcoin', 'bitcoin.conf')):
        runcmd(r"""sudo bash -c 'echo -e "rpcuser=rpc\nrpcpassword=%s\nserver=1\ndaemon=1\ntxindex=1" > ~%s/.bitcoin/bitcoin.conf'""" % (
            bitcoind_rpc_password, USERNAME))
    else: #grab the existing RPC password
        bitcoind_rpc_password = subprocess.check_output(
            r"""sudo bash -c "cat ~%s/.bitcoin/bitcoin.conf | sed -n 's/.*rpcpassword=\([^ \n]*\).*/\1/p'" """ % USERNAME, shell=True).decode('utf-8')
    if not os.path.exists(os.path.join(user_homedir, '.bitcoin-testnet', 'bitcoin.conf')):
        runcmd(r"""sudo bash -c 'echo -e "rpcuser=rpc\nrpcpassword=%s\nserver=1\ndaemon=1\ntxindex=1\ntestnet=1" > ~%s/.bitcoin-testnet/bitcoin.conf'""" % (
            bitcoind_rpc_password_testnet, USERNAME))
    else:
        bitcoind_rpc_password_testnet = subprocess.check_output(
            r"""sudo bash -c "cat ~%s/.bitcoin-testnet/bitcoin.conf | sed -n 's/.*rpcpassword=\([^ \n]*\).*/\1/p'" """
            % USERNAME, shell=True).decode('utf-8')
    
    #Check out counterpartyd-build repo under this user's home dir and use that for the build
    if os.path.exists(os.path.expanduser("~%s/counterpartyd_build" % USERNAME)):
        runcmd("cd ~%s/counterpartyd_build && git pull origin %s" % (USERNAME, branch))
    else:
        runcmd("sudo git clone -b %s https://github.com/xnova/counterpartyd_build.git ~%s/counterpartyd_build" % (branch, USERNAME))
    runcmd("sudo chown -R %s:%s ~%s/counterpartyd_build" % (USERNAME, USERNAME, USERNAME))
    base_path = os.path.expanduser("%s/counterpartyd_build" % USERNAME)
    dist_path = os.path.join(base_path, "dist")

    #Set up bitcoind startup scripts (will be disabled later from autostarting on system startup if necessary)
    runcmd("sudo cp -af %s/linux/init/bitcoind.conf.template /etc/init/bitcoind.conf" % dist_path)
    runcmd("sudo sed -rie \"s/\!RUN_AS_USER\!/%s/g\" /etc/init/bitcoind.conf" % USERNAME)
    runcmd("sudo cp -af %s/linux/init/bitcoind-testnet.conf.template /etc/init/bitcoind-testnet.conf" % dist_path)
    runcmd("sudo sed -rie \"s/\!RUN_AS_USER\!/%s/g\" /etc/init/bitcoind-testnet.conf" % USERNAME)

    #Run setup.py (as the XCP user, who runs it sudoed) to install and set up counterpartyd, counterwalletd
    # as -y is specified, this will auto install counterwalletd full node (mongo and redis) as well as setting
    # counterpartyd/counterwalletd to start up at startup for both mainnet and testnet (we will override this as necessary
    # based on run_mode later in this function)
    runcmd("sudo ~%s/counterpartyd_build/setup.py -y --with-counterwalletd --with-testnet --for-user=%s" % (USERNAME, USERNAME))
    
    #modify the default stored bitcoind passwords in counterparty.conf and counterwallet.conf
    runcmd(r"""sudo sed -r -i -e "s/^bitcoind\-rpc\-password=.*?$/bitcoind-rpc-password=%s/g" ~%s/.config/counterpartyd/counterpartyd.conf""" % (
        bitcoind_rpc_password, USERNAME))
    runcmd(r"""sudo sed -r -i -e "s/^bitcoind\-rpc\-password=.*?$/bitcoind-rpc-password=%s/g" ~%s/.config/counterpartyd-testnet/counterpartyd.conf""" % (
        bitcoind_rpc_password_testnet, USERNAME))
    runcmd(r"""sudo sed -r -i -e "s/^bitcoind\-rpc\-password=.*?$/bitcoind-rpc-password=%s/g" ~%s/.config/counterwalletd/counterwalletd.conf""" % (
        bitcoind_rpc_password, USERNAME))
    runcmd(r"""sudo sed -r -i -e "s/^bitcoind\-rpc\-password=.*?$/bitcoind-rpc-password=%s/g" ~%s/.config/counterwalletd-testnet/counterwalletd.conf""" % (
        bitcoind_rpc_password_testnet, USERNAME))
    #modify the counterpartyd API rpc password in both counterpartyd and counterwalletd
    runcmd(r"""sudo sed -r -i -e "s/^rpc\-password=.*?$/rpc-password=%s/g" ~%s/.config/counterpartyd/counterpartyd.conf""" % (
        counterpartyd_rpc_password, USERNAME))
    runcmd(r"""sudo sed -r -i -e "s/^rpc\-password=.*?$/rpc-password=%s/g" ~%s/.config/counterpartyd-testnet/counterpartyd.conf""" % (
        counterpartyd_rpc_password_testnet, USERNAME))
    runcmd(r"""sudo sed -r -i -e "s/^counterpartyd\-rpc\-password=.*?$/counterpartyd-rpc-password=%s/g" ~%s/.config/counterwalletd/counterwalletd.conf""" % (
        counterpartyd_rpc_password, USERNAME))
    runcmd(r"""sudo sed -r -i -e "s/^counterpartyd\-rpc\-password=.*?$/counterpartyd-rpc-password=%s/g" ~%s/.config/counterwalletd-testnet/counterwalletd.conf""" % (
        counterpartyd_rpc_password_testnet, USERNAME))
    
    #disable upstart scripts from autostarting on system boot if necessary
    if run_mode == 't': #disable mainnet daemons from autostarting
        runcmd(r"""sudo bash -c "echo 'manual' >> /etc/init/bitcoind.override" """)
        runcmd(r"""sudo bash -c "echo 'manual' >> /etc/init/counterpartyd.override" """)
        runcmd(r"""sudo bash -c "echo 'manual' >> /etc/init/counterwalletd.override" """)
    else:
        runcmd("sudo rm -f /etc/init/bitcoind.override /etc/init/counterpartyd.override /etc/init/counterwalletd.override")
    if run_mode == 'm': #disable testnet daemons from autostarting
        runcmd(r"""sudo bash -c "echo 'manual' >> /etc/init/bitcoind-testnet.override" """)
        runcmd(r"""sudo bash -c "echo 'manual' >> /etc/init/counterpartyd-testnet.override" """)
        runcmd(r"""sudo bash -c "echo 'manual' >> /etc/init/counterwalletd-testnet.override" """)
    else:
        runcmd("sudo rm -f /etc/init/bitcoind-testnet.override /etc/init/counterpartyd-testnet.override /etc/init/counterwalletd-testnet.override")
    
    #change ownership
    runcmd("sudo chown -R %s:%s ~%s/.bitcoin ~%s/.config/counterpartyd ~%s/.config/counterwalletd" % (
        USERNAME, USERNAME, USERNAME, USERNAME, USERNAME))
    runcmd("sudo chown -R %s:%s ~%s/.bitcoin-testnet ~%s/.config/counterpartyd-testnet ~%s/.config/counterwalletd-testnet" % (
        USERNAME, USERNAME, USERNAME, USERNAME, USERNAME))
    

def main():
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s|%(levelname)s: %(message)s')
    do_prerun_checks()

    #parse any command line objects
    branch = "master"
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hb:", ["help", "branch"])
    except getopt.GetoptError as err:
        usage()
        sys.exit(2)
    for o, a in opts:
        if o in ("-h", "--help"):
            usage()
            sys.exit()
        elif o in ("-b", "--branch"):
            branch = a
            if branch not in ("master", "develop"):
                logging.error("branch must be 'master' or 'develop'")
                sys.exit(2)
        else:
            assert False, "Unhandled or unimplemented switch or option"
    
    logging.info("Working with branch: %s" % branch)
    do_setup(branch)        
    logging.info("Counterwallet Federated Node Build Complete. Please reboot to start installed services.")


if __name__ == "__main__":
    main()
