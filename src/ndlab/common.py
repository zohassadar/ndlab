from __future__ import annotations

import logging

import os
import pathlib
import re
import typing as T

if T.TYPE_CHECKING:
    from ndlab.console import ConsoleDumper
    from ndlab.config import DeviceInfo


def get_free_port() -> int:
    import contextlib
    import socket

    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


DEVICE_IS_READY = b"DEVICE IS READY!"

DEVICE_REQUIRES_BUILD = b"DEVICE NEEDS BUILDING"


DEFAULT_BUILD_TAG = "build"

SOCKET_TIMEOUT = 1
MAX_SIZE = 10000


NDLAB_DIRECTORY_ENV = "NDLAB_DIRECTORY"
NDLAB_DIRECTORY_DEFAULT = pathlib.Path.home() / ".ndlab"
NDLAB_DIRECTORY = pathlib.Path(
    os.getenv(NDLAB_DIRECTORY_ENV, NDLAB_DIRECTORY_DEFAULT),
)

STATE_FILE_ENV = "NDLAB_STATE_FILE"
STATE_FILE_DEFAULT = NDLAB_DIRECTORY / "ndlab.yml"
NDLAB_STATE_FILE = pathlib.Path(
    os.getenv(STATE_FILE_ENV, STATE_FILE_DEFAULT),
)


LABS_DIRECTORY_ENV = "NDLAB_LABS"
LABS_DEFAULT_DIRECTORY = NDLAB_DIRECTORY / "labs"
LABS_DIRECTORY = pathlib.Path(
    os.getenv(LABS_DIRECTORY_ENV, LABS_DEFAULT_DIRECTORY),
)


IMAGES_DIRECTORY_ENV = "NDLAB_IMAGES"
IMAGES_DEFAULT_DIRECTORY = NDLAB_DIRECTORY / "images"
IMAGES_DIRECTORY = pathlib.Path(
    os.getenv(IMAGES_DIRECTORY_ENV, IMAGES_DEFAULT_DIRECTORY),
)

BUILDS_DIRECTORY_ENV = "NDLAB_BUILD_DIRECTORY"
BUILDS_DIRECTORY_DEFAULT = NDLAB_DIRECTORY / "builds"
BUILDS_DIRECTORY = pathlib.Path(
    os.getenv(BUILDS_DIRECTORY_ENV, BUILDS_DIRECTORY_DEFAULT),
)

QEMU_OUI = "52:54:00"


###################

LOCALHOST = "127.0.0.1"

DEFAULT_USERNAME = "admin123"
DEFAULT_PASSWORD = "admin123"

DEFAULT_USERNAME_ENV = "NDLAB_USERNAME"
DEFAULT_PASSWORD_ENV = "NDLAB_PASSWORD"

USERNAME = os.getenv(DEFAULT_USERNAME_ENV, DEFAULT_USERNAME)
PASSWORD = os.getenv(DEFAULT_PASSWORD_ENV, DEFAULT_PASSWORD)


class VirtualNetworkDevice(T.Protocol):
    NAME: str
    IMAGE_PATTERN: re.Pattern
    RAM: int

    TEMPLATE: str | None

    NIC_ADAPTER: str
    NIC_COUNT: int
    NICS_PER_BUS: int

    MGMT_PORT: bool

    WAIT_STR: bytes
    TAIL: bytes
    EXPECTS: dict[bytes, bytes]
    SAVE_WAIT: tuple[bytes, ...]

    NIC_ADDR_OFFSET: int

    qemu_port: int | None
    ethernet_ports: dict[int, int]
    console_ports: dict[int, int]

    name: str
    image: pathlib.Path | str
    base_mac: str
    build_tag: str | None
    overlay: pathlib.Path

    version: str

    console: ConsoleDumper | None

    def __call__(
        self,
        name: str,
        base_mac: str,
        image: pathlib.Path | str,
        build: bool = False,
        fake_start_date: bool = False,
        qemu_port: int | None = None,
        ethernet_ports: dict[int, int] | None = None,
        console_ports: dict[int, int] | None = None,
        *args,
        **kwargs,
    ) -> VirtualNetworkDevice:
        ...

    @classmethod
    def version_from_imagename(cls, imagename) -> str:
        ...

    @staticmethod
    def get_interface(index) -> str:
        ...

    @staticmethod
    def device_build_steps(console: ConsoleDumper) -> None:
        ...

    def dump_config(self, info: DeviceInfo) -> str:
        ...

    def debug_print(self) -> None:
        ...

    def image_extension(self) -> str:
        ...

    def image_format(self) -> str:
        ...

    def platform_specific_qemu_args(self) -> list:
        ...

    def info(self) -> dict:
        ...

    def gen_mgmt(self) -> list[str]:
        ...

    def gen_nics(self) -> list[str]:
        ...

    def gen_mac(self) -> str:
        ...

    def create_overlay_image(self) -> None:
        ...

    def get_qemu_img_cmd(self, create_directory: bool = False) -> list[str]:
        ...

    def get_qemu_cmd(self) -> list[str]:
        ...


def set_logging(debug: bool, file=None):
    global logging
    import logging.handlers

    level = logging.DEBUG if debug else logging.INFO
    BASIC_FORMAT = dict(
        fmt="{name}:{funcName}:{lineno}:{levelno}:{message}",
        style="{",
        datefmt="%Y-%m-%d %H:%M:%S",
        validate=True,
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    while root_logger.handlers:
        root_logger.handlers.pop()
    if file:
        file_handler = logging.handlers.RotatingFileHandler(
            file,
            maxBytes=MAX_SIZE,
            backupCount=1,
        )
        file_handler.setFormatter(logging.Formatter(**BASIC_FORMAT))
        file_handler.setLevel(logging.DEBUG)
        root_logger.addHandler(file_handler)
        return
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter(**BASIC_FORMAT))
    # stream_handler.setLevel(level)
    root_logger.addHandler(stream_handler)
    logging.debug("Log level set to debug")
