import os
import sys
import logging
import getopt

from ...setup_util import *

USERNAME = "xcp"
DAEMON_USERNAME = "xcpd"
USER_HOMEDIR = "/home/xcp"

def usage():
    print("SYNTAX: %s [-h] [--get-bitcoind-data] [--get-counterpartyd-data] [--get-testnet-data]" % sys.argv[0])

def main():
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s|%(levelname)s: %(message)s')
    do_federated_node_prerun_checks()
    run_as_user = os.environ["SUDO_USER"]
    assert run_as_user

    #parse any command line objects
    get_bitcoind_data = False
    get_counterpartyd_data = False
    get_testnet_data = False
    try:
        opts, args = getopt.getopt(sys.argv[1:], "h", ["help", "get-bitcoind-data", "get-counterpartyd-data", "get-testnet-data",])
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
    if get_bitcoind_data:
        logging.info("Downloading bitcoind mainnet bootstrap.dat ...")
        runcmd("echo \"killall transmission-cli\" > /tmp/torrentfinish.sh && chmod +x /tmp/torrentfinish.sh")
        runcmd("transmission-cli -w %s/.bitcoind/ -f /tmp/torrentfinish.sh https://bitcoin.org/bin/blockchain/bootstrap.dat.torrent" % USER_HOME)
        runcmd("chown -R %s:%s %s/.bitcoind/" % (DAEMON_USERNAME, USERNAME, USER_HOMEDIR))
        runcmd("rm /tmp/torrentfinish.sh")
        if get_testnet_data:
            logging.info("No bitcoin testnet bootstrap.dat file support yet. Skipping...")
    
    if get_counterpartyd_data:
        runcmd("wget -O /tmp/counterpartyd-db.latest.tar.gz %s/ https://bootstrap.counterpartyd.co/counterpartyd-db.latest.tar.gz")
        runcmd("rm -f %s/.config/counterpartyd/counterpartyd.*.db* && tar -C %s/.config/counterpartyd -zxvf /tmp/counterpartyd-db.latest.tar.gz" % (USER_HOME, USER_HOME))
        runcmd("chown -R %s:%s %s/.config/counterpartyd/" % (DAEMON_USERNAME, USERNAME, USER_HOMEDIR))
        if get_testnet_data:
            runcmd("wget -O /tmp/counterpartyd-testnet-db.latest.tar.gz %s/ https://bootstrap.counterpartyd.co/counterpartyd-testnet-db.latest.tar.gz")
            runcmd("rm -f %s/.config/counterpartyd-testnet/counterpartyd.*.db* && tar -C %s/.config/counterpartyd-testnet -zxvf /tmp/counterpartyd-testnet-db.latest.tar.gz" % (USER_HOME, USER_HOME))
            runcmd("chown -R %s:%s %s/.config/counterpartyd-testnet/" % (DAEMON_USERNAME, USERNAME, USER_HOMEDIR))

if __name__ == "__main__":
    main()
