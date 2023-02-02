import logging
import pathlib

import click

import ndlab.cli.cli_common as cli_common
import ndlab.common as common
import ndlab.current_state as current_state
import ndlab.images as images

logger = logging.getLogger(__name__)


@click.group(name="image")
def image_command():
    pass


@image_command.command(help="Add new image tag")
@cli_common.shared_options.debug
@click.argument("tag")
@click.argument("image", type=click.Path())
def tag(
    debug,
    image: pathlib.Path,
    tag: str,
):
    common.set_logging(debug)
    logger.debug(f"image tag invoked. {debug=} {image=} {tag=}")
    with cli_common.get_write_state() as state:
        state.add_tag(
            tag=tag,
            image=image,
        )


@image_command.command(
    name="list",
    help="List tagged images",
)
@cli_common.shared_options.pattern
@cli_common.shared_options.debug
def list_command(debug, pattern):
    logger.debug(f"image list invoked.  {debug=} {pattern=}")
    state = cli_common.get_read_state()
    cli_common.output_data(state.output_tags())


@image_command.command(
    name="delete",
    help="Delete image tag",
)
@cli_common.shared_options.debug
@click.argument("tag", shell_complete=cli_common.tag_completion)
def delete(debug, tag):
    logger.debug(f"image delete invoked.  {debug=} {tag=}")
    with cli_common.get_write_state() as state:
        state.delete_tag(tag)


@image_command.command(help="Auto add tags")
@click.option(
    "--overwrite",
    is_flag=True,
)
@cli_common.shared_options.debug
def discover(debug, overwrite):
    logger.debug(f"image discover invoked. {overwrite=} {debug=}")
    tags = images.auto_discover_tags()
    with cli_common.get_write_state() as state:
        for tag, image in tags.items():
            try:
                state.add_tag(tag, image, overwrite)
            except current_state.NDLabStateException as exc:
                logger.debug(f"Unable to add tag: {exc!s}")
