from __future__ import annotations
import logging
import re

import ndlab.common as common
import ndlab.device as device
import typing as T

if T.TYPE_CHECKING:
    from ndlab.console import ConsoleDumper

logger = logging.getLogger(__name__)


class CiscoCSR(device.DefaultNetworkDevice):
    NAME = "csr"
    TEMPLATE = "csr.j2"
    IMAGE_PATTERN = re.compile(r"^csr1000v-universalk9\.(?P<version>.*)-serial\.qcow2$")
    NIC_ADAPTER = "virtio-net-pci"

    EXPECTS = {
        rb"(?s).*Press RETURN to get started!.*": b"\r",
        rb"(?s).*configuration dialog\? \[yes/no\]:.*$": b"no",
        rb"(?s).*Would you like to terminate autoinstall\? \[yes\].*": b"yes",
        rb"(?s).*\w>(?:\s|$)": b"enable",
        rb"(?s).*(Router|Switch)#": common.DEVICE_REQUIRES_BUILD,
        rb"(?s).*\w(?<!\(config\))(?<!Router)(?<!Switch)#(?:\s|$)": b"configure terminal",
        rb"(?s).*\w\(config\)#": common.DEVICE_IS_READY,
    }

    @staticmethod
    def get_interface(index):
        return f"GigabitEthernet{index + 1}"

    def device_build_steps(self, console: ConsoleDumper):

        logger.debug("Beginning device build steps")
        console.write_wait(b"configure terminal")
        console.write_wait(b"hostname csr")
        console.write_wait(b"lldp run")
        console.write_wait(
            f"username {common.USERNAME} privilege 15 password {common.PASSWORD}".encode()
        )
        for index in range(self.NIC_COUNT):
            console.write_wait(f"interface {self.get_interface(index)}".encode())
            console.write_wait(b"no shut")
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
