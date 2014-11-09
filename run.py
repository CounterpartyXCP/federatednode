#! /usr/bin/env python3
"""
Runs counterpartyd or the counterpartyd test suite via the python interpreter in its virtualenv on both Linux and Windows
"""
import os
import sys
import subprocess

assert os.name in ("nt", "posix")

#under *nix, script must NOT be run as root
if os.name == "posix" and os.geteuid() == 0:
    print("Please run this script as a non-root user.")
    sys.exit(1)

run = None
if len(sys.argv) >= 2 and sys.argv[1] == 'tests':
    args = sys.argv[2:]
    run = 'tests'
elif len(sys.argv) >= 2 and sys.argv[1] == 'counterblockd':
    args = sys.argv[2:]
    run = 'counterblockd'
elif len(sys.argv) >= 2 and sys.argv[1] == 'armory_utxsvr':
    args = sys.argv[2:]
    run = 'armory_utxsvr'
else:
    args = sys.argv[1:]
    run = 'counterpartyd'
    
base_path = os.path.dirname(os.path.realpath(sys.argv[0]))
env_path = os.path.join(base_path, "env")
dist_path = os.path.join(base_path, "dist")
python_path = os.path.join(env_path, "Scripts" if os.name == "nt" else "bin", "python.exe" if os.name == "nt" else "python")

def delete_lockfile(component):
    import appdirs #installed earlier
    import glob
    running_testnet = "--testnet" in args
    data_dir = appdirs.user_data_dir(appauthor='Counterparty',
        appname="%s%s" % (component, "-testnet" if running_testnet else ''), roaming=True)
    lockfile_paths = glob.glob(os.path.join("%s%scounterpartyd.*.db.lock" % (data_dir, os.sep)))
    for p in lockfile_paths:
        print("Removing stale lock file at '%s'" % p)
        os.remove(p)

if run == 'tests':
    pytest_path = os.path.join(env_path, "Scripts" if os.name == "nt" else "bin", "py.test.exe" if os.name == "nt" else "py.test")
    counterpartyd_tests_path = os.path.join(dist_path, "counterpartyd", "test", "test_.py")
    command = "%s %s %s" % (pytest_path, counterpartyd_tests_path, ' '.join(args))
elif run == 'counterblockd':
    delete_lockfile("counterblockd")
    counterblockd_env_path = os.path.join(base_path, "env.counterblockd")
    counterblockd_python_path = os.path.join(counterblockd_env_path, "Scripts" if os.name == "nt" else "bin", "python.exe" if os.name == "nt" else "python")
    counterblockd_path = os.path.join(dist_path, "counterblockd", "counterblockd.py")
    command = "%s %s %s" % (counterblockd_python_path, counterblockd_path, ' '.join(args))
elif run == 'armory_utxsvr':
    armory_utxsvr_env_path = os.path.join(base_path, "env.counterblockd") #use the counterblock venv
    armory_utxsvr_python_path = os.path.join(armory_utxsvr_env_path, "Scripts" if os.name == "nt" else "bin", "python.exe" if os.name == "nt" else "python")
    armory_utxsvr_path = os.path.join(dist_path, "counterblockd", "armory_utxsvr.py")
    command = "DISPLAY=localhost:1.0 xvfb-run --auto-servernum %s %s %s" % (armory_utxsvr_python_path, armory_utxsvr_path, ' '.join(args))
else:
    assert run == 'counterpartyd'
    delete_lockfile("counterpartyd")
    counterpartyd_path = os.path.join(dist_path, "counterpartyd", "counterpartyd.py")
    command = "%s %s %s" % (python_path, counterpartyd_path, ' '.join(args))

status = subprocess.call(command, shell=True)
sys.exit(status)
