#! /usr/bin/env python3
"""
Tighten up an Ubuntu host box
"""
import os
import sys
import re
import logging
import socket
import platform


DIST_PATH = os.path.join(os.path.dirname(__file__), "dist")


def runcmd(command, abort_on_failure=True):
    logging.debug("RUNNING COMMAND: %s" % command)
    ret = os.system(command)
    if abort_on_failure and ret != 0:
        logging.error("Command failed: '%s'" % command)
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


def do_security_setup():
    """Some helpful security-related tasks, to tighten up the box"""

    # modify host.conf
    modify_config(r'^nospoof on$', 'nospoof on', '/etc/host.conf')

    # enable automatic security updates
    runcmd("apt-get -y install unattended-upgrades")
    runcmd('''bash -c "echo -e 'APT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";' > /etc/apt/apt.conf.d/20auto-upgrades" ''')
    runcmd("dpkg-reconfigure -fnoninteractive -plow unattended-upgrades")

    # sysctl
    runcmd("install -m 0644 -o root -g root -D %s/sysctl_rules.conf /etc/sysctl.d/60-tweaks.conf" % DIST_PATH)

    # set up fail2ban
    runcmd("apt-get -y install fail2ban")
    runcmd("install -m 0644 -o root -g root -D %s/fail2ban.jail.conf /etc/fail2ban/jail.d/counterblock.conf" % DIST_PATH)
    runcmd("service fail2ban restart")

    # set up psad (this will install postfix, which will prompt the user)
    runcmd("apt-get -y install psad")
    modify_config(r'^ENABLE_AUTO_IDS\s+?N;$', 'ENABLE_AUTO_IDS\tY;', '/etc/psad/psad.conf')
    modify_config(r'^ENABLE_AUTO_IDS_EMAILS\s+?Y;$', 'ENABLE_AUTO_IDS_EMAILS\tN;', '/etc/psad/psad.conf')
    for f in ['/etc/ufw/before.rules', '/etc/ufw/before6.rules']:
        modify_config(
            r'^# End required lines.*?# allow all on loopback$',
            '# End required lines\n\n#CUSTOM: for psad\n-A INPUT -j LOG\n-A FORWARD -j LOG\n\n# allow all on loopback',
            f, dotall=True)
    runcmd("psad -R && psad --sig-update")
    runcmd("service ufw restart")
    runcmd("service psad restart")

    # set up chkrootkit, rkhunter
    runcmd("apt-get -y install rkhunter chkrootkit")
    runcmd('bash -c "rkhunter --update; exit 0"')
    runcmd("rkhunter --propupd")
    runcmd('bash -c "rkhunter --check --sk; exit 0"')
    runcmd("rkhunter --propupd")

    # logwatch
    runcmd("apt-get -y install logwatch libdate-manip-perl")

    # apparmor
    runcmd("apt-get -y install apparmor apparmor-profiles")

    # auditd
    # note that auditd will need a reboot to fully apply the rules, due to it operating in "immutable mode" by default
    runcmd("apt-get -y install auditd audispd-plugins")
    runcmd("install -m 0640 -o root -g root -D %s/audit.rules /etc/audit/rules.d/counterblock.rules" % DIST_PATH)
    modify_config(r'^USE_AUGENRULES=.*?$', 'USE_AUGENRULES="yes"', '/etc/default/auditd')
    runcmd("service auditd restart")

    # iwatch
    runcmd("apt-get -y install iwatch")
    modify_config(r'^START_DAEMON=.*?$', 'START_DAEMON=true', '/etc/default/iwatch')
    runcmd("install -m 0644 -o root -g root -D %s/iwatch.xml /etc/iwatch/iwatch.xml" % DIST_PATH)
    modify_config(r'guard email="root@localhost"', 'guard email="noreply@%s"' % socket.gethostname(), '/etc/iwatch/iwatch.xml')
    runcmd("service iwatch restart")

if __name__ == "__main__":
    if platform.dist()[0] != "Ubuntu":
        logging.error("Script requires Ubuntu linux")
        sys.exit(1)

    do_security_setup()
