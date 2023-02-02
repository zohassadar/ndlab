from __future__ import annotations
import logging
import re

import ndlab.common as common
import ndlab.device as device
import typing as T

if T.TYPE_CHECKING:
    from ndlab.console import ConsoleDumper


logger = logging.getLogger(__name__)


class CiscoGeneric(device.DefaultNetworkDevice):
    EXPECTS = {
        rb"(?s).*Press RETURN to get started!": b"\r",
        rb"(?s).*configuration dialog\? \[yes/no\]:.*$": b"no",
        rb"(?s).*Would you like to terminate autoinstall\? \[yes\]": b"yes",
        rb"(?s).*\w>(?:\s|$)": b"enable",
        rb"(?s).*(Router|Switch)#": common.DEVICE_REQUIRES_BUILD,
        rb"(?s).*\w(?<!\(config\))(?<!Router)(?<!Switch)#(?:\s|$)": b"configure terminal",
        rb"(?s).*\w\(config\)#": common.DEVICE_IS_READY,
    }

    @staticmethod
    def device_build_steps(console: ConsoleDumper):

        logger.debug("applying bootstrap configuration")

        console.write_wait(b"", wait_str=None)
        console.write_wait(b"enable")
        console.write_wait(b"configure terminal")

        console.write_wait(b"hostname vios")
        console.write_wait(b"lldp run")
        console.write_wait(
            f"username {console.username} privilege 15 password {console.password}".encode(),
        )
        console.write_wait(b"end")
        console.write_wait(b"write memory")
        console.write_wait(b"\r", wait_str=b"was written to disk successfully")
        console.write_wait(b"\r", wait_str=None)

    @staticmethod
    def device_save_steps(console: ConsoleDumper) -> None:
        logger.debug(f"Sending enter")
        console.write_wait(b"", wait_str=None)
        buffer = console.telnet.read_until(console.wait_str, 1)
        if b"config" in buffer:
            console.write_wait(b"end")
        console.write_wait(b"write memory", wait_str=b"[OK]")


class CiscoVIOS(CiscoGeneric):
    NAME = "iosv"
    IMAGE_PATTERN = re.compile(r"vios(?!l2)-.*\.qcow2$")
    TEMPLATE = "vios.j2"

    @staticmethod
    def get_interface(index):
        return f"GigabitEthernet0/{index}"

    @classmethod
    def version_from_imagename(cls, imagename) -> str:
        if version_search := re.search(
            rf"15\d(?:-[\da-z]+)?",
            imagename,
            flags=re.I,
        ):
            return version_search.group()
        raise RuntimeError(f"Version not found in {imagename}")


class CiscoVIOSL2(CiscoGeneric):
    NAME = "iosvl2"
    IMAGE_PATTERN = re.compile(r"viosl2-.*\.qcow2$")
    TEMPLATE = "viosl2.j2"

    @staticmethod
    def get_interface(index):
        mod = 4
        return f"GigabitEthernet{index//mod}/{index%mod}"

    @classmethod
    def version_from_imagename(cls, imagename) -> str:
        if version_search := re.search(
            rf"15\d(?:-[\da-z]+)?",
            imagename,
            flags=re.I,
        ):
            return version_search.group()
        raise RuntimeError(f"Version not found in {imagename}")
