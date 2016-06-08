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
import socket

CURDIR = os.getcwd()
SCRIPTDIR = os.path.dirname(os.path.realpath(__file__))
FEDNODE_CONFIG_FILE = ".fednode.config"
FEDNODE_CONFIG_PATH = os.path.join(SCRIPTDIR, FEDNODE_CONFIG_FILE)

PROJECT_NAME = "federatednode"
REPO_BASE = "https://github.com/CounterpartyXCP/{}.git"
REPOS = ['counterparty-lib', 'counterparty-cli', 'counterblock', 'counterwallet', 'armory-utxsvr']
HOST_PORTS_USED = {
    'base': [8332, 18332, 4000, 14000],
    'counterblock': [8332, 18332, 4000, 14000, 4100, 14100],
    'full': [8332, 18332, 4000, 14000, 4100, 14100, 80, 443]
}
UPDATE_CHOICES = ['counterparty', 'counterparty-testnet', 'counterblock', 'counterblock-testnet', 'counterwallet', 'armory-utxsvr', 'armory-utxsvr-testnet']
REPARSE_CHOICES = ['counterparty', 'counterparty-testnet', 'counterblock', 'counterblock-testnet']

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

    parser_reparse = subparsers.add_parser('reparse', help="reparse a counterparty-server or counterblock service")
    parser_reparse.add_argument("service", choices=REPARSE_CHOICES, help="The name of the service for which to kick off a reparse")

    parser_ps = subparsers.add_parser('ps', help="list installed services")

    parser_tail = subparsers.add_parser('tail', help="tail fednode logs")
    parser_tail.add_argument("service", nargs='?', default='', help="The name of the service whose logs to tail (or blank to tail all services)")

    parser_logs = subparsers.add_parser('logs', help="tail fednode logs")
    parser_logs.add_argument("service", nargs='?', default='', help="The name of the service whose logs to view (or blank to view all services)")

    parser_exec = subparsers.add_parser('exec', help="execute a command on a specific container")
    parser_exec.add_argument("service", help="The name of the service to execute the command on")
    parser_exec.add_argument("cmd", nargs=argparse.REMAINDER, help="The shell command to execute")

    parser_shell = subparsers.add_parser('shell', help="get a shell on a specific service container")
    parser_shell.add_argument("service", help="The name of the service to shell into")

    parser_update = subparsers.add_parser('update', help="upgrade fednode services (i.e. update source code and restart the container, but don't update the container')")
    parser_update.add_argument("service", nargs='?', default='', choices=UPDATE_CHOICES, help="The name of the service to update (or blank to update all applicable services)")
    parser_update.add_argument("--no-restart", help="Don't restart the container after updating the code'")

    parser_rebuild = subparsers.add_parser('rebuild', help="rebuild fednode services (i.e. remove and refetch/install docker containers)")
    parser_rebuild.add_argument("service", nargs='?', default='', help="The name of the service to rebuild (or blank to rebuild all services)")

    parser_docker_clean = subparsers.add_parser('docker_clean', help="remove ALL docker containers and cached images (use with caution!)")

    return parser.parse_args()


def write_config(config):
    cfg_file = open(FEDNODE_CONFIG_PATH, 'w')
    config.write(cfg_file)
    cfg_file.close()


def run_compose_cmd(docker_config_path, cmd):
    return os.system("docker-compose -f {} -p {} {}".format(docker_config_path, PROJECT_NAME, cmd))


def is_port_open(port):
    # TCP ports only
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    return sock.connect_ex(('127.0.0.1', port)) == 0  # returns True if the port is open


