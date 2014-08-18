import os
import sys
import logging
import getopt

from ...setup_util import *

USERNAME = "xcp"
DAEMON_USERNAME = "xcpd"
USER_HOMEDIR = "/home/xcp"

def usage():
    print("SYNTAX: %s [-h] <imagename>" % sys.argv[0])

def main():
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s|%(levelname)s: %(message)s')
    do_federated_node_prerun_checks()
    run_as_user = os.environ["SUDO_USER"]
    assert run_as_user

    #parse any command line objects
    try:
        opts, args = getopt.getopt(sys.argv[1:], "h", ["help",])
    except getopt.GetoptError as err:
        usage()
        sys.exit(2)
    mode = None
    for o, a in opts:
        if o in ("-h", "--help"):
            usage()
            sys.exit()
        else:
            assert False, "Unhandled or unimplemented switch or option"

    #get the imagename to build
    if len(args) != 1:
        usage()
        sys.exit(2)
    
    image_name = args[0]
    
    #does a template exist for this image name (i.e. is specified image name valid?)
    if not os.path.exists("%s/docker/%s" % (USER_HOMEDIR, image_name)):
        logging.error("Invalid image name: '%s'" % image_name)
        sys.exit(1)
    
    logging.info("Building image '%s' ..." % image_name)
    runcmd("sudo docker build -t my_mongodb .")

if __name__ == "__main__":
    main()
