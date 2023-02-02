import click
import ndlab.cli.cli_common as cli_common
import sys
import ndlab.common as common


@click.command(
    name="console",
    help="Launch telnet to device console port",
)
@cli_common.shared_options.debug
@click.option(
    "-q",
    "--qemu",
    is_flag=True,
    help="Connect to qemu mgmt console",
)
@click.argument("name", shell_complete=cli_common.running_device_completion)
def console_command(debug, name, qemu):
    common.set_logging(debug)
    import subprocess

    state = cli_common.get_read_state()
    if qemu:
        port = state.get_qemu_port(name)
    else:
        port = state.get_device_console_port(name, 0)
    launched = subprocess.run(["telnet", "localhost", f"{port}"])
    sys.exit(launched.returncode)
