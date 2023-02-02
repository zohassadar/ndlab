import logging

import click

import ndlab.cli.cli_common as cli_common
import ndlab.common as common
import ndlab.current_state as current_state

logger = logging.getLogger(__name__)


@click.group(name="state")
def state_command():
    pass


@state_command.command(
    name="delete",
    help="Delete state",
)
@cli_common.shared_options.debug
def state_delete(debug):
    common.set_logging(debug)
    state = current_state.State()
    state.save(common.NDLAB_STATE_FILE)


@state_command.command(
    name="show",
    help="Show state",
)
@cli_common.shared_options.debug
def state_show(debug):
    common.set_logging(debug)
    state = cli_common.get_read_state()
    cli_common.output_data(state.asdict())


@state_command.command(help="Refresh state")
@cli_common.shared_options.debug
def refresh(debug):
    common.set_logging(debug)
    with cli_common.get_write_state() as state:
        state.check_state()


@state_command.command(help="Kill everything")
@cli_common.shared_options.debug
def kill(debug):
    common.set_logging(debug)
    print(
        "ps -ef | grep -P '[q]emu-system|ndl[a]b launch-bridge' | awk '{print $2}' | xargs -r kill",
    )
