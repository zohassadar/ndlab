import click
import ndlab.cli.cli_common as cli_common
import ndlab.common as common
import ndlab.current_state as current_state
import logging

logger = logging.getLogger(__name__)


@click.group(name="bridge")
def bridge_command():
    pass


@bridge_command.command(
    name="delete",
    help="Delete a bridge",
)
@cli_common.shared_options.debug
@click.option(
    "--all",
    is_flag="true",
    help="Delete all bridges",
)
@click.argument(
    "names",
    nargs=-1,
    shell_complete=cli_common.running_bridge_completion,
)
def bridge_delete(debug, names, all):
    common.set_logging(debug)
    with cli_common.get_write_state() as state:
        if all:
            bridges = list(state.bridges)
        else:
            bridges = names
        for bridge in bridges:
            try:
                state.stop_bridge(bridge, delete=True)
            except current_state.NDLabStateException as exc:
                logger.info(f"Unable to delete bridge: {exc}")


@bridge_command.command(
    name="stop",
    help="Stop a bridge",
)
@cli_common.shared_options.debug
@click.option(
    "--all",
    is_flag="true",
    help="Stop all bridges",
)
@click.argument(
    "names",
    shell_complete=cli_common.running_bridge_completion,
)
def bridge_stop(debug, names, all):
    common.set_logging(debug)
    with cli_common.get_write_state() as state:
        if all:
            bridges = list(state.bridges)
        else:
            bridges = names
        for bridge in bridges:
            try:
                state.stop_bridge(bridge)
            except current_state.NDLabStateException as exc:
                logger.info(f"Unable to stop bridge: {exc}")


@bridge_command.command(
    name="start",
    help="Start a bridge",
)
@cli_common.shared_options.debug
@click.option(
    "--all",
    is_flag="true",
    help="Start all bridges",
)
@click.argument(
    "names",
    nargs=-1,
    shell_complete=cli_common.stopped_bridge_completion,
)
def bridge_start(debug, names, all):
    common.set_logging(debug)
    with cli_common.get_write_state() as state:
        if all:
            bridges = list(state.bridges)
        else:
            bridges = names
        for bridge in bridges:
            try:
                state.start_bridge(bridge)
            except current_state.NDLabStateException as exc:
                logger.info(f"Unable to start bridge: {exc}")


@bridge_command.command(
    name="list",
    help="List bridges",
)
@cli_common.shared_options.debug
def bridge_list(debug):
    common.set_logging(debug)
    state = cli_common.get_read_state()
    for output in state.output_bridges():
        if not output:
            continue
        cli_common.output_data(output)


@bridge_command.command(
    name="add",
    help="Add new bridge",
)
@cli_common.shared_options.debug
@click.option("--sniffer")
@click.option("--physical", shell_complete=cli_common.physical_interface_completion)
@click.option("--name", required=True)
@click.option(
    "--tcp-endpoint",
    "tcp_endpoints",
    multiple=True,
    shell_complete=cli_common.open_interface_completion,
)
def bridge_add(
    debug,
    name: str,
    sniffer: str,
    physical: str,
    tcp_endpoints: tuple[str],
):

    common.set_logging(debug)
    logger.debug(f"bridge add invoked {name=} {sniffer=} {physical=} {tcp_endpoints=}")
    with cli_common.get_write_state() as state:
        state.add_bridge(
            name,
            list(tcp_endpoints),
            nic_endpoint=physical,
            sniffer_endpoint=sniffer,
        )


@bridge_command.command(help="Register PID for bridge launched as root")
@cli_common.shared_options.debug
@click.argument("name")
@click.argument("pid", type=int)
def register_bridge_pid(debug, name, pid: int):
    with cli_common.get_write_state() as state:
        state.register_bridge_pid(name, pid)
