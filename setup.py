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
import subprocess
import stat

try: #ignore import errors on windows
    import pwd
    import grp
except ImportError:
    pass

PYTHON3_VER = None
DEFAULT_CONFIG = "[Default]\nbitcoind-rpc-connect=localhost\nbitcoind-rpc-port=8332\nbitcoind-rpc-user=rpc\nbitcoind-rpc-password=rpcpw1234\nrpc-host=localhost\nrpc-user=rpcuser\nrpc-password=xcppw1234"
DEFAULT_CONFIG_INSTALLER = "[Default]\nbitcoind-rpc-connect=BITCOIND_RPC_CONNECT\nbitcoind-rpc-port=BITCOIND_RPC_PORT\nbitcoind-rpc-user=BITCOIND_RPC_USER\nbitcoind-rpc-password=BITCOIND_RPC_PASSWORD\nrpc-host=RPC_HOST\nrpc-port=RPC_PORT\nrpc-user=RPC_USER\nrpc-password=RPC_PASSWORD"

DEFAULT_CONFIG_COUNTERWALLETD = "[Default]\nbitcoind-rpc-connect=localhost\nbitcoind-rpc-port=8332\nbitcoind-rpc-user=rpc\nbitcoind-rpc-password=rpcpw1234\ncounterpartyd-rpc-host=localhost\ncounterpartyd-rpc-port=\ncounterpartyd-rpc-user=\ncounterpartyd-rpc-password=xcppw1234"
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
    print("SYNTAX: %s [-h] [--build] [--with-counterwalletd]" % sys.argv[0])

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
        PYTHON3_VER = "3.2"
    else:
        for ver in ["3.3", "3.2", "3.1"]:
            if which("python%s" % ver):
                PYTHON3_VER = ver
                logging.info("Found Python version %s" % PYTHON3_VER)
                break
        else:
            logging.error("Cannot find your Python version in your path")
            sys.exit(1)

def get_paths(is_build, with_counterwalletd):
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

    #for now, counterwalletd currently uses Python 2.7 due to gevent-socketio's lack of support for Python 3
    #because of this, it needs its own virtual environment
    if with_counterwalletd:
        paths['virtualenv_args.cwalletd'] = "--system-site-packages --python=python2.7"
        paths['env_path.cwalletd'] = os.path.join(paths['base_path'], "env.cwalletd") # home for the virtual environment
        paths['pip_path.cwalletd'] = os.path.join(paths['env_path.cwalletd'], "Scripts" if os.name == "nt" else "bin", "pip.exe" if os.name == "nt" else "pip")
        paths['python_path.cwalletd'] = os.path.join(paths['env_path.cwalletd'], "Scripts" if os.name == "nt" else "bin", "python.exe" if os.name == "nt" else "python")
    
    return paths

def checkout(paths, run_as_user, with_counterwalletd):
    #check what our current branch is
    try:
        branch = subprocess.check_output("git rev-parse --abbrev-ref HEAD".split(' ')).strip().decode('utf-8')
        assert branch in ("master", "develop") 
    except:
        raise Exception("Cannot get current get branch. Please make sure you are running setup.py from your counterpartyd_build directory.")
    
    logging.info("Checking out/updating counterpartyd:%s from git..." % branch)
    counterpartyd_path = os.path.join(paths['dist_path'], "counterpartyd")
    if os.path.exists(counterpartyd_path):
        runcmd("cd \"%s\" && git pull origin %s" % (counterpartyd_path, branch))
    else:
        runcmd("git clone -b %s https://github.com/PhantomPhreak/counterpartyd \"%s\"" % (branch, counterpartyd_path))
        
    if with_counterwalletd:
        counterwalletd_path = os.path.join(paths['dist_path'], "counterwalletd")
        if os.path.exists(counterwalletd_path):
            runcmd("cd \"%s\" && git pull origin %s" % (counterwalletd_path, branch))
        else:
            #TODO: check out counterwalletd under dist
            #runcmd("git clone https://github.com/PhantomPhreak/counterpartyd \"%s\"" % counterwalletd_path)
            pass
    
    if os.name != 'nt':
        runcmd("chown -R %s \"%s\"" % (run_as_user, counterpartyd_path))
    sys.path.insert(0, os.path.join(paths['dist_path'], "counterpartyd")) #can now import counterparty modules

