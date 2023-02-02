from __future__ import annotations
import logging
import re

import ndlab.common as common
import ndlab.device as device

import typing as T

if T.TYPE_CHECKING:
    from ndlab.console import ConsoleDumper

logger = logging.getLogger(__name__)


class MikrotikRouterOS(device.DefaultNetworkDevice):
    TEMPLATE = "routeros.j2"
    NAME = "chr"
    RAM = 2048
    IMAGE_PATTERN = re.compile(r"^chr-(?P<version>.*)\.vmdk$")

    WAIT_STR = b">"
    EXPECTS = {
        # rb"(?s).*Login failed, incorrect username or password": common.DEVICE_REQUIRES_BUILD,
        rb"(?s).*Login: ": common.DEVICE_REQUIRES_BUILD,
        # rb"(?s).*Login: ": f"{common.USERNAME}+ct".encode(),
        # rb"(?s).*Password: ": common.PASSWORD.encode(),
        rb"> ": common.DEVICE_IS_READY,
    }

    @staticmethod
    def get_interface(index):
        return f"ether{index+1}"

    def platform_specific_qemu_args(self) -> list:
        return ["-boot", "n"]

    @staticmethod
    def device_save_steps(console: ConsoleDumper) -> None:
        logger.debug(f"Save steps not necessary for RouterOS")

    @staticmethod
    def device_build_steps(console: ConsoleDumper):
        logger.debug(f"Sending mikrotik build steps")
        console.knock()
        attempt_limit = 15
        attempts = 0
        while True:
            buffer = console.telnet.read_very_eager()
            if not buffer and attempts < attempt_limit:
                logger.debug(f"Waiting and sleeping")
                import time

                time.sleep(1)
                attempts += 1
            elif not buffer:
                raise RuntimeError("Did not receive anything from device")

            logger.debug(f"Received raw buffer: {buffer!r}")

            if buffer.decode().strip().endswith("Login:"):
                break

        console.write_wait(f"{common.USERNAME}+ct".encode(), wait_str=b"Password:")
        console.write_wait(common.PASSWORD.encode(), wait_str=None)
        index, match, buffer = console.telnet.expect([b"Login:", b"> "], 5)
        if match and index == 0:
            console.write_wait(b"admin+ct", wait_str=b"Password:")
            console.write_wait(b"", wait_str=None)
        while True:
            index, match, buffer = console.telnet.expect(
                [
                    rb"Do you want to see the software license\? \[Y\/n\]: ",
                    rb"(?:repeat )?new password>",
                    rb" >",
                ],
                10,
            )
            if not match:
                raise RuntimeError(
                    f"Unexpected timeout with mikrotik config.  Buffer contained {buffer!r}",
                )
            if index == 0:
                logger.debug(f"No we don't wanna see the license: {match!r}")
                console.write_wait(b"n", wait_str=None)
            if index == 1:
                logger.debug(f"Setting new password {match!r}")
                console.write_wait(common.PASSWORD.encode(), wait_str=None)
            if index == 2:
                logger.debug(f"Ready: {match!r}")
                console.write_wait(
                    f'/user add name={console.username} password="{console.password}" group=full'.encode(),
                )
                break
