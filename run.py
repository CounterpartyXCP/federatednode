#! /usr/bin/env python3
"""
Runs counterpartyd or the counterpartyd test suite via the python interpreter in its virtualenv on both Linux and Windows
"""
import os
import sys

assert os.name in ("nt", "posix")

#under *nix, script must NOT be run as root
if os.name == "posix" and os.geteuid() == 0:
    print("Please run this script as a non-root user.")
    sys.exit(1)

run_tests = False
run_counterwalletd = False
args = sys.argv[1:]
if len(sys.argv) >= 2 and sys.argv[1] == 'tests':
    run_tests = True
    args = sys.argv[2:]
elif len(sys.argv) >= 2 and sys.argv[1] == 'counterwalletd':
    run_counterwalletd = True
    args = sys.argv[2:]
    
base_path = os.path.dirname(os.path.realpath(sys.argv[0]))
env_path = os.path.join(base_path, "env")
dist_path = os.path.join(base_path, "dist")
python_path = os.path.join(env_path, "Scripts" if os.name == "nt" else "bin", "python.exe" if os.name == "nt" else "python")

if run_tests:
    pytest_path = os.path.join(env_path, "Scripts" if os.name == "nt" else "bin", "py.test.exe" if os.name == "nt" else "py.test")
    counterpartyd_tests_path = os.path.join(dist_path, "counterpartyd", "test", "test_.py")
    command = "%s %s %s" % (pytest_path, counterpartyd_tests_path, ' '.join(args))
elif run_counterwalletd:
    counterwalletd_env_path = os.path.join(base_path, "env.cwalletd")
    counterwalletd_python_path = os.path.join(counterwalletd_env_path, "Scripts" if os.name == "nt" else "bin", "python.exe" if os.name == "nt" else "python")
    counterwalletd_path = os.path.join(dist_path, "counterwalletd", "counterwalletd.py")
    command = "%s %s %s" % (counterwalletd_python_path, counterwalletd_path, ' '.join(args))
else: #run counterpartyd
    counterpartyd_path = os.path.join(dist_path, "counterpartyd", "counterpartyd.py")
    command = "%s %s %s" % (python_path, counterpartyd_path, ' '.join(args))
os.system(command)
