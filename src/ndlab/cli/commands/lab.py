import logging

import click

import ndlab.cli.cli_common as cli_common
import ndlab.common as common
import ndlab.current_state as current_state
import ndlab.labmaker as labmaker
import ndlab.config as config


import logging

import click

import ndlab.cli.cli_common as cli_common
import ndlab.common as common


logger = logging.getLogger(__name__)


@click.group(name="lab")
def lab_command():
    pass


def devices_from_topology_completion(
    context: click.Context,
    argument: click.Argument,
    incomplete,
):
    import re

    filename = None

    for arg in context.args:
        if re.search(r"\.ya?ml$", arg, re.I):
            filename = arg
            break
    if not filename:
        return []
    try:
        topology = labmaker.Topology.from_yaml(filename)

    except Exception as exc:
        import sys

        print(f"Unable to load {filename}: {exc}", file=sys.stderr)
        sys.exit(1)
    return [
        device["name"]
        for device in topology.devices
        if device["name"].startswith(incomplete)
    ]


@lab_command.command(help="Load devices from lab file.")
@cli_common.shared_options.debug
@click.option("--validate", is_flag=True, help="Validate against a dummy device")
@click.argument("filename", type=click.Path())
def load(debug, filename, validate):
    common.set_logging(debug)
    logger.debug(f"load invoked.  {debug=} {filename=}")
    topology = labmaker.Topology.from_yaml(filename)
    with cli_common.get_write_state() as state:
        if validate:
            state = state.copy()

        for device in topology.devices:
            device_name = device["name"]
            tag = device["tag"]
            try:
                state.load_device(device_name, tag)
            except current_state.NDLabStateException:
                logger.debug(f"Unable to load {device_name}")
                continue
        for bridge in topology.bridges:
            bridge_name = bridge["name"]
            endpoints_as_strings = [
                (
                    f'{ep["device"]}'
                    f"{current_state.DEVICE_INTERFACE_SEPARATOR}"
                    f'{ep["index"]}'
                )
                for ep in bridge["tcp_endpoints"]
            ]

            nic_endpoint = None
            if bridge["interface_endpoint"]:
                nic_endpoint = bridge["interface_endpoint"]["interface"]
            tap_endpoint = None
            if bridge["tap_endpoint"]:
                tap_endpoint = bridge["tap_endpoint"]["interface"]
            try:
                state.add_bridge(
                    name=bridge_name,
                    tcp_endpoints=endpoints_as_strings,
                    nic_endpoint=nic_endpoint,
                    tap_endpoint=tap_endpoint,
                )
            except:
                logger.debug(f"Unable to load {bridge_name}")
                continue
    cli_common.output_data(state.output_devices())
    cli_common.output_data(state.output_bridges())


@lab_command.command(
    name="config",
    help="Send config to device",
)
@cli_common.shared_options.debug
@click.argument("filename", type=click.Path())
@click.option(
    "--name",
    "names",
    shell_complete=devices_from_topology_completion,
    multiple=True,
)
@click.option(
    "--all",
    is_flag=True,
    help="Load config on all devices",
)
def config_command(
    debug: bool,
    names: str,
    all: bool,
    filename: click.Path,
):
    common.set_logging(debug)
    logger.debug(f"Invoking config.  {debug=} {all=} {names=}")
    state = cli_common.get_read_state()
    topology = labmaker.Topology.from_yaml(str(filename))
    configinfo = config.ConfigInformation(topology)
    template_info = configinfo.get_template_info()
    _names = names
    if all:
        _names = [d["name"] for d in topology.devices]

    for name in _names:
        device = state.load_running_device_from_state(name)
        device_info = template_info.get(name)
        if not device_info:
            raise RuntimeError(f"{name} not part of this lab")
        import pprint

        actual_config = device.dump_config(device_info)
        state.send_config(name, actual_config.splitlines())
