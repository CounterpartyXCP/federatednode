#! /usr/bin/env python3
"""
Counterparty setup script - works under Ubuntu Linux and Windows at the present moment
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
import stat

try: #ignore import errors on windows
    import pwd
    import grp
except ImportError:
    pass

PYTHON_VER = None
DEFAULT_CONFIG = "[Default]\nbitcoind-rpc-connect=localhost\nbitcoind-rpc-port=8332\nbitcoind-rpc-user=rpc\nbitcoind-rpc-password=rpcpw1234\nrpc-host=localhost\nrpc-port=\nrpc-user=\nrpc-password=xcppw1234"
DEFAULT_CONFIG_INSTALLER = "[Default]\nbitcoind-rpc-connect=BITCOIND_RPC_CONNECT\nbitcoind-rpc-port=BITCOIND_RPC_PORT\nbitcoind-rpc-user=BITCOIND_RPC_USER\nbitcoind-rpc-password=BITCOIND_RPC_PASSWORD\nrpc-host=RPC_HOST\nrpc-port=RPC_PORT\nrpc-user=RPC_USER\nrpc-password=RPC_PASSWORD"

def which(filename):
    """docstring for which"""
    locations = os.environ.get("PATH").split(os.pathsep)
    candidates = []
    for location in locations:
        candidate = os.path.join(location, filename)
        if os.path.isfile(candidate):
            candidates.append(candidate)
    return candidates

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
    print("SYNTAX: %s [-h] [--build]" % sys.argv[0])

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
    global PYTHON_VER
    if os.name == "nt":
        PYTHON_VER = "3.3"
    else:
        for ver in ["3.3", "3.2", "3.1"]:
            if which("python%s" % ver):
                PYTHON_VER = ver
                logging.info("Found Python version %s" % PYTHON_VER)
                break
        else:
            logging.error("Cannot find your Python version in your path")
            sys.exit(1)

def get_paths(is_build):
    paths = {}
    paths['sys_python_path'] = os.path.dirname(sys.executable)

    paths['base_path'] = os.path.normpath(os.path.dirname(os.path.realpath(sys.argv[0])))
    #^ the dir of where counterparty source was downloaded to
    logging.debug("base path: '%s'" % paths['base_path'])
    
    #find the location of the virtualenv command and make sure it exists
    if os.name == "posix":
        paths['virtualenv_path'] = "/usr/bin/virtualenv"
        paths['virtualenv_args'] = "--python=python%s" % PYTHON_VER
    elif os.name == "nt":
        paths['virtualenv_path'] = os.path.join(paths['sys_python_path'], "Scripts", "virtualenv.exe")
        paths['virtualenv_args'] = "--system-site-packages" if is_build else ""
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
    
    return paths

def checkout_counterpartyd(paths, run_as_user):
    logging.info("Checking out/updating counterpartyd from git...")
    counterpartyd_path = os.path.join(paths['dist_path'], "counterpartyd")
    if os.path.exists(counterpartyd_path):
        runcmd("cd \"%s\" && git pull origin master" % counterpartyd_path)
    else:
        runcmd("git clone https://github.com/PhantomPhreak/counterpartyd \"%s\"" % counterpartyd_path)
    
    if os.name != 'nt':
        runcmd("chown -R %s \"%s\"" % (run_as_user, counterpartyd_path))
    sys.path.insert(0, os.path.join(paths['dist_path'], "counterpartyd")) #can now import counterparty modules

def install_dependencies(paths):
    if os.name == "posix" and platform.dist()[0] == "Ubuntu":
        ubuntu_release = platform.linux_distribution()[1]
        logging.info("UBUNTU LINUX %s: Installing Required Packages..." % ubuntu_release) 
        runcmd("sudo apt-get -y update")
        
        #13.10 deps
        if ubuntu_release == "13.10":
            runcmd("sudo apt-get -y install software-properties-common python-software-properties git-core wget cx-freeze \
            python3 python3-setuptools python3-dev python3-pip build-essential python3-sphinx python-virtualenv")
        elif ubuntu_release == "12.04":
            #12.04 deps. 12.04 doesn't include python3-pip, so we need to use the workaround at http://stackoverflow.com/a/12262143
            runcmd("sudo apt-get -y install software-properties-common python-software-properties git-core wget cx-freeze \
            python3 python3-setuptools python3-dev build-essential python3-sphinx python-virtualenv")
            if not os.path.exists("/usr/local/bin/pip3"):
                runcmd("sudo easy_install3 pip==1.4.1") #pip1.5 breaks things due to its use of wheel by default
                #for some reason, it installs "pip" to /usr/local/bin, instead of "pip3"
                runcmd("sudo mv /usr/local/bin/pip /usr/local/bin/pip3")
        else:
            logging.error("Unsupported Ubuntu version, please use 13.10 or 12.04 LTS")
            sys.exit(1)

        #install sqlite utilities (not technically required as python's sqlite3 module is self-contained, but nice to have)
        runcmd("sudo apt-get -y install sqlite sqlite3 libsqlite3-dev libleveldb-dev")
        
        #now that pip is installed, install necessary deps outside of the virtualenv (e.g. for this script)
        runcmd("sudo pip3 install appdirs==1.2.0")
    elif os.name == 'nt':
        logging.info("WINDOWS: Installing Required Packages...")
        if not os.path.exists(os.path.join(paths['sys_python_path'], "Scripts", "easy_install.exe")):
            #^ ez_setup.py doesn't seem to tolerate being run after it's already been installed... errors out
            #run the ez_setup.py script to download and install easy_install.exe so we can grab virtualenv and more...
            runcmd("pushd %%TEMP%% && %s %s && popd" % (sys.executable,
                os.path.join(paths['dist_path'], "windows", "ez_setup.py")))
        
        #now easy_install is installed, install virtualenv, and sphinx for doc building
        runcmd("%s virtualenv==1.10.1 pip==1.4.1 sphinx==1.2" % (os.path.join(paths['sys_python_path'], "Scripts", "easy_install.exe")))
        
        #now that pip is installed, install necessary deps outside of the virtualenv (e.g. for this script)
        runcmd("%s install appdirs==1.2.0" % (os.path.join(paths['sys_python_path'], "Scripts", "pip.exe")))

def create_virtualenv(paths):
    if paths['virtualenv_path'] is None or not os.path.exists(paths['virtualenv_path']):
        logging.debug("ERROR: virtualenv missing (%s)" % (paths['virtualenv_path'],))
        sys.exit(1)
    
    if os.path.exists(paths['env_path']):
        logging.warning("Deleting existing virtualenv...")
        _rmtree(paths['env_path'])
    logging.info("Creating virtualenv at '%s' ..." % paths['env_path'])
    runcmd("%s %s %s" % (paths['virtualenv_path'], paths['virtualenv_args'], paths['env_path']))
    
    #pip should now exist
    if not os.path.exists(paths['pip_path']):
        logging.error("pip does not exist at path '%s'" % paths['pip_path'])
        sys.exit(1)
    
    #install packages from manifest via pip
    runcmd("%s install -r %s" % (paths['pip_path'], os.path.join(paths['dist_path'], "reqs.txt")))

def setup_startup(paths, run_as_user):
    if os.name == "posix":
        runcmd("sudo ln -sf %s/run.py /usr/local/bin/counterpartyd" % paths['base_path'])

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
        logging.debug("Installing startup shortcut to '%s'" % buf.value)
        
        ws = win32com.client.Dispatch("wscript.shell")
        scut = ws.CreateShortcut(os.path.join(buf.value, 'run_counterpartyd.lnk'))
        scut.TargetPath = '"c:/Python33/python.exe"'
        scut.Arguments = os.path.join(paths['base_path'], 'run.py')
        scut.Save()        
    else:
        logging.info("Setting up init scripts...")
        assert run_as_user
        runcmd("sudo cp -a %s/linux/init/counterpartyd.conf.template /etc/init/counterpartyd.conf" % paths['dist_path'])
        runcmd("sudo sed -r -i -e \"s/!RUN_AS_USER!/%s/g\" /etc/init/counterpartyd.conf" % run_as_user)

def create_default_datadir_and_config(paths, run_as_user):
    import appdirs #installed earlier
    cfg_path = os.path.join(
        appdirs.user_data_dir(appauthor='Counterparty', appname='counterpartyd', roaming=True) \
            if os.name == "nt" else ("%s/.config/counterpartyd" % os.path.expanduser("~%s" % run_as_user)), 
        "counterpartyd.conf")
    data_dir = os.path.dirname(cfg_path)
    
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
    
    if not os.path.exists(cfg_path):
        logging.info("Creating new configuration file at: %s" % cfg_path)
        #create a default config file
        cfg = open(cfg_path, 'w')
        cfg.write(DEFAULT_CONFIG)
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
    
        logging.info("NEXT STEP: Edit the config file we created at '%s', according to the documentation" % cfg_path)
    else:
        logging.info("Config file already exists at: %s" % cfg_path)

def do_build(paths):
    if os.name != "nt":
        logging.error("Building an installer only supported on Windows at this time.")
        sys.exit(1)

    logging.debug("Cleaning any old build dirs...")
    if os.path.exists(os.path.join(paths['bin_path'], "exe.win-amd64-%s" % PYTHON_VER)):
        shutil.rmtree(os.path.join(paths['bin_path'], "exe.win-amd64-%s" % PYTHON_VER))
    if os.path.exists(os.path.join(paths['bin_path'], "exe.win-i386-%s" % PYTHON_VER)):
        shutil.rmtree(os.path.join(paths['bin_path'], "exe.win-i386-%s" % PYTHON_VER))
    if os.path.exists(os.path.join(paths['bin_path'], "build")):
        shutil.rmtree(os.path.join(paths['bin_path'], "build"))

    #Run cx_freeze to build the counterparty sources into a self-contained executiable
    runcmd("%s \"%s\" build -b \"%s\"" % (
        paths['python_path'], os.path.join(paths['dist_path'], "_cxfreeze_setup.py"), paths['bin_path']))
    #move the build dir to something more predictable so we can build an installer with it
    arch = "amd64" if os.path.exists(os.path.join(paths['bin_path'], "exe.win-amd64-%s" % PYTHON_VER)) else "i386"
    shutil.move(os.path.join(paths['bin_path'], "exe.win-%s-%s" % (arch, PYTHON_VER)), os.path.join(paths['bin_path'], "build"))
    
    logging.info("Frozen executiable data created in %s" % os.path.join(paths['bin_path'], "build"))
    
    #Add a default config to the build
    cfg = open(os.path.join(os.path.join(paths['bin_path'], "build"), "counterpartyd.conf.default"), 'w')
    cfg.write(DEFAULT_CONFIG_INSTALLER)
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
    installer_dest = os.path.join(paths['bin_path'], "counterpartyd-v%s-%s_install.exe" % (config.VERSION, arch))
    if os.path.exists(installer_dest):
        os.remove(installer_dest)
    shutil.move(os.path.join(paths['dist_path'], "windows", "counterpartyd_install.exe"), installer_dest)
    logging.info("FINAL installer created as %s" % installer_dest)

def main():
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s|%(levelname)s: %(message)s')
    
    do_prerun_checks()

    run_as_user = None
    if os.name != "nt":
        run_as_user = os.environ["SUDO_USER"]
        assert run_as_user

    #parse any command line objects
    is_build = False
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hb", ["build", "help"])
    except getopt.GetoptError as err:
        usage()
        sys.exit(2)
    mode = None
    for o, a in opts:
        if o in ("-b", "--build"):
            is_build = True
        elif o in ("-h", "--help"):
            usage()
            sys.exit()
        else:
            assert False, "Unhandled or unimplemented switch or option"

    paths = get_paths(is_build)

    if is_build:
        logging.info("Building Counterparty...")
        checkout_counterpartyd(paths, run_as_user)
        install_dependencies(paths)
        create_virtualenv(paths)
        do_build(paths)
    else: #install mode
        logging.info("Installing Counterparty from source%s..." % (
            (" for user '%s'" % run_as_user) if os.name != "nt" else '',))
        checkout_counterpartyd(paths, run_as_user)
        install_dependencies(paths)
        create_virtualenv(paths)
        setup_startup(paths, run_as_user)
    
    logging.info("%s DONE. (It's time to kick ass, and chew bubblegum... and I'm all outta gum.)" % ("BUILD" if is_build else "SETUP"))
    if not is_build:
        create_default_datadir_and_config(paths, run_as_user)


if __name__ == "__main__":
    main()
