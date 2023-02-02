from __future__ import annotations

import logging
import re
import typing as T

import ndlab.common as common
import ndlab.device as device

if T.TYPE_CHECKING:
    from ndlab.console import ConsoleDumper

logger = logging.getLogger(__name__)


class CiscoXRV9K(device.DefaultNetworkDevice):

    NAME = "xrv9k"
    RAM = 16384
    TEMPLATE = "xrv9k.j2"
    IMAGE_PATTERN = re.compile(r"^xrv9k-full.*-x-(?P<version>.*)\.qcow2$")
    NIC_ADAPTER = "virtio-net-pci"
    MGMT_PORT = True

    TAIL = b"\n"
    EXPECTS = {
        rb"(?s).*Press RETURN to get started": b"\r",
        rb"(?s).*Not settable: Success": b"\r",
        rb"(?s).*Enter root-system username:": common.USERNAME.encode(),
        rb"(?s).*Enter secret(?: again)?:": common.PASSWORD.encode(),
        rb"(?s).*Username: ": common.USERNAME.encode(),
        rb"(?s).*Password: ": common.PASSWORD.encode(),
        rb"(?sm)^(?:(?!\\x1b\[).)*\w(?<!\(config\))(?<!ios)#\s*$": b"configure",
        rb"ios#(?:\s|$)": common.DEVICE_REQUIRES_BUILD,
        rb"(?s).*\w\(config\)#": common.DEVICE_IS_READY,
    }

    def platform_specific_qemu_args(self) -> list:
        results = []
        results.extend(
            [
                "-cpu",
                "host",
                "-smp",
                "cores=4,threads=1,sockets=1",
            ],
        )
        for i in range(1, 4):
            if not (port := self.console_ports.get(i)):
                port = self.get_available_port()
                device.set_port_index(self.console_ports, port)
            results.extend(
                [
                    "-serial",
                    f"telnet:0.0.0.0:{port},server,nowait",
                ],
            )

        return results

    def gen_mgmt(self):
        results = []
        if not self.MGMT_PORT:
            return results

        if not self.ethernet_ports.get(-1):
            self.ethernet_ports[-1] = self.get_available_port()

        if not self.ethernet_ports.get(-2):
            self.ethernet_ports[-2] = self.get_available_port()

        if not self.ethernet_ports.get(-3):
            self.ethernet_ports[-3] = self.get_available_port()

        """Generate qemu args for the mgmt interface(s)"""
        # mgmt interface
        results.extend(
            [
                "-device",
                f"virtio-net-pci,netdev=mgmt,mac={self.gen_mac()}",
                "-netdev",
                f"socket,id=mgmt,listen=:{self.ethernet_ports[-1]}",
            ],
        )
        # dummy interface for xrv9k ctrl interface
        results.extend(
            [
                "-device",
                f"virtio-net-pci,netdev=ctrl-dummy,id=ctrl-dummy,mac={self.gen_mac()}",
                "-netdev",
                f"socket,id=ctrl-dummy,listen=:{self.ethernet_ports[-2]}",
            ],
        )
        # dummy interface for xrv9k dev interface
        results.extend(
            [
                "-device",
                f"virtio-net-pci,netdev=dev-dummy,id=dev-dummy,mac={self.gen_mac()}",
                "-netdev",
                f"socket,id=dev-dummy,listen=:{self.ethernet_ports[-3]}",
            ],
        )

        return results

    @staticmethod
    def get_interface(index):
        return f"GigabitEthernet0/0/0/{index}"

    def device_build_steps(self, console: ConsoleDumper):
        """Do the actual bootstrap config"""
        logger.info("applying bootstrap configuration")
        console.write_wait(b"", wait_str=None)

        console.write_wait(b"terminal length 0")

        if not console._wait_config("show interfaces description", "Gi0/0/0/0"):
            return False

        # wait for call-home in config
        if not console._wait_config("show running-config call-home", "service active"):
            return False

        console.write_wait(b"configure")
        # configure netconf
        console.write_wait(b"hostname xrv9k")
        console.write_wait(b"lldp")
        console.write_wait(b"interface MgmtEth 0/RP0/CPU0/0")
        console.write_wait(b"no shutdown")
        for index in range(self.NIC_COUNT):
            console.write_wait(f"interface {self.get_interface(index)}".encode())
            console.write_wait(b"no shut")
            console.write_wait(b"lldp")

        console.write_wait(b"exit")

    @staticmethod
    def device_save_steps(console: ConsoleDumper) -> None:
        logger.debug(f"Sending enter")
        console.write_wait(b"")
        # buffer = console.telnet.read_until(console.wait_str, 1)
        logger.debug(f"Sending commit")
        console.write_wait(b"commit", wait_str=None)
        # todo: change this to expect
        buffer = console.telnet.read_until(b"[no]", 1)
        logger.debug(f"Commit response: {buffer=}")
        if b"commit anyway" in buffer:
            console.write_wait(b"yes")
        console.write_wait(b"end")
