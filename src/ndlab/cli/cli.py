#!/usr/bin/env python3
import logging
import ndlab.current_state as current_state
import click

from .commands.bridge import bridge_command
from .commands.console import console_command
from .commands.build import build_command
from .commands.device import device_command
from .commands.image import image_command
from .commands.lab import lab_command
from .commands.launch_bridge import launch_bridge_command
from .commands.state import state_command

logger = logging.getLogger(__name__)


@click.group()
def cli():
    pass


cli.add_command(bridge_command)
cli.add_command(console_command)
cli.add_command(build_command)
cli.add_command(device_command)
cli.add_command(image_command)
cli.add_command(lab_command)
cli.add_command(launch_bridge_command)
cli.add_command(state_command)


def main():
    try:
        cli()
    except current_state.NDLabStateException as exc:
        logger.debug(f"Caught exception in main: {exc}")
