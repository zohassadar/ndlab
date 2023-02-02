import logging
import sys

import click

import ndlab.cli.cli_common as cli_common
import ndlab.common as common
import ndlab.current_state as current_state

logger = logging.getLogger(__name__)


@click.group(name="device")
def device_command():
    pass


@device_command.command(
    name="list",
    help="List devices",
)
@cli_common.shared_options.debug
@cli_common.shared_options.pattern
def device_list(debug, pattern):
    common.set_logging(debug)
    logger.debug(f"device list invoked. {debug=} {pattern=}")
    state = cli_common.get_read_state()
    cli_common.output_data(state.output_devices())


@device_command.command(help="Add device")
@click.option(
    "--tag",
    required=True,
    shell_complete=cli_common.tag_completion,
)
@click.option(
    "--name",
    required=True,
)
@cli_common.shared_options.debug
def add(debug, tag, name):
    common.set_logging(debug)
    logger.debug(f"device load invoked. {debug=} {tag=} {name=}")

    with cli_common.get_write_state() as state:
        state.load_device(
            tag=tag,
            name=name,
        )


@device_command.command(
    name="delete",
    help="Delete device",
)
@cli_common.shared_options.debug
@click.option(
    "--all",
    is_flag="true",
    help="Delete all devices",
)
@click.argument(
    "names",
    nargs=-1,
    shell_complete=cli_common.device_completion,
)
def device_delete(debug, names, all):
    common.set_logging(debug)
    logger.debug(f"device delete invoked {names=} {all=} {debug=}")
    with cli_common.get_write_state() as state:
        if all:
            devices = list(state.devices)
        else:
            devices = names
        for device in devices:
            try:
                state.delete_device(device)
            except current_state.NDLabStateException as exc:
                logger.info(f"Unable to stop device: {exc}")


@device_command.command(
    name="start",
    help="Start device",
)
@cli_common.shared_options.debug
@click.option(
    "--qemu-img-cmd",
    is_flag=True,
    help="Print qemu-img cmd (does not run)",
)
@click.option(
    "--qemu-cmd",
    is_flag=True,
    help="Print qemu cmd (does not run)",
)
@click.option(
    "--all",
    is_flag="true",
    help="Start all devices",
)
@click.argument(
    "names",
    nargs=-1,
    shell_complete=cli_common.stopped_device_completion,
)
def device_start(debug, names, all, qemu_img_cmd, qemu_cmd):
    common.set_logging(debug)
    logger.debug(f"start invoked {names=} {all} {debug=}")

    with cli_common.get_write_state() as state:
        if all:
            devices = list(state.devices)
        else:
            devices = names
        for device in devices:
            try:
                if qemu_cmd:
                    print(" ".join(state.get_qemu_cmd(device)))
                if qemu_img_cmd:
                    print(" ".join(state.get_qemu_image_cmd(device)))
                if qemu_cmd or qemu_img_cmd:
                    continue
                state.start_device(device)
            except current_state.NDLabStateException as exc:
                print(f"Unable to start device: {exc}", file=sys.stderr)


@device_command.command(
    name="stop",
    help="Stop device",
)
@cli_common.shared_options.debug
@click.option(
    "--all",
    is_flag="true",
    help="Stop all devices",
)
@click.argument(
    "names",
    nargs=-1,
    shell_complete=cli_common.running_device_completion,
)
def device_stop(debug, names, all):
    common.set_logging(debug)
    logger.debug(f"stop invoked {names=} {all=} {debug=}")
    with cli_common.get_write_state() as state:
        if all:
            devices = list(state.devices)
        else:
            devices = names
        for device in devices:
            try:
                state.stop_device(device)
            except current_state.NDLabStateException as exc:
                logger.info(f"Unable to stop device: {exc}")