def install_dependencies(paths, with_counterwalletd):
    if os.name == "posix" and platform.dist()[0] == "Ubuntu":
        ubuntu_release = platform.linux_distribution()[1]
        logging.info("UBUNTU LINUX %s: Installing Required Packages..." % ubuntu_release) 
        runcmd("sudo apt-get -y update")

        if with_counterwalletd and ubuntu_release != "13.10":
            logging.error("Only Ubuntu 13.10 supported for counterwalletd install.")
        
        #13.10 deps
        if ubuntu_release == "13.10":
            runcmd("sudo apt-get -y install software-properties-common python-software-properties git-core wget cx-freeze \
            python3 python3-setuptools python3-dev python3-pip build-essential python3-sphinx python-virtualenv python3-apsw python3-zmq")
            
            if with_counterwalletd:
                #counterwalletd currently uses Python 2.7 due to gevent-socketio's lack of support for Python 3
                runcmd("sudo apt-get -y install python python-dev python-setuptools python-pip python-sphinx python-zmq libzmq3 libzmq3-dev")
                #delete the environment dir now, since we may need to install cube and we skip deleteting it 
                # when making the virtualenv
                runcmd("sudo rm -rf %s && sudo mkdir -p %s" % (paths['env_path.cwalletd'], paths['env_path.cwalletd']))
                while True:
                    db_locally = input("counterwalletd: Run mongo, redis and cube locally? (y/n): ")
                    if db_locally.lower() not in ('y', 'n'):
                        logger.error("Please enter 'y' or 'n'")
                    else:
                        break
                if db_locally.lower() == 'y':
                    runcmd("sudo apt-get -y install npm mongodb mongodb-server redis-server")
                    runcmd("sudo ln -sf /usr/bin/nodejs /usr/bin/node")
                    runcmd("cd %s && sudo npm install cube@0.2.12" % (paths['env_path.cwalletd'],))
                    #runcmd("cd %s && sudo npm install npm" % paths['env_path']) #install updated NPM into the dir
                    #runcmd("cd %s && sudo %s install cube@0.2.12" % (paths['env_path'],
                    #    os.path.join(paths['env_path'], "node_modules", "npm", "bin", "npm")))
                    
        elif ubuntu_release == "12.04":
            #12.04 deps. 12.04 doesn't include python3-pip, so we need to use the workaround at http://stackoverflow.com/a/12262143
            runcmd("sudo apt-get -y install software-properties-common python-software-properties git-core wget cx-freeze \
            python3 python3-setuptools python3-dev build-essential python3-sphinx python-virtualenv")
            if not os.path.exists("/usr/local/bin/pip3"):
                runcmd("sudo easy_install3 pip==1.4.1") #pip1.5 breaks things due to its use of wheel by default
                #for some reason, it installs "pip" to /usr/local/bin, instead of "pip3"
                runcmd("sudo mv /usr/local/bin/pip /usr/local/bin/pip3")
            
            ##ASPW
            #12.04 also has no python3-apsw module as well (unlike 13.10), so we need to do this one manually
            # Ubuntu 12.04 (Precise) ships with sqlite3 version 3.7.9 - the apsw version needs to match that exactly
            runcmd("sudo pip3 install https://github.com/rogerbinns/apsw/zipball/f5bf9e5e7617bc7ff2a5b4e1ea7a978257e08c95#egg=apsw")
            
            ##LIBZMQ
            #12.04 has no python3-zmq module
            runcmd("sudo apt-get -y install libzmq-dev")
            runcmd("sudo easy_install3 pyzmq")
        else:
            logging.error("Unsupported Ubuntu version, please use 13.10 or 12.04 LTS")
            sys.exit(1)

        #install sqlite utilities (not technically required, but nice to have)
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
        
        #now easy_install is installed, install virtualenv, and pip
        runcmd("%s virtualenv==1.10.1 pip==1.4.1" % (os.path.join(paths['sys_python_path'], "Scripts", "easy_install.exe")))

        #now that pip is installed, install necessary deps outside of the virtualenv (e.g. for this script)
        runcmd("%s install appdirs==1.2.0" % (os.path.join(paths['sys_python_path'], "Scripts", "pip.exe")))

def create_virtualenv(paths, with_counterwalletd):
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

    create_venv(paths['env_path'], paths['pip_path'], paths['python_path'], paths['virtualenv_args'], 'reqs.txt')    
    if with_counterwalletd: #as counterwalletd uses python 2.x, it needs its own virtualenv
        #also, since
        create_venv(paths['env_path.cwalletd'], paths['pip_path.cwalletd'], paths['python_path.cwalletd'],
            paths['virtualenv_args.cwalletd'], 'reqs.counterwalletd.txt', delete_if_exists=False)    

