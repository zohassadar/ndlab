import logging

import click

import ndlab.cli.cli_common as cli_common
import ndlab.common as common
import ndlab.connect as connect


logger = logging.getLogger(__name__)


@click.command(
    help="Start bridge service",
    name="launch-bridge",
    # hidden=True,
)
@cli_common.shared_options.debug
@click.option(
    "-n",
    "--name",
)
@click.option(
    "-l",
    "--log-file",
)
@click.option(
    "-t",
    "--tcp-endpoint",
    "tcp_endpoints",
    multiple=True,
)
@click.option(
    "-s",
    "--sniffer-port",
    type=int,
)
@click.option(
    "-p",
    "--physical-endpoint",
    shell_complete=cli_common.physical_interface_completion,
)
@click.option(
    "-T",
    "--tap-endpoint",
    shell_complete=cli_common.physical_interface_completion,
)
def launch_bridge_command(
    debug,
    name,
    log_file,
    physical_endpoint,
    tap_endpoint,
    sniffer_port,
    tcp_endpoints,
):
    common.set_logging(debug)

    logger.debug(
        f"Launch connection invoked {name=} {log_file=} {sniffer_port=} {physical_endpoint=} {tap_endpoint=} {tcp_endpoints=}",
    )
    connect.start_bridge(
        name=name,
        log_file=cli_common.sanitize_log_file(log_file),
        debug=debug,
        tcp_endpoints=tcp_endpoints,
        physical_endpoint=physical_endpoint,
        tap_endpoint=tap_endpoint,
        sniffer_port=sniffer_port,
    )
