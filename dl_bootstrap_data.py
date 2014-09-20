"""
download bootstrap data (for federated node use only)
"""
import os
import sys
import glob
import logging
import getopt

from setup_util import *

USERNAME = "xcp"
DAEMON_USERNAME = "xcpd"
USER_HOMEDIR = "/home/xcp"

def usage():
    print("SYNTAX: %s [-h] [--get-bitcoind-data] [--get-counterpartyd-data] [--get-testnet-data]" % sys.argv[0])

def main():
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s|%(levelname)s: %(message)s')
    do_federated_node_prerun_checks(require_sudo=False)

    #parse any command line objects
    get_bitcoind_data = False
    get_counterpartyd_data = False
    get_testnet_data = False
    force = False #by default, skip if the data exists
    try:
        opts, args = getopt.getopt(sys.argv[1:], "h", ["help", "force", "get-bitcoind-data", "get-counterpartyd-data", "get-testnet-data",])
    except getopt.GetoptError as err:
        usage()
        sys.exit(2)
    mode = None
    for o, a in opts:
        if o in ("--get-bitcoind-data",):
            get_bitcoind_data = True
        elif o in ("--get-bitcoind-data",):
            get_counterpartyd_data = True
        elif o in ("--get-testnet-data",):
            get_testnet_data = True
        elif o in ("--force",):
            force = True
        elif o in ("-h", "--help"):
            usage()
            sys.exit()
        else:
            assert False, "Unhandled or unimplemented switch or option"

    #fetch bittorrent client
    runcmd("apt-get -y install transmission-cli")
    
    #stop services just in case
    runcmd("sv stop counterpartyd", abort_on_failure=False)
    runcmd("sv stop counterpartyd-testnet", abort_on_failure=False)
    
    #download bitcoin bootstrap data (no testnet present)
    bitcoind_data_exists = os.path.exists("%s/.bitcoin/blocks" % USER_HOMEDIR)
    if get_bitcoind_data and (force or not bitcoind_data_exists):
        logging.info("Downloading bitcoind mainnet bootstrap.dat ...")
        runcmd("echo \"killall transmission-cli\" > /tmp/torrentfinish.sh && chmod +x /tmp/torrentfinish.sh")
        runcmd("transmission-cli -w %s/.bitcoin/ -f /tmp/torrentfinish.sh https://bitcoin.org/bin/blockchain/bootstrap.dat.torrent" % USER_HOME)
        runcmd("chown -R %s:%s %s/.bitcoind/" % (DAEMON_USERNAME, USERNAME, USER_HOMEDIR))
        runcmd("rm /tmp/torrentfinish.sh")
        if get_testnet_data:
            logging.info("No bitcoin testnet bootstrap.dat file support yet. Skipping...")
    
    counterpartyd_data_exists = bool(glob.glob("%s/.config/counterpartyd/counterpartyd.*.db" % USER_HOMEDIR))
    counterpartyd_testnet_data_exists = bool(glob.glob("%s/.config/counterpartyd-testnet/counterpartyd.*.db" % USER_HOMEDIR))
    if get_counterpartyd_data and (force or not counterpartyd_data_exists):
        fetch_counterpartyd_bootstrap_db("%s/.config/counterpartyd/" % USER_HOMEDIR, testnet=False,
            chown_user="%s:%s" % (DAEMON_USERNAME, USERNAME))
        if get_testnet_data and (force or not counterpartyd_testnet_data_exists):
            fetch_counterpartyd_bootstrap_db("%s/.config/counterpartyd-testnet/" % USER_HOMEDIR, testnet=True,
                chown_user="%s:%s" % (DAEMON_USERNAME, USERNAME))

if __name__ == "__main__":
    main()