def setup_startup(paths, run_as_user, with_counterwalletd):
    if os.name == "posix":
        runcmd("sudo ln -sf %s/run.py /usr/local/bin/counterpartyd" % paths['base_path'])
        if with_counterwalletd:
            #make a short script to launch counterwallet
            runcmd('sudo echo -e "#!/bin/sh\\n%s/run.py counterwalletd" > /usr/local/bin/counterwalletd' % paths['base_path'])
            runcmd("sudo chmod +x /usr/local/bin/counterwalletd")
    elif os.name == "nt":
        #create a batch script
        batch_contents = "echo off%sREM Launch counterpartyd (source build) under windows%s%s %s %%*" % (
            os.linesep, os.linesep, os.path.join(paths['sys_python_path'], "python.exe"), os.path.join(paths['base_path'], "run.py"))
        f = open("%s" % os.path.join(os.environ['WINDIR'], "counterpartyd.bat"), "w")
        f.write(batch_contents)
        f.close()

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
        scut.TargetPath = '"c:/Python32/python.exe"'
        scut.Arguments = os.path.join(paths['base_path'], 'run.py') + ' server'
        scut.Save()        
    else:
        logging.info("Setting up init scripts...")
        assert run_as_user
        runcmd("sudo cp -a %s/linux/init/counterpartyd.conf.template /etc/init/counterpartyd.conf" % paths['dist_path'])
        runcmd("sudo sed -r -i -e \"s/!RUN_AS_USER!/%s/g\" /etc/init/counterpartyd.conf" % run_as_user)
        if with_counterwalletd:
            runcmd("sudo cp -a %s/linux/init/cube-collector.conf.template /etc/init/cube-collector.conf" % paths['dist_path'])
            runcmd("sudo sed -r -i -e \"s/!RUN_AS_USER!/%s/g\" /etc/init/cube-collector.conf" % run_as_user)
            runcmd("sudo sed -r -i -e \"s/!CUBE_COLLECTOR_PATH!/%s/g\" /etc/init/cube-collector.conf" % (
                os.path.join(paths['env_path.cwalletd'], 'node_modules', 'cube', 'bin', 'collector.js').replace('/', '\\/')))
            runcmd("sudo cp -a %s/linux/init/cube-evaluator.conf.template /etc/init/cube-evaluator.conf" % paths['dist_path'])
            runcmd("sudo sed -r -i -e \"s/!RUN_AS_USER!/%s/g\" /etc/init/cube-evaluator.conf" % run_as_user)
            runcmd("sudo sed -r -i -e \"s/!CUBE_EVALUATOR_PATH!/%s/g\" /etc/init/cube-evaluator.conf" % ( 
                os.path.join(paths['env_path.cwalletd'], 'node_modules', 'cube', 'bin', 'evaluator.js').replace('/', '\\/') ))

def create_default_datadir_and_config(paths, run_as_user, with_counterwalletd):
    def create_config(appname, default_config):
        import appdirs #installed earlier
        cfg_path = os.path.join(
            appdirs.user_data_dir(appauthor='Counterparty', appname=appname, roaming=True) \
                if os.name == "nt" else ("%s/.config/%s" % (os.path.expanduser("~%s" % run_as_user), appname)), 
            "%s.conf" % appname)
        data_dir = os.path.dirname(cfg_path)
        
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
        
            logging.info("NEXT STEP: Edit the %s config file we created at '%s', according to the documentation" % (appname, cfg_path))
        else:
            logging.info("%s config file already exists at: %s" % (appname, cfg_path))
    
    create_config('counterpartyd', DEFAULT_CONFIG)
    if with_counterwalletd:
        create_config('counterwalletd', DEFAULT_CONFIG_COUNTERWALLETD)

def do_build(paths, with_counterwalletd):
    #TODO: finish windows build support for counterwalletd
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
    if with_counterwalletd:
        cfg = open(os.path.join(os.path.join(paths['bin_path'], "build"), "counterwalletd.conf.default"), 'w')
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
    with_counterwalletd = False
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hb", ["build", "help", "with-counterwalletd"])
    except getopt.GetoptError as err:
        usage()
        sys.exit(2)
    mode = None
    for o, a in opts:
        if o in ("-b", "--build"):
            is_build = True
        elif o in ("--with-counterwalletd",):
            with_counterwalletd = True
        elif o in ("-h", "--help"):
            usage()
            sys.exit()
        else:
            assert False, "Unhandled or unimplemented switch or option"

    paths = get_paths(is_build, with_counterwalletd)

    if is_build:
        logging.info("Building Counterparty...")
        checkout(paths, run_as_user, with_counterwalletd)
        install_dependencies(paths, with_counterwalletd)
        create_virtualenv(paths, with_counterwalletd)
        do_build(paths, with_counterwalletd)
    else: #install mode
        logging.info("Installing Counterparty from source%s..." % (
            (" for user '%s'" % run_as_user) if os.name != "nt" else '',))
        checkout(paths, run_as_user, with_counterwalletd)
        install_dependencies(paths, with_counterwalletd)
        create_virtualenv(paths, with_counterwalletd)
        setup_startup(paths, run_as_user, with_counterwalletd)
    
    logging.info("%s DONE. (It's time to kick ass, and chew bubblegum... and I'm all outta gum.)" % ("BUILD" if is_build else "SETUP"))
    if not is_build:
        create_default_datadir_and_config(paths, run_as_user, with_counterwalletd)


if __name__ == "__main__":
    main()
