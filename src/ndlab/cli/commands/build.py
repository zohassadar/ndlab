import logging

import click

import ndlab.cli.cli_common as cli_common
import ndlab.common as common
import ndlab.current_state as current_state
import ndlab.images as images

logger = logging.getLogger(__name__)


@click.group(name="build")
def build_command():
    pass


@build_command.command(help="Load images to get ready for building")
@cli_common.shared_options.debug
@click.option(
    "--all",
    is_flag=True,
    help="Create build image for all non-build tags",
)
@click.option(
    "--build-tag",
    default=common.DEFAULT_BUILD_TAG,
    help=f"Tag to build the images.  Default is {common.DEFAULT_BUILD_TAG},",
)
@click.argument(
    "base_tags",
    nargs=-1,
    shell_complete=cli_common.base_tag_completion,
)
def load(debug, base_tags, all, build_tag):
    common.set_logging(debug)
    logger.debug(f"build load invoked {debug=} {base_tags=} {all=} {build_tag=}")
    with cli_common.get_write_state() as state:
        _base_tags = base_tags
        if all:
            _base_tags = state.get_base_tags()
        for base_tag in _base_tags:
            full_tag = images.get_build_tag(base_tag, build_tag)
            state.load_device(
                tag=base_tag,
                name=full_tag,
                build_tag=build_tag,
            )


@build_command.command(help="Run device build steps")
@cli_common.shared_options.debug
@click.option(
    "--all",
    is_flag=True,
    help="Finalize all build images",
)
@click.argument(
    "build_tags",
    nargs=-1,
    shell_complete=cli_common.active_build_tag_completion,
)
def configure(debug, build_tags, all):
    common.set_logging(debug)
    logger.debug(f"build configure invoked {debug=} {build_tags=} {all=}")
    with cli_common.get_write_state() as state:
        _build_tags = build_tags
        if all:
            _build_tags = state.get_active_build_tags()
        for _build_tag in _build_tags:
            state.send_config(_build_tag)


@build_command.command(help="Finalize build images")
@cli_common.shared_options.debug
@click.option(
    "--all",
    is_flag=True,
    help="Finalize all build images",
)
@click.argument(
    "build_tags",
    nargs=-1,
    shell_complete=cli_common.active_build_tag_completion,
)
def finalize(debug, build_tags, all):
    common.set_logging(debug)
    logger.debug(f"build finalize invoked {debug=} {build_tags=} {all=}")
    with cli_common.get_write_state() as state:
        _build_tags = build_tags
        if all:
            _build_tags = state.get_active_build_tags()
        for _build_tag in _build_tags:
            device = state.get_running_device_state(_build_tag)
            state.add_tag(_build_tag, device.overlay)
            state.delete_device(_build_tag, leave_overlay=True)
