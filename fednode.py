#!/usr/bin/env python3
'''
fednode.py: script to manage a Counterparty federated node
'''

import sys
import os
import argparse
import copy
import subprocess
import configparser

CURDIR = os.getcwd()
SCRIPTDIR = os.path.dirname(os.path.realpath(__file__))
FEDNODE_CONFIG_FILE = ".fednode.config"
FEDNODE_CONFIG_PATH = os.path.join(SCRIPTDIR, FEDNODE_CONFIG_FILE)

UPDATE_CHOICES = ['counterparty', 'counterparty-testnet', 'counterblock', 'counterblock-testnet', 'counterwallet', 'armory_utxsvr', 'armory_utxsvr-testnet']

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action='store_true', default=False, help="increase output verbosity")

    subparsers = parser.add_subparsers(help='help on modes', dest='command')
    subparsers.required = True

    parser_install = subparsers.add_parser('install', help="install fednode services")
    parser_install.add_argument("config", choices=['base', 'counterblock', 'full'], help="The name of the service configuration to utilize")
    parser_install.add_argument("branch", choices=['master', 'develop'], help="The name of the git branch to utilize for the build")

    parser_uninstall = subparsers.add_parser('uninstall', help="uninstall fednode services")
    parser_uninstall.add_argument("--force", help="Force uninstall (no prompting)")

    parser_start = subparsers.add_parser('start', help="start fednode services")
    parser_start.add_argument("service", nargs='?', default='', help="The name of the service to start (or blank to start all services)")

    parser_stop = subparsers.add_parser('stop', help="stop fednode services")
    parser_stop.add_argument("service", nargs='?', default='', help="The name of the service to stop (or blank to stop all services)")

    parser_restart = subparsers.add_parser('restart', help="restart fednode services")
    parser_restart.add_argument("service", nargs='?', default='', help="The name of the service to restart (or blank to restart all services)")

    parser_ps = subparsers.add_parser('ps', help="list installed services")

    parser_tail = subparsers.add_parser('tail', help="tail fednode logs")
    parser_tail.add_argument("service", nargs='?', default='', help="The name of the service whose logs to tail (or blank to tail all services)")

    parser_logs = subparsers.add_parser('logs', help="tail fednode logs")
    parser_logs.add_argument("service", nargs='?', default='', help="The name of the service whose logs to view (or blank to view all services)")

    parser_exec = subparsers.add_parser('exec', help="execute a command on a specific container")
    parser_exec.add_argument("service", help="The name of the service to execute the command on")

    parser_shell = subparsers.add_parser('shell', help="get a shell on a specific service container")
    parser_shell.add_argument("service", help="The name of the service to shell into")

    parser_update = subparsers.add_parser('update', help="upgrade fednode services (i.e. update source code and restart the container, but don't update the container')")
    parser_update.add_argument("service", nargs='?', default='', choices=UPDATE_CHOICES, help="The name of the service to update (or blank to update all applicable services)")
    parser_update.add_argument("--no-restart", help="Don't restart the container after updating the code'")

    parser_rebuild = subparsers.add_parser('rebuild', help="rebuild fednode services (i.e. remove and refetch/install docker containers)")
    parser_rebuild.add_argument("service", nargs='?', default='', help="The name of the service to rebuild (or blank to rebuild all services)")

    return parser.parse_known_args()


def write_config(config):
    cfg_file = open(FEDNODE_CONFIG_PATH, 'w')
    config.write(cfg_file)
    cfg_file.close()


def run_compose_cmd(docker_config_path, cmd):
    return os.system("docker-compose -f {} {}".format(docker_config_path, cmd))


def main():
    if os.name != 'nt' and not os.geteuid() == 0:
        print("Please run this script as root")
        sys.exit(1)

    # parse command line arguments
    args, extra_args = parse_args()

    # if config doesn't exist, only the 'install' command may be run
    config_existed = os.path.exists(FEDNODE_CONFIG_PATH)
    config = configparser.SafeConfigParser()
    if not config_existed:
        if args.command != 'install': 
            print("config file {} does not exist. Please run the 'install' command first")
            sys.exit(1)

        # write default config
        config.add_section('Default')
        config.set('Default', 'branch', args.branch)
        config.set('Default', 'config', args.config)
        write_config(config)

    # load and read config
    assert os.path.exists(FEDNODE_CONFIG_PATH)
    config.read(FEDNODE_CONFIG_PATH)
    docker_config_file = "docker-compose.{}.yml".format(config.get('Default', 'config'))
    docker_config_path = os.path.join(SCRIPTDIR, docker_config_file)
    os.environ['FEDNODE_RELEASE_TAG'] = config.get('Default', 'branch')
    assert os.environ['FEDNODE_RELEASE_TAG']

    # do what we need to do...
    if args.command == 'install':
        if config_existed:
            print("Cannot install, as it appears a configuration already exists. Please run the 'uninstall' command first")
            sys.exit(1)
        os.system("cd {}; git submodule init && git submodule update; cd {}".format(SCRIPTDIR, CURDIR))
        run_compose_cmd(docker_config_path, "up -d")
    elif args.command == 'uninstall':
        run_compose_cmd(docker_config_path, "down")
        os.remove(FEDNODE_CONFIG_PATH)
    elif args.command == 'start':
        run_compose_cmd(docker_config_path, "start {}".format(args.service))
    elif args.command == 'stop':
        run_compose_cmd(docker_config_path, "stop {}".format(args.service))
    elif args.command == 'restart':
        run_compose_cmd(docker_config_path, "restart {}".format(args.service))
    elif args.command == 'tail':
        run_compose_cmd(docker_config_path, "logs -f {}".format(args.service))
    elif args.command == 'logs':
        run_compose_cmd(docker_config_path, "logs {}".format(args.service))
    elif args.command == 'ps':
        run_compose_cmd(docker_config_path, "ps")
    elif args.command == 'exec':
        os.system("docker exec -i -t federatednode_{}_1 {}".format(args.service, extra_args))
    elif args.command == 'shell':
        os.system("docker exec -i -t federatednode_{}_1 bash".format(args.service))
    elif args.command == 'update':
        services_to_update = copy.copy(UPDATE_CHOICES) if not args.service.strip() else [args.service, ]
        while services_to_update:
            service = services_to_update.pop(0)
            #update source code
            service_dir = service.replace('-testnet', '')
            service_branch = subprocess.check_output("cd {};git symbolic-ref --short -q HEAD;cd {}".format(SCRIPTDIR, CURDIR), shell=True)
            if not service_branch:
                print("Unknown service git branch name, or repo in detached state")
                sys.exit(1)

            os.system("cd {}; git pull origin {}; cd {}".format(SCRIPTDIR, service_branch, CURDIR))
            run_compose_cmd(docker_config_path, "restart {}".format(service))
    elif args.command == 'rebuild':
        run_compose_cmd(docker_config_path, "up -d --build --no-deps {}".format(args.service))


if __name__ == '__main__':
    main()
