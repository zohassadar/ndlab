from __future__ import annotations

import contextlib
import datetime
import logging
import math
import os
import pathlib
import re
import socket
import typing as T

import ndlab.common as common
import ndlab.console as console

if T.TYPE_CHECKING:
    from ndlab.console import ConsoleDumper
    from ndlab.config import DeviceInfo


logger = logging.getLogger(__name__)


def get_template_by_name(name):
    import jinja2

    logger.debug(f"Attempting to load {name}")
    loader = jinja2.PackageLoader("ndlab.platforms")
    environment = jinja2.Environment(loader=loader)
    return environment.get_template(name)


def set_port_index(ports: dict[int, int], port: int):
    highest_index = max(ports) if ports else -1
    ports[highest_index + 1] = port


VALIDATE_BASE_MAC = re.compile(r"^(?:[\da-f]{2}:){5}00$", re.I)
COLON = ":"


class DefaultNetworkDevice:
    NAME: str = "default"
    IMAGE_PATTERN: re.Pattern = re.compile(r".*\.qcow2$")
    RAM: int = 4096
    TEMPLATE: str | None = None

    NIC_ADAPTER: str = "e1000"
    NIC_COUNT = 10
    NICS_PER_BUS = 26

    MGMT_PORT: bool = False

    WAIT_STR: bytes = b"#"
    TAIL: bytes = b"\r\n"
    EXPECTS: dict[bytes, bytes] = {}
    SAVE_WAIT: tuple[bytes, ...] | None = None

    NIC_ADDR_OFFSET: int = 0

    @classmethod
    def version_from_imagename(cls, imagename: str) -> str:
        if version := cls.IMAGE_PATTERN.match(imagename):
            return version.group("version")
        raise RuntimeError(f"Version not found in {imagename}")

    def __str__(self):
        return self.__class__.__name__

    def __init__(
        self,
        name: str,
        base_mac: str,
        image: pathlib.Path | str,
        build_tag: str | None = None,
        fake_start_date: bool = False,
        qemu_port: int | None = None,
        ethernet_ports: dict[int, int] | None = None,
        console_ports: dict[int, int] | None = None,
        *args,
        **kwargs,
    ):
        self.name = name
        self.base_mac = base_mac
        self.image = pathlib.Path(image).absolute()
        self.build_tag = build_tag

        self.fake_start_date = fake_start_date

        self.qemu_port: int | None = qemu_port
        logger.debug(f"{ethernet_ports=}")
        self.ethernet_ports = ethernet_ports or {}

        self.console_ports = console_ports or {}
        self.console_port = self.console_ports.get(0)

        if self.build_tag:
            self.overlay = (
                common.BUILDS_DIRECTORY / self.build_tag / self.image.name
            ).absolute()
        else:
            self.overlay = (
                common.LABS_DIRECTORY / self.name / self.image.name
            ).absolute()
        logger.debug(f"Overlay set to {self.overlay}")
        self.hash = hash(self.name)

        if not VALIDATE_BASE_MAC.search(self.base_mac):
            raise RuntimeError(f"Invalid base mac: {self.base_mac}")

        self._base_mac = self.base_mac.split(COLON)[:-1]
        self.start_time = datetime.datetime.now()
        self.next_mac = iter(range(255))

        self.boot_image: pathlib.Path | None = None
        self.version = self.version_from_imagename(self.image.name)
        if self.console_port:
            self.establish_console()

        logger.debug(f"{self.get_qemu_img_cmd()=}")

    def establish_console(self):
        logger.debug(f"Establishing console object")
        if not self.console_port:
            raise RuntimeError(f"Unable to establish console without port set")
        args = dict(
            port=self.console_port,
            hostname=common.LOCALHOST,
            username=common.USERNAME,
            password=common.PASSWORD,
            wait_str=self.WAIT_STR,
            tail=self.TAIL,
            expects=self.EXPECTS,
            save_wait=self.SAVE_WAIT,
            device_build_steps=self.device_build_steps,
            device_save_steps=self.device_save_steps,
        )
        logger.debug(f"Calling {console.ConsoleDumper.__name__} with {args!r}")
        self.console = console.ConsoleDumper(**args)  # type: ignore

    def debug_print(self):
        import pprint

        pprint.pprint(self.__dict__)

    def __hash__(self):
        return self.hash

    def __eq__(self, other):
        return self.hash == other.hash

    def get_qemu_cmd(self):
        self.set_qemu_cmd()
        return self.qemu_cmd

    def set_qemu_cmd(self):

        if self.MGMT_PORT and not self.ethernet_ports.get(-1):
            self.ethernet_ports[-1] = self.get_available_port()

        if not self.qemu_port:
            self.qemu_port = self.get_available_port()

        if not self.console_port:
            self.console_port = self.get_available_port()
            set_port_index(self.console_ports, self.console_port)
        self.establish_console()

        self.qemu_cmd = ["qemu-system-x86_64"]

        if os.path.exists("/dev/kvm"):
            self.qemu_cmd.append("-enable-kvm")

        self.qemu_cmd.extend(
            [
                "-display",
                "none",
                "-machine",
                "pc",
                "-monitor",
                f"tcp:0.0.0.0:{self.qemu_port},server,nowait",
                "-m",
                str(self.RAM),
                "-serial",
                f"telnet:0.0.0.0:{self.console_port},server,nowait",
                "-drive",
                f"if=ide,file={self.overlay.absolute()}",
            ],
        )
        if self.fake_start_date:
            self.qemu_cmd.extend(["-rtc", "base=" + str(self.fake_start_date)])

        # setup PCI buses
        for index in range(1, math.ceil(self.NIC_COUNT / self.NICS_PER_BUS) + 1):
            self.qemu_cmd.extend(
                [
                    "-device",
                    f"pci-bridge,chassis_nr={index},id=pci.{index}",
                ],
            )
        self.qemu_cmd.extend(self.gen_mgmt())

        self.qemu_cmd.extend(self.gen_nics())
        self.qemu_cmd.extend(self.platform_specific_qemu_args())

        logger.debug(f'Qemu command: {" ".join(self.qemu_cmd)}')

    def get_available_port(self) -> int:
        return common.get_free_port()

    def platform_specific_qemu_args(self) -> list:
        logger.debug(f"Generic platform specific qemu args.  nothing defined here")
        return []

    def get_mgmt_card_info(self):
        logger.debug(f"Generating mgmt card info")
        results = [
            f"{self.NIC_ADAPTER}",
            f"netdev=p00",
            f"mac={self.gen_mac()}",
        ]
        logger.debug(f"Management Card Info: {' '.join(results)!r}")
        return results

    def gen_mgmt(self):
        logger.debug(f"Generating management port portion")
        if not self.MGMT_PORT:
            logger.info(f"Skipping generation of mgmt for {type(self).__name__}")
            return list()
        """Generate qemu args for the mgmt interface(s)"""
        results = ["-device"]
        # mgmt interface is special - we use qemu user mode network

        # vEOS-lab requires its Ma1 interface to be the first in the bus, so let's hardcode it

        results.append(",".join(self.get_mgmt_card_info()))
        results.extend(
            [
                "-netdev",
                f"socket,id=p00,listen=:{self.ethernet_ports[-1]}",
            ],
        )
        logger.debug(f"Management: {' '.join(results)!r}")
        return results

    def gen_nics(self):
        """Generate qemu args for the normal traffic carrying interface(s)"""
        results = []

        for i in range(1, self.NIC_COUNT + 1):
            port_id = i
            # calc which PCI bus we are on and the local add on that PCI bus
            pci_bus = (port_id // self.NICS_PER_BUS) + 1
            address = (port_id % self.NICS_PER_BUS) + 1 + self.NIC_ADDR_OFFSET
            if not (port := self.ethernet_ports.get(i - 1)):
                port = self.get_available_port()
                set_port_index(self.ethernet_ports, port)
            results.extend(
                [
                    "-device",
                    ",".join(
                        [
                            f"{self.NIC_ADAPTER}",
                            f"netdev=p{port_id:02d}",
                            f"mac={self.gen_mac()}",
                            f"bus=pci.{pci_bus}",
                            f"addr=0x{address:x}",
                        ],
                    ),
                    "-netdev",
                    ",".join(
                        [
                            f"socket,id=p{port_id:02d}",
                            f"listen=:{port}",
                        ],
                    ),
                ],
            )
        return results

    def gen_mac(self):
        return COLON.join(self._base_mac + [f"{next(self.next_mac):02x}"]).upper()

    def image_extension(self) -> str:
        return "".join(self.image.name.split(".")[-1:])

    def image_format(self) -> str:
        format = "raw"
        if self.image_extension() in ("vmdk", "qcow2"):
            format = self.image_extension()
        return format

    def get_qemu_img_cmd(self, create_directory: bool = False):
        if not self.image.exists() and create_directory:
            raise RuntimeError(f"Base image {self.image} does not exist")
        if self.overlay.exists() and create_directory:
            logger.debug("overlay image exists")
            return
        if create_directory:
            parent = pathlib.Path(self.overlay).parent
            logger.debug(f"Creating directory: {parent}")
            parent.mkdir(exist_ok=True, parents=True)
        image = self.image.absolute()
        overlay = self.overlay.absolute()
        result = [
            "qemu-img",
            "create",
            "-f",
            self.image_format(),
            "-F",
            self.image_format(),
            "-b",
            str(image),
            str(overlay),
        ]

        return result

    @staticmethod
    def get_interface(index) -> str:
        raise RuntimeError("No interface defined")

    @staticmethod
    def device_build_steps(console: ConsoleDumper) -> None:
        raise RuntimeError("Build steps should not be called")

    @staticmethod
    def device_save_steps(console: ConsoleDumper) -> None:
        raise RuntimeError("Save steps not configured for base device")

    def dump_config(self, info: DeviceInfo) -> str:
        template = get_template_by_name(self.TEMPLATE)
        return template.render(info=info, get_interface=self.get_interface)
