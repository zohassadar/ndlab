from __future__ import annotations
import pprint
import sys
import ndlab.current_state as current_state
import ndlab.common as common
import contextlib
import click.shell_completion
import typing as T

import click


class shared_options:
    debug = click.option(
        "-d",
        "--debug",
        is_flag=True,
        help="Enable debugging",
    )

    pattern = click.option(
        "--pattern",
        default="",
        help="Regular expression pattern to filter",
    )

    force = click.option(
        "-f",
        "--force",
        is_flag=True,
        help="Force.  Do not prompt for confirmation",
    )


def sanitize_log_file(filename):
    import pathlib
    import re

    path = pathlib.Path(filename)
    return str(path.parent / re.sub(r"[^\w\.-]", "", path.name))


def output_data(data: list[dict] | T.Any) -> None:
    import tabulate

    try:
        headers = list(data[0].keys())
        converted = [list(d.values()) for d in data]
        print(tabulate.tabulate(converted, headers=headers))
        print("")
    except:
        pprint.pprint(data)


def error_exit(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def get_read_state():
    return current_state.State.from_file(common.NDLAB_STATE_FILE)


@contextlib.contextmanager
def get_write_state() -> T.Generator[current_state.State, None, None]:
    with current_state.State.auto_saving_open(common.NDLAB_STATE_FILE) as state:
        yield state


def tag_completion(context, args, incomplete):
    state = get_read_state()
    return [
        click.shell_completion.CompletionItem(tag)
        for tag in state.tags
        if tag.startswith(incomplete)
    ]


def active_build_tag_completion(context, args, incomplete):
    state = get_read_state()
    return [
        click.shell_completion.CompletionItem(tag)
        for tag in state.get_active_build_tags()
        if tag.startswith(incomplete)
    ]


def base_tag_completion(context, args, incomplete):
    state = get_read_state()
    return [
        click.shell_completion.CompletionItem(tag)
        for tag in state.get_base_tags()
        if tag.startswith(incomplete)
    ]


def device_completion(context, args, incomplete):
    state = get_read_state()
    return [
        click.shell_completion.CompletionItem(device)
        for device in state.devices
        if device.startswith(incomplete)
    ]


def running_device_completion(context, args, incomplete):
    state = get_read_state()
    return [
        click.shell_completion.CompletionItem(device_name)
        for device_name, device in state.devices.items()
        if device_name.startswith(incomplete) and device.pid
    ]


def stopped_device_completion(context, args, incomplete):
    state = get_read_state()
    return [
        click.shell_completion.CompletionItem(device_name)
        for device_name, device in state.devices.items()
        if device_name.startswith(incomplete) and not device.pid
    ]


def bridge_completion(context, args, incomplete):
    state = get_read_state()
    return [
        click.shell_completion.CompletionItem(bridge)
        for bridge in state.bridges
        if bridge.startswith(incomplete)
    ]


def running_bridge_completion(context, args, incomplete):
    state = get_read_state()
    return [
        click.shell_completion.CompletionItem(bridge_name)
        for bridge_name, bridge in state.bridges.items()
        if bridge_name.startswith(incomplete) and bridge.pid
    ]


def stopped_bridge_completion(context, args, incomplete):
    state = get_read_state()
    return [
        click.shell_completion.CompletionItem(bridge_name)
        for bridge_name, bridge in state.bridges.items()
        if bridge_name.startswith(incomplete) and not bridge.pid
    ]


def open_interface_completion(context, args, incomplete):
    state = get_read_state()

    return [
        click.shell_completion.CompletionItem(interface)
        for interface in state.get_open_interfaces()
        if interface.startswith(incomplete)
    ]


def physical_interface_completion(context, args, incomplete):
    import psutil

    nics = list(psutil.net_if_addrs().keys())
    nics.sort()
    return [
        click.shell_completion.CompletionItem(nic)
        for nic in nics
        if nic.startswith(incomplete)
    ]