def main():
    if os.name != 'nt' and not os.geteuid() == 0:
        print("Please run this script as root")
        sys.exit(1)
    if os.name != 'nt':
        SESSION_USER = subprocess.check_output("logname", shell=True).decode("utf-8").strip()
    else:
        SESSION_USER = None

    # parse command line arguments
    args = parse_args()

    # run utility commands (docker_clean) if specified
    if args.command == 'docker_clean':
        docker_containers = subprocess.check_output("docker ps -a -q", shell=True).decode("utf-8").split('\n')
        docker_images = subprocess.check_output("docker images -q", shell=True).decode("utf-8").split('\n')
        for container in docker_containers:
            if not container:
                continue
            os.system("docker rm {}".format(container))
        for image in docker_images:
            if not image:
                continue
            os.system("docker rmi {}".format(image))
        sys.exit(1)

    # for all other commands
    # if config doesn't exist, only the 'install' command may be run
    config_existed = os.path.exists(FEDNODE_CONFIG_PATH)
    config = configparser.SafeConfigParser()
    if not config_existed:
        if args.command != 'install': 
            print("config file {} does not exist. Please run the 'install' command first".format(FEDNODE_CONFIG_FILE))
            sys.exit(1)

        # write default config
        config.add_section('Default')
        config.set('Default', 'branch', args.branch)
        config.set('Default', 'config', args.config)
        write_config(config)

    # load and read config
    assert os.path.exists(FEDNODE_CONFIG_PATH)
    config.read(FEDNODE_CONFIG_PATH)
    build_config = config.get('Default', 'config')
    docker_config_file = "docker-compose.{}.yml".format(build_config)
    docker_config_path = os.path.join(SCRIPTDIR, docker_config_file)
    repo_branch = config.get('Default', 'branch')
    os.environ['FEDNODE_RELEASE_TAG'] = config.get('Default', 'branch')
    assert os.environ['FEDNODE_RELEASE_TAG']

    # perform action for the specified command
    if args.command == 'install':
        if config_existed:
            print("Cannot install, as it appears a configuration already exists. Please run the 'uninstall' command first")
            sys.exit(1)

        # check port usage
        for port in HOST_PORTS_USED[build_config]:
            if is_port_open(port):
                print("Cannot install, as it appears a process is already listening on host port {}".format(port))
                sys.exit(1)

        # check out the necessary source trees (don't use submodules due to detached HEAD and other problems)
        for repo in REPOS:
            repo_url = REPO_BASE.format(repo)
            repo_dir = os.path.join(SCRIPTDIR, "src", repo)
            if not os.path.exists(repo_dir):
                git_cmd = "git clone -b {} {} {}".format(repo_branch, repo_url, repo_dir)
                if SESSION_USER:  # check out the code as the original user, so the permissions are right
                    os.system("su -c '{}' {}".format(git_cmd, SESSION_USER))
                else:
                    os.system(git_cmd)

        # make sure we have the newest image for each service
        run_compose_cmd(docker_config_path, "pull --ignore-pull-failures")

        # launch
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
    elif args.command == 'reparse':
        run_compose_cmd(docker_config_path, "stop {}".format(args.service))
        if args.service in ['counterparty', 'counterparty-testnet']:
            run_compose_cmd(docker_config_path, "run -e COMMAND=reparse {}".format(args.service))
        elif args.service in ['counterblock', 'counterblock-testnet']:
            run_compose_cmd(docker_config_path, "run -e EXTRA_PARAMS=\"--reparse\" {}".format(args.service))
    elif args.command == 'tail':
        run_compose_cmd(docker_config_path, "logs -f {}".format(args.service))
    elif args.command == 'logs':
        run_compose_cmd(docker_config_path, "logs {}".format(args.service))
    elif args.command == 'ps':
        run_compose_cmd(docker_config_path, "ps")
    elif args.command == 'exec':
        os.system("docker exec -i -t federatednode_{}_1 {}".format(args.service, ' '.join(args.cmd)))
    elif args.command == 'shell':
        exec_result = os.system("docker exec -i -t federatednode_{}_1 bash".format(args.service))
        if exec_result != 0:
            print("Container is not running -- starting it with a 'bash' shell entrypoint...")
            run_compose_cmd(docker_config_path, "run --no-deps --entrypoint bash {}".format(args.service))
    elif args.command == 'update':
        services_to_update = copy.copy(UPDATE_CHOICES) if not args.service.strip() else [args.service, ]
        git_has_updated = []
        while services_to_update:
            service = services_to_update.pop(0)

            #update source code and restart container
            service_dir = service.replace('-testnet', '')
            if service_dir not in git_has_updated:
                git_has_updated.append(service_dir)
                service_dir_path = os.path.join(SCRIPTDIR, "src", service_dir)
                service_branch = subprocess.check_output("cd {};git symbolic-ref --short -q HEAD;cd {}".format(service_dir_path, CURDIR), shell=True).decode("utf-8").strip()
                if not service_branch:
                    print("Unknown service git branch name, or repo in detached state")
                    sys.exit(1)

                git_cmd = "cd {}; git pull origin {}; cd {}".format(service_dir_path, service_branch, CURDIR)
                if SESSION_USER:  # update the code as the original user, so the permissions are right
                    os.system("su -c '{}' {}".format(git_cmd, SESSION_USER))
                else:
                    os.system(git_cmd)

            run_compose_cmd(docker_config_path, "restart {}".format(service))
    elif args.command == 'rebuild':
        run_compose_cmd(docker_config_path, "pull --ignore-pull-failures {}".format(args.service))
        run_compose_cmd(docker_config_path, "up -d --build --force-recreate --no-deps {}".format(args.service))


if __name__ == '__main__':
    main()
