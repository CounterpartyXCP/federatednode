import os
import sys
import re
import logging
import urllib
import tarfile
import shutil
import random
import platform
import string
import subprocess

__all__ = ['pass_generator', 'runcmd', 'do_federated_node_prerun_checks', 'modify_config', 'modify_cp_config', 'ask_question',
    'git_repo_clone', 'config_runit_for_service', 'config_runit_disable_manual_control', 'which', 'rmtree',
    'fetch_counterpartyd_bootstrap_db']

def pass_generator(size=14, chars=string.ascii_uppercase + string.ascii_lowercase + string.digits):
    return ''.join(random.choice(chars) for x in range(size))

def runcmd(command, abort_on_failure=True):
    logging.debug("RUNNING COMMAND: %s" % command)
    ret = os.system(command)
    if abort_on_failure and ret != 0:
        logging.error("Command failed: '%s'" % command)
        sys.exit(1) 

def get_python_version():
    python3_ver = None
    allowed_vers = ["3.4", "3.3"]
    for ver in allowed_vers:
        if which("python%s" % ver):
            python3_ver = ver
            logging.info("Found Python version %s" % PYTHON3_VER)
            break
    return python3_ver
                
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

def modify_cp_config(param_re, content_to_add, replace_if_exists=True, config='counterpartyd', net='both', for_user='xcp'):
    assert config in ('counterpartyd', 'counterblockd', 'both')
    assert net in ('mainnet', 'testnet', 'both')
    cfg_filenames = []
    if config in ('counterpartyd', 'both'):
        if net in ('mainnet', 'both'):
            cfg_filenames.append(os.path.join(os.path.expanduser('~'+for_user), ".config", "counterpartyd", "counterpartyd.conf"))
        if net in ('testnet', 'both'):
            cfg_filenames.append(os.path.join(os.path.expanduser('~'+for_user), ".config", "counterpartyd-testnet", "counterpartyd.conf"))
    if config in ('counterblockd', 'both'):
        if net in ('mainnet', 'both'):
            cfg_filenames.append(os.path.join(os.path.expanduser('~'+for_user), ".config", "counterblockd", "counterblockd.conf"))
        if net in ('testnet', 'both'):
            cfg_filenames.append(os.path.join(os.path.expanduser('~'+for_user), ".config", "counterblockd-testnet", "counterblockd.conf"))
        
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
        
def git_repo_clone(repo_name, repo_url, repo_dest_dir, branch="AUTO", for_user="xcp", hash=None):
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
            
    if os.name != 'nt':
        runcmd("cd %s && git config core.sharedRepository group && find %s -type d -print0 | xargs -0 chmod g+s" % (
            repo_dest_dir, repo_dest_dir)) #to allow for group git actions 
        runcmd("chown -R %s:%s %s" % (for_user, for_user, repo_dest_dir))
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

def which(filename):
    """docstring for which"""
    locations = os.environ.get("PATH").split(os.pathsep)
    candidates = []
    for location in locations:
        candidate = os.path.join(location, filename)
        if os.path.isfile(candidate):
            candidates.append(candidate)
    return candidates

def rmtree(path):
    """We use this function instead of the built-in shutil.rmtree because it unsets the windoze read-only/archive bit
    before trying a delete (and if we don't do this, we can have problems)"""
    
    if os.name != 'nt':
        return shutil.rmtree(path) #this works fine on non-windows

    #this code only for windows - DO NOT USE THIS CODE ON NON-WINDOWS
    def rmgeneric(path, __func__):
        import win32api, win32con
        win32api.SetFileAttributes(path, win32con.FILE_ATTRIBUTE_NORMAL)
        
        try:
            __func__(path)
            #print 'Removed ', path
        except OSError as err:
            logging.error("Error removing %(path)s, %(error)s" % {'path' : path, 'error': err })

    if not os.path.isdir(path):
        return
    files=os.listdir(path)
    for x in files:
        fullpath=os.path.join(path, x)
        if os.path.isfile(fullpath):
            f=os.remove
            rmgeneric(fullpath, f)
        elif os.path.isdir(fullpath):
            rmtree(fullpath)
            f=os.rmdir
            rmgeneric(fullpath, f)    

def fetch_counterpartyd_bootstrap_db(data_dir, testnet=False, chown_user=None):
    """download bootstrap data for counterpartyd"""
    from progressbar import Percentage, Bar, RotatingMarker, ETA, FileTransferSpeed, ProgressBar

    widgets = ['Bootstrap: ', Percentage(), ' ', Bar(marker=RotatingMarker()), ' ', ETA(), ' ', FileTransferSpeed()]
    pbar = ProgressBar(widgets=widgets)

    def dl_progress(count, blockSize, totalSize):
        if pbar.maxval is None:
            pbar.maxval = totalSize
            pbar.start()
        pbar.update(min(count * blockSize, totalSize))

    bootstrap_url = "http://counterparty-bootstrap.s3.amazonaws.com/counterpartyd%s-db.latest.tar.gz" % ('-testnet' if testnet else '')
    appname = "counterpartyd%s" % ('-testnet' if testnet else '',)
    logging.info("Downloading %s DB bootstrap data from %s ..." % (appname, bootstrap_url))
    bootstrap_filename, headers = urllib.request.urlretrieve(bootstrap_url, reporthook=dl_progress)
    pbar.finish()
    logging.info("%s DB bootstrap data downloaded to %s ..." % (appname, bootstrap_filename))
    tfile = tarfile.open(bootstrap_filename, 'r:gz')
    logging.info("Extracting %s DB bootstrap data to %s ..." % (appname, data_dir))
    tfile.extractall(path=data_dir)
    try:
        os.remove(bootstrap_filename)
    except:
        pass #windows errors out on this
    if chown_user:
        runcmd("chown -R %s %s" % (chown_user, data_dir))
