#! /usr/bin/env python3
"""
Counterparty setup script - works under Ubuntu Linux and Windows at the present moment

TODO: On Linux, update to use fpm to package the files in a .deb, .rpm, etc archive, with the depenencies listed.
This should make installation/uninstallation more straight-forward.
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

PYTHON3_VER = None
DEFAULT_CONFIG = "[Default]\nbitcoind-rpc-connect=localhost\nbitcoind-rpc-port=8332\nbitcoind-rpc-user=rpc\nbitcoind-rpc-password=rpcpw1234\nrpc-host=localhost\nrpc-port=4000\nrpc-user=rpc\nrpc-password=xcppw1234"
DEFAULT_CONFIG_TESTNET = "[Default]\nbitcoind-rpc-connect=localhost\nbitcoind-rpc-port=18332\nbitcoind-rpc-user=rpc\nbitcoind-rpc-password=rpcpw1234\nrpc-host=localhost\nrpc-port=14000\nrpc-user=rpc\nrpc-password=xcppw1234\ntestnet=1"
DEFAULT_CONFIG_INSTALLER = "[Default]\nbitcoind-rpc-connect=BITCOIND_RPC_CONNECT\nbitcoind-rpc-port=BITCOIND_RPC_PORT\nbitcoind-rpc-user=BITCOIND_RPC_USER\nbitcoind-rpc-password=BITCOIND_RPC_PASSWORD\nrpc-host=RPC_HOST\nrpc-port=RPC_PORT\nrpc-user=RPC_USER\nrpc-password=RPC_PASSWORD"

DEFAULT_CONFIG_COUNTERWALLETD = "[Default]\nbitcoind-rpc-connect=localhost\nbitcoind-rpc-port=8332\nbitcoind-rpc-user=rpc\nbitcoind-rpc-password=rpcpw1234\ncounterpartyd-rpc-host=localhost\ncounterpartyd-rpc-port=4000\ncounterpartyd-rpc-user=rpc\ncounterpartyd-rpc-password=xcppw1234\nrpc-host=0.0.0.0\nsocketio-host=0.0.0.0\nsocketio-chat-host=0.0.0.0\nredis-enable-apicache=0"
DEFAULT_CONFIG_COUNTERWALLETD_TESTNET = "[Default]\nbitcoind-rpc-connect=localhost\nbitcoind-rpc-port=18332\nbitcoind-rpc-user=rpc\nbitcoind-rpc-password=rpcpw1234\ncounterpartyd-rpc-host=localhost\ncounterpartyd-rpc-port=14000\ncounterpartyd-rpc-user=rpc\ncounterpartyd-rpc-password=xcppw1234\nrpc-host=0.0.0.0\nsocketio-host=0.0.0.0\nsocketio-chat-host=0.0.0.0\nredis-enable-apicache=0\ntestnet=1"
DEFAULT_CONFIG_INSTALLER_COUNTERWALLETD = "[Default]\nbitcoind-rpc-connect=localhost\nbitcoind-rpc-port=8332\nbitcoind-rpc-user=rpc\nbitcoind-rpc-password=rpcpw1234\ncounterpartyd-rpc-host=RPC_HOST\ncounterpartyd-rpc-port=RPC_PORT\ncounterpartyd-rpc-user=RPC_USER\ncounterpartyd-rpc-password=RPC_PASSWORD"

def which(filename):
    """docstring for which"""
    locations = os.environ.get("PATH").split(os.pathsep)
    candidates = []
    for location in locations:
        candidate = os.path.join(location, filename)
        if os.path.isfile(candidate):
            candidates.append(candidate)
    return candidates

def _get_app_cfg_paths(appname, run_as_user):
    import appdirs #installed earlier
    cfg_path = os.path.join(
        appdirs.user_data_dir(appauthor='Counterparty', appname=appname, roaming=True) \
            if os.name == "nt" else ("%s/.config/%s" % (os.path.expanduser("~%s" % run_as_user), appname)), 
        "%s.conf" % appname.replace('-testnet', ''))
    data_dir = os.path.dirname(cfg_path)
    return (data_dir, cfg_path)

def _rmtree(path):
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
            _rmtree(fullpath)
            f=os.rmdir
            rmgeneric(fullpath, f)    

def usage():
    print("SYNTAX: %s [-h] [--with-counterblockd] [--with-testnet] [--for-user=] [setup|build|update]" % sys.argv[0])
    print("* The 'setup' command will setup and install counterpartyd as a source installation (including automated setup of its dependencies)")
    print("* The 'build' command builds an installer package (Windows only, currently)")
    print("* The 'update' command updates the git repo for both counterpartyd, counterpartyd_build, and counterblockd (if --with-counterblockd is specified)")
    print("* 'setup' is chosen by default if neither the 'build', 'update', or 'setup' arguments are specified.")
    print("* If you want to install counterblockd along with counterpartyd, specify the --with-counterblockd option")

def runcmd(command, abort_on_failure=True):
    logging.debug("RUNNING COMMAND: %s" % command)
    ret = os.system(command)
    if abort_on_failure and ret != 0:
        logging.error("Command failed: '%s'" % command)
        sys.exit(1) 

def do_prerun_checks():
    #make sure this is running on a supported OS
    if os.name not in ("nt", "posix"):
        logging.error("Build script only supports Linux or Windows at this time")
        sys.exit(1)
    if os.name == "posix" and platform.dist()[0] != "Ubuntu":
        logging.error("Non-Ubuntu install detected. Only Ubuntu Linux is supported at this time")
        sys.exit(1)
        
    #under *nix, script must be run as root
    if os.name == "posix" and os.geteuid() != 0:
        logging.error("This script must be run as root (use 'sudo' to run)")
        sys.exit(1)
        
    if os.name == "posix" and "SUDO_USER" not in os.environ:
        logging.error("Please use `sudo` to run this script.")
    
    #establish python version
    global PYTHON3_VER
    if os.name == "nt":
        PYTHON3_VER = "3.3"
    elif os.name == "posix" and platform.dist()[0] == "Ubuntu" and platform.linux_distribution()[1] == "12.04":
        #ubuntu 12.04 -- python 3.3 will be installed in install_dependencies, as flask requires it
        PYTHON3_VER = "3.3"
    else:
        allowed_vers = ["3.4", "3.3"]
        for ver in allowed_vers:
            if which("python%s" % ver):
                PYTHON3_VER = ver
                logging.info("Found Python version %s" % PYTHON3_VER)
                break
        else:
            logging.error("Cannot find your Python version in your path. You need one of the following versions: %s"
                % ', '.join(allowed_vers))
            sys.exit(1)

def get_paths(with_counterblockd):
    paths = {}
    paths['sys_python_path'] = os.path.dirname(sys.executable)

    paths['base_path'] = os.path.normpath(os.path.dirname(os.path.realpath(sys.argv[0])))
    #^ the dir of where counterparty source was downloaded to
    logging.debug("base path: '%s'" % paths['base_path'])
    
    #find the location of the virtualenv command and make sure it exists
    if os.name == "posix":
        paths['virtualenv_path'] = "/usr/bin/virtualenv"
        paths['virtualenv_args'] = "--system-site-packages --python=python%s" % PYTHON3_VER
    elif os.name == "nt":
        paths['virtualenv_path'] = os.path.join(paths['sys_python_path'], "Scripts", "virtualenv.exe")
        paths['virtualenv_args'] = "--system-site-packages"
        #^ we use system-site-packages here because we need to be able to import cx_freeze from the sys packages
    
    #compose the rest of the paths...
    paths['dist_path'] = os.path.join(paths['base_path'], "dist")
    logging.debug("dist path: '%s'" % paths['dist_path'])

    paths['env_path'] = os.path.join(paths['base_path'], "env") # home for the virtual environment
    logging.debug("env path: '%s'" % paths['env_path'])

    paths['bin_path'] = os.path.join(paths['base_path'], "bin")
    logging.debug("bin path: '%s'" % paths['bin_path'])
    
    #the pip executiable that we'll be using does not exist yet, but it will, once we've created the virtualenv
    paths['pip_path'] = os.path.join(paths['env_path'], "Scripts" if os.name == "nt" else "bin", "pip.exe" if os.name == "nt" else "pip")
    paths['python_path'] = os.path.join(paths['env_path'], "Scripts" if os.name == "nt" else "bin", "python.exe" if os.name == "nt" else "python3")

    #for now, counterblockd currently uses Python 2.7 due to gevent-socketio's lack of support for Python 3
    #because of this, it needs its own virtual environment
    if with_counterblockd:
        paths['virtualenv_args.counterblockd'] = "--system-site-packages --python=python2.7"
        paths['env_path.counterblockd'] = os.path.join(paths['base_path'], "env.counterblockd") # home for the virtual environment
        paths['pip_path.counterblockd'] = os.path.join(paths['env_path.counterblockd'], "Scripts" if os.name == "nt" else "bin", "pip.exe" if os.name == "nt" else "pip")
        paths['python_path.counterblockd'] = os.path.join(paths['env_path.counterblockd'], "Scripts" if os.name == "nt" else "bin", "python.exe" if os.name == "nt" else "python")
    
    return paths

def checkout(paths, run_as_user, with_counterblockd, is_update):
    #check what our current branch is
    try:
        branch = subprocess.check_output(("cd %s && git rev-parse --abbrev-ref HEAD" % paths['base_path']), shell=True).strip().decode('utf-8')
        assert branch in ("master", "develop") #the two that we support for now
    except:
        raise Exception("Cannot get current get branch. Please make sure you are running setup.py from your counterpartyd_build directory.")
    
    logging.info("Checking out/updating counterpartyd:%s from git..." % branch)
    counterpartyd_path = os.path.join(paths['dist_path'], "counterpartyd")
    if os.path.exists(counterpartyd_path):
        runcmd("cd \"%s\" && git pull origin %s" % (counterpartyd_path, branch))
    else:
        runcmd("git clone -b %s https://github.com/CounterpartyXCP/counterpartyd \"%s\"" % (branch, counterpartyd_path))
    if os.name != 'nt':
        runcmd("chown -R %s \"%s\"" % (run_as_user, counterpartyd_path))
        
    if with_counterblockd:
        counterblockd_path = os.path.join(paths['dist_path'], "counterblockd")
        if os.path.exists(counterblockd_path):
            runcmd("cd \"%s\" && git pull origin %s" % (counterblockd_path, branch))
        else:
            runcmd("git clone -b %s https://github.com/CounterpartyXCP/counterblockd \"%s\"" % (branch, counterblockd_path))
            pass
        if os.name != 'nt':
            runcmd("chown -R %s \"%s\"" % (run_as_user, counterblockd_path))
    
    if is_update: #update mode specified... update ourselves (counterpartyd_build) as well
        runcmd("cd \"%s\" && git pull origin %s" % (paths['base_path'], branch))
    
    sys.path.insert(0, os.path.join(paths['dist_path'], "counterpartyd")) #can now import counterparty modules


def install_dependencies(paths, with_counterblockd, assume_yes):
    if os.name == "posix" and platform.dist()[0] == "Ubuntu":
        ubuntu_release = platform.linux_distribution()[1]
        logging.info("UBUNTU LINUX %s: Installing Required Packages..." % ubuntu_release) 
        runcmd("apt-get -y update")

        if ubuntu_release in ("14.04", "13.10"):
            runcmd("apt-get -y install software-properties-common python-software-properties git-core wget cx-freeze \
            python3 python3-setuptools python3-dev python3-pip build-essential python3-sphinx python-virtualenv libsqlite3-dev python3-apsw python3-zmq")
            
            if with_counterblockd:
                #counterblockd currently uses Python 2.7 due to gevent-socketio's lack of support for Python 3
                runcmd("apt-get -y install python python-dev python-setuptools python-pip python-sphinx python-zmq libzmq3 libzmq3-dev libxml2-dev libxslt-dev zlib1g-dev libimage-exiftool-perl libevent-dev cython")
                if assume_yes:
                    db_locally = 'y'
                else:
                    while True:
                        db_locally = input("counterblockd: Run mongo and redis locally? (y/n): ")
                        if db_locally.lower() not in ('y', 'n'):
                            logger.error("Please enter 'y' or 'n'")
                        else:
                            break
                if db_locally.lower() == 'y':
                    runcmd("apt-get -y install mongodb mongodb-server redis-server")
        elif ubuntu_release == "12.04":
            #12.04 deps. 12.04 doesn't include python3-pip, so we need to use the workaround at http://stackoverflow.com/a/12262143
            runcmd("apt-get -y install software-properties-common python-software-properties git-core wget cx-freeze \
            python3 python3-setuptools python3-dev build-essential python3-sphinx python-virtualenv libsqlite3-dev")

            #install python 3.3 (required for flask)
            runcmd("add-apt-repository -y ppa:fkrull/deadsnakes")
            runcmd("apt-get update; apt-get -y install python3.3 python3.3-dev")
            runcmd("ln -sf /usr/bin/python3.3 /usr/bin/python3")
            
            #now actually run the distribute_setup.py script as pip3 is broken
            runcmd("rm -f /tmp/distribute_setup.py; curl -o /tmp/distribute_setup.py http://python-distribute.org/distribute_setup.py")
            runcmd("python3 /tmp/distribute_setup.py")
            runcmd("rm -f ./distribute-*.tar.gz") #the script above likes to create this file in the local dir
            
            runcmd("easy_install3 pip==1.4.1") #pip1.5 breaks things due to its use of wheel by default
            #for some reason, it installs "pip" to /usr/local/bin, instead of "pip3"
            runcmd("cp -a /usr/local/bin/pip /usr/local/bin/pip3")

            ##ASPW
            #12.04 also has no python3-apsw module as well (unlike 13.10), so we need to do this one manually
            # Ubuntu 12.04 (Precise) ships with sqlite3 version 3.7.9 - the apsw version needs to match that exactly
            runcmd("pip3 install https://github.com/rogerbinns/apsw/zipball/f5bf9e5e7617bc7ff2a5b4e1ea7a978257e08c95#egg=apsw")
            
            ##LIBZMQ
            #12.04 has no python3-zmq module
            runcmd("apt-get -y install libzmq-dev")
            runcmd("pip3 install pyzmq")
            
            #also update virtualenv
            runcmd("pip3 install virtualenv")
            paths['virtualenv_path'] = "/usr/local/bin/virtualenv-3.3" #HACK
        else:
            logging.error("Unsupported Ubuntu version, please use 14.04 LTS, 13.10 or 12.04 LTS")
            sys.exit(1)

        #install sqlite utilities (not technically required, but nice to have)
        runcmd("apt-get -y install sqlite sqlite3 libleveldb-dev")
        
        #now that pip is installed, install necessary deps outside of the virtualenv (e.g. for this script)
        runcmd("pip3 install appdirs==1.2.0")
    elif os.name == 'nt':
        logging.info("WINDOWS: Installing Required Packages...")
        if not os.path.exists(os.path.join(paths['sys_python_path'], "Scripts", "easy_install.exe")):
            #^ ez_setup.py doesn't seem to tolerate being run after it's already been installed... errors out
            #run the ez_setup.py script to download and install easy_install.exe so we can grab virtualenv and more...
            runcmd("pushd %%TEMP%% && %s %s && popd" % (sys.executable,
                os.path.join(paths['dist_path'], "windows", "ez_setup.py")))
        
        #now easy_install is installed, install virtualenv, and pip
        runcmd("%s virtualenv==1.10.1 pip==1.4.1" % (os.path.join(paths['sys_python_path'], "Scripts", "easy_install.exe")))

        #now that pip is installed, install necessary deps outside of the virtualenv (e.g. for this script)
        runcmd("%s install appdirs==1.2.0" % (os.path.join(paths['sys_python_path'], "Scripts", "pip.exe")))

def create_virtualenv(paths, with_counterblockd):
    def create_venv(env_path, pip_path, python_path, virtualenv_args, reqs_filename, delete_if_exists=True):
        if paths['virtualenv_path'] is None or not os.path.exists(paths['virtualenv_path']):
            logging.debug("ERROR: virtualenv missing (%s)" % (paths['virtualenv_path'],))
            sys.exit(1)
        
        if delete_if_exists and os.path.exists(env_path):
            logging.warning("Deleting existing virtualenv...")
            _rmtree(env_path)
        assert not os.path.exists(os.path.join(env_path, 'bin'))
        logging.info("Creating virtualenv at '%s' ..." % env_path)
        runcmd("%s %s %s" % (paths['virtualenv_path'], virtualenv_args, env_path))
        
        #pip should now exist
        if not os.path.exists(pip_path):
            logging.error("pip does not exist at path '%s'" % pip_path)
            sys.exit(1)
            
        #install packages from manifest via pip
        runcmd("%s install -r %s" % (pip_path, os.path.join(paths['dist_path'], reqs_filename)))

    create_venv(paths['env_path'], paths['pip_path'], paths['python_path'], paths['virtualenv_args'],
        os.path.join(paths['dist_path'], "counterpartyd", "pip-requirements.txt")) 
    if with_counterblockd: #as counterblockd uses python 2.x, it needs its own virtualenv
        runcmd("rm -rf %s && mkdir -p %s" % (paths['env_path.counterblockd'], paths['env_path.counterblockd']))
        create_venv(paths['env_path.counterblockd'], paths['pip_path.counterblockd'], paths['python_path.counterblockd'],
            paths['virtualenv_args.counterblockd'],
            os.path.join(paths['dist_path'], "counterblockd", "pip-requirements.txt"), delete_if_exists=False)    

def setup_startup(paths, run_as_user, with_counterblockd, with_testnet, assume_yes):
    if os.name == "posix":
        runcmd("ln -sf %s/run.py /usr/local/bin/counterpartyd" % paths['base_path'])
        if with_counterblockd:
            #make a short script to launch counterblockd
            f = open("/usr/local/bin/counterblockd", 'w')
            f.write("#!/bin/sh\n%s/run.py counterblockd \"$@\"" % paths['base_path'])
            f.close()
            runcmd("chmod +x /usr/local/bin/counterblockd")
    elif os.name == "nt":
        #create a batch script
        batch_contents = "echo off%sREM Launch counterpartyd (source build) under windows%s%s %s %%*" % (
            os.linesep, os.linesep, os.path.join(paths['sys_python_path'], "python.exe"), os.path.join(paths['base_path'], "run.py"))
        f = open("%s" % os.path.join(os.environ['WINDIR'], "counterpartyd.bat"), "w")
        f.write(batch_contents)
        f.close()

    if assume_yes:
        start_choice = 'y'
    else:
        while True:
            start_choice = input("Start counterpartyd automatically on system startup? (y/n): ")
            if start_choice.lower() not in ('y', 'n'):
                logger.error("Please enter 'y' or 'n'")
            else:
                break
    if start_choice.lower() == 'n':
        return
    
    #windows - no automatic startup from the script itself (auto startup is used when installing from installer)
    if os.name == "nt":
        #add a shortcut to run.py to the startup group
        import win32com.client
        import ctypes.wintypes
        CSIDL_PERSONAL=7 # Startup folder
        SHGFP_TYPE_CURRENT= 0 # Want current, not default value
        buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
        ctypes.windll.shell32.SHGetFolderPathW(0, CSIDL_PERSONAL, 0, SHGFP_TYPE_CURRENT, buf)
        logging.debug("Installing startup shortcut(s) to '%s'" % buf.value)
        
        ws = win32com.client.Dispatch("wscript.shell")
        scut = ws.CreateShortcut(os.path.join(buf.value, 'run_counterpartyd.lnk'))
        scut.TargetPath = '"c:/Python32/python.exe"'
        scut.Arguments = os.path.join(paths['base_path'], 'run.py') + ' server'
        scut.Save()
        if with_testnet:
            ws = win32com.client.Dispatch("wscript.shell")
            scut = ws.CreateShortcut(os.path.join(buf.value, 'run_counterpartyd_testnet.lnk' % s))
            scut.TargetPath = '"c:/Python32/python.exe"'
            scut.Arguments = os.path.join(paths['base_path'], 'run.py') \
                + (' --testnet --data-dir="%s" server' % data_dir, _get_app_cfg_paths('counterpartyd-testnet', run_as_user))
            scut.Save()
    else:
        logging.info("Setting up init scripts...")
        assert run_as_user
        user_homedir = os.path.expanduser("~" + run_as_user)
        runcmd("rm -f /etc/init/counterpartyd.conf")
        runcmd("cp -af %s/linux/init/counterpartyd.conf.template /etc/init/counterpartyd.conf" % paths['dist_path'])
        runcmd("sed -ri \"s/\!RUN_AS_USER\!/%s/g\" /etc/init/counterpartyd.conf" % run_as_user)
        runcmd("sed -ri \"s/\!USER_HOMEDIR\!/%s/g\" /etc/init/counterpartyd.conf" % user_homedir.replace('/', '\/'))
        if with_testnet:
            runcmd("rm -f /etc/init/counterpartyd-testnet.conf")
            runcmd("cp -af %s/linux/init/counterpartyd-testnet.conf.template /etc/init/counterpartyd-testnet.conf" % paths['dist_path'])
            runcmd("sed -ri \"s/\!RUN_AS_USER\!/%s/g\" /etc/init/counterpartyd-testnet.conf" % run_as_user)
            runcmd("sed -ri \"s/\!USER_HOMEDIR\!/%s/g\" /etc/init/counterpartyd-testnet.conf" % user_homedir.replace('/', '\/'))
        if with_counterblockd:
            runcmd("rm -f /etc/init/counterblockd.conf")
            runcmd("cp -af %s/linux/init/counterblockd.conf.template /etc/init/counterblockd.conf" % paths['dist_path'])
            runcmd("sed -ri \"s/\!RUN_AS_USER\!/%s/g\" /etc/init/counterblockd.conf" % run_as_user)
            runcmd("sed -ri \"s/\!USER_HOMEDIR\!/%s/g\" /etc/init/counterblockd.conf" % user_homedir.replace('/', '\/'))
            if with_testnet:
                runcmd("rm -f /etc/init/counterblockd-testnet.conf")
                runcmd("cp -af %s/linux/init/counterblockd-testnet.conf.template /etc/init/counterblockd-testnet.conf" % paths['dist_path'])
                runcmd("sed -ri \"s/\!RUN_AS_USER\!/%s/g\" /etc/init/counterblockd-testnet.conf" % run_as_user)
                runcmd("sed -ri \"s/\!USER_HOMEDIR\!/%s/g\" /etc/init/counterblockd-testnet.conf" % user_homedir.replace('/', '\/'))

def create_default_datadir_and_config(paths, run_as_user, with_counterblockd, with_testnet):
    def create_config(appname, default_config):
        data_dir, cfg_path = _get_app_cfg_paths(appname, run_as_user)
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
        
        if not os.path.exists(cfg_path):
            logging.info("Creating new configuration file at: %s" % cfg_path)
            #create a default config file
            cfg = open(cfg_path, 'w')
            cfg.write(default_config)
            cfg.close()
        
            if os.name != "nt": #set permissions on non-windows
                uid = pwd.getpwnam(run_as_user).pw_uid
                gid = grp.getgrnam(run_as_user).gr_gid    
        
                #set directory ownership
                os.chown(data_dir, uid, gid)
        
                #set proper file ownership and mode
                os.chown(cfg_path, uid, gid)
                os.chmod(cfg_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP) #660
            else:
                #on windows, open notepad to the config file to help out
                import win32api
                try:
                    win32api.WinExec('NOTEPAD.exe "%s"' % cfg_path)
                except:
                    pass        
        
            logging.info("NOTE: %s config file has been created at '%s'" % (appname, cfg_path))
        else:
            logging.info("%s config file already exists at: '%s'" % (appname, cfg_path))
    
    create_config('counterpartyd', DEFAULT_CONFIG)
    if with_testnet:
        create_config('counterpartyd-testnet', DEFAULT_CONFIG_TESTNET)
    if with_counterblockd:
        create_config('counterblockd', DEFAULT_CONFIG_COUNTERWALLETD)
        if with_testnet:
            create_config('counterblockd-testnet', DEFAULT_CONFIG_COUNTERWALLETD_TESTNET)

def do_build(paths, with_counterblockd):
    #TODO: finish windows build support for counterblockd
    if os.name != "nt":
        logging.error("Building an installer only supported on Windows at this time.")
        sys.exit(1)
        
    logging.debug("Cleaning any old build dirs...")
    if os.path.exists(os.path.join(paths['bin_path'], "exe.win-amd64-%s" % PYTHON3_VER)):
        shutil.rmtree(os.path.join(paths['bin_path'], "exe.win-amd64-%s" % PYTHON3_VER))
    if os.path.exists(os.path.join(paths['bin_path'], "exe.win-i386-%s" % PYTHON3_VER)):
        shutil.rmtree(os.path.join(paths['bin_path'], "exe.win-i386-%s" % PYTHON3_VER))
    if os.path.exists(os.path.join(paths['bin_path'], "build")):
        shutil.rmtree(os.path.join(paths['bin_path'], "build"))

    #Run cx_freeze to build the counterparty sources into a self-contained executiable
    runcmd("%s \"%s\" build -b \"%s\"" % (
        paths['python_path'], os.path.join(paths['dist_path'], "_cxfreeze_setup.py"), paths['bin_path']))
    #move the build dir to something more predictable so we can build an installer with it
    arch = "amd64" if os.path.exists(os.path.join(paths['bin_path'], "exe.win-amd64-%s" % PYTHON3_VER)) else "i386"
    shutil.move(os.path.join(paths['bin_path'], "exe.win-%s-%s" % (arch, PYTHON3_VER)), os.path.join(paths['bin_path'], "build"))
    
    logging.info("Frozen executiable data created in %s" % os.path.join(paths['bin_path'], "build"))
    
    #Add a default config to the build
    cfg = open(os.path.join(os.path.join(paths['bin_path'], "build"), "counterpartyd.conf.default"), 'w')
    cfg.write(DEFAULT_CONFIG_INSTALLER)
    cfg.close()
    if with_counterblockd:
        cfg = open(os.path.join(os.path.join(paths['bin_path'], "build"), "counterblockd.conf.default"), 'w')
        cfg.write(COUNTERWALLETD_DEFAULT_CONFIG_INSTALLER)
        cfg.close()
    
    #find the location of makensis.exe (freaking windows...)
    if 'PROGRAMFILES(X86)' in os.environ:
        pf_path = os.environ['PROGRAMFILES(X86)'].replace("Program Files (x86)", "Progra~2")
    else:
        pf_path = os.environ['PROGRAMFILES'].replace("Program Files", "Progra~1")
    
    make_nsis_path = os.path.normpath(os.path.join(pf_path, "NSIS", "makensis.exe"))
    if not os.path.exists(make_nsis_path):
        logging.error("Error finding makensis.exe at path '%s'. Did you install NSIS?" % make_nsis_path)
        sys.exit(1)
    runcmd(r'%s %s%s' % (make_nsis_path, "/DIS_64BIT " if arch == "amd64" else '',
        os.path.normpath(os.path.join(paths['dist_path'], "windows", "installer.nsi"))))
    
    #move created .msi file to the bin dir
    from lib import config #counter party
    installer_dest = os.path.join(paths['bin_path'], "counterpartyd-v%s-%s_install.exe" % (config.CLIENT_VERSION, arch))
    if os.path.exists(installer_dest):
        os.remove(installer_dest)
    shutil.move(os.path.join(paths['dist_path'], "windows", "counterpartyd_install.exe"), installer_dest)
    logging.info("FINAL installer created as %s" % installer_dest)

def main():
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s|%(levelname)s: %(message)s')
    
    do_prerun_checks()

    run_as_user = None
    if os.name != "nt":
        run_as_user = os.environ["SUDO_USER"] #default value, can be overridden via the --for-user= switch
        assert run_as_user

    #parse any command line objects
    command = None
    with_counterblockd = False
    with_testnet = False
    assume_yes = False #headless operation
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hby", ["build", "help", "with-counterblockd", "with-testnet", "for-user="])
    except getopt.GetoptError as err:
        usage()
        sys.exit(2)
    mode = None
    for o, a in opts:
        if o in ("--with-counterblockd",):
            with_counterblockd = True
        elif o in ("--with-testnet",):
            with_testnet = True
        elif o in ("--for-user",):
            assert os.name != "nt" #not supported
            #allow overriding run_as_user
            try: #make sure user exists
                assert(a)
                pwd.getpwnam(a)
            except:
                logging.error(("User '%s' does not appear to exist" % a) if a else 'You must specify a username')
                sys.exit(2)
            else:
                run_as_user = a
        elif o in ("-h", "--help"):
            usage()
            sys.exit()
        elif o in ("-y"):
            assume_yes = True
        else:
            assert False, "Unhandled or unimplemented switch or option"
            
    if len(args) not in [0, 1]:
        usage()
        sys.exit(2)
        
    if args and args[0] == "build":
        command = "build"
    elif args and args[0] == "update":
        command = "update"
    else: #either setup specified explicitly, or no command specified
        command = "setup"
    assert command in ["build", "update", "setup"]

    paths = get_paths(with_counterblockd)

    if command == "build": #build counterpartyd installer (currently windows only)
        logging.info("Building Counterparty...")
        checkout(paths, run_as_user, with_counterblockd, command == "update")
        install_dependencies(paths, with_counterblockd, assume_yes)
        create_virtualenv(paths, with_counterblockd)
        do_build(paths, with_counterblockd)
    elif command == "update": #auto update from git
        logging.info("Updating relevant Counterparty repos")
        checkout(paths, run_as_user, with_counterblockd, command == "update")
    else: #setup mode
        assert command == "setup"
        logging.info("Installing Counterparty from source%s..." % (
            (" for user '%s'" % run_as_user) if os.name != "nt" else '',))
        checkout(paths, run_as_user, with_counterblockd, command == "update")
        install_dependencies(paths, with_counterblockd, assume_yes)
        create_virtualenv(paths, with_counterblockd)
        setup_startup(paths, run_as_user, with_counterblockd, with_testnet, assume_yes)
    
    logging.info("%s DONE. (It's time to kick ass, and chew bubblegum... and I'm all outta gum.)" % ("BUILD" if command == "build" else "SETUP"))
    if command != "build":
        create_default_datadir_and_config(paths, run_as_user, with_counterblockd, with_testnet)


if __name__ == "__main__":
    main()
