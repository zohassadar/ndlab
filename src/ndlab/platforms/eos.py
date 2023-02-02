from __future__ import annotations
import logging
import re

import ndlab.common as common
import ndlab.device as device
import typing as T

if T.TYPE_CHECKING:
    from ndlab.console import ConsoleDumper

logger = logging.getLogger(__name__)

ZERO_TOUCH_MESSAGE = b"zerotouch disable"


class AristaVEOS(device.DefaultNetworkDevice):
    NAME = "veos"
    TEMPLATE = "veos.j2"
    RAM = 2048
    IMAGE_PATTERN = re.compile(r"vEOS-lab-(?P<version>.*)\.vmdk$")
    BOOT_IMAGE_PATTERN = re.compile(r"Aboot-veos-serial-8.0.[01].iso")
    MGMT_PORT = True
    NIC_ADDR_OFFSET = 1
    EXPECTS = {
        rb"(?s)(?:(?!zerotouch).)*login:": common.USERNAME.encode(),
        rb"(?s).*Password: ": common.PASSWORD.encode(),
        rb"(?s).*\w>(?:\s|$)": b"enable",
        rb"(?s).*\w(?<!\(config\))#(?:\s|$)": b"configure",
        ZERO_TOUCH_MESSAGE: common.DEVICE_REQUIRES_BUILD,
        rb"(?s).*Login incorrect": common.DEVICE_REQUIRES_BUILD,
        rb"(?s).*\w\(config\)#": common.DEVICE_IS_READY,
    }

    def get_mgmt_card_info(self):
        mgmt_card = super().get_mgmt_card_info()
        mgmt_card.append("bus=pci.1,addr=0x2")
        return mgmt_card

    def get_qemu_cmd(self):
        if not self.boot_image:
            for image in self.image.parent.iterdir():
                if self.BOOT_IMAGE_PATTERN.match(image.name):
                    logger.debug(f"Found aboot file: {image.name}")
                    self.boot_image = image
                    break
            else:
                raise RuntimeError(
                    f"Unable to find aboot file using pattern: {self.BOOT_IMAGE_PATTERN} in {self.image.parent}",
                )
        return super().get_qemu_cmd()

    def platform_specific_qemu_args(self) -> list:
        return ["-cdrom", str(self.boot_image.absolute()), "-boot", "d"]  # type: ignore

    @staticmethod
    def get_interface(index):
        return f"Ethernet{index+1}"

    def zero_touch_reboot(self, console: ConsoleDumper):
        console.write_wait(b"zerotouch disable")
        logger.info("Waiting for reboot after zerotouch")
        ready = b"login:"
        while True:
            console.knock()
            buffer = console.telnet.read_until(ready, 5)
            if ready in buffer:
                logger.info(f"Zerotouch reboot complete")
                break
            logger.debug(f"Waiting for reboot to finish.  Received: {buffer!r}")
        logger.info("Zerotouch reboot complete")
        console.write_wait(b"admin", wait_str=b">")
        console.write_wait(b"enable")

    def device_build_steps(self, console: ConsoleDumper):
        """Do the actual bootstrap config"""
        logger.info("applying bootstrap configuration")
        logger.debug(f"Sending arista eos build steps")
        console.knock()
        while True:
            buffer = console.telnet.read_until(b"asdfasdfasdf", timeout=1)
            logger.debug(f"Received buffer {buffer=}")
            if b"login:" in buffer and b"Password:" not in buffer:
                break

        console.write_wait(b"admin", wait_str=b">")
        console.write_wait(b"enable")
        if ZERO_TOUCH_MESSAGE in buffer:
            logger.debug(f"Zerotouch evidence!: {buffer!r}")
            console.write_wait(b"admin", wait_str=None)
            self.zero_touch_reboot(console)

        console.write_wait(b"configure")
        console.write_wait(b"hostname veos")
        console.write_wait(
            f"username {console.username} secret 0 {console.password} role network-admin".encode(),
        )
        console.write_wait(b"exit")
        console.write_wait(b"copy running-config startup-config")
        # Sending nothing but waiting for above to be complete
        console.write_wait(b"!")
        console.write_wait(b"!")
        console.write_wait(b"!")

    @staticmethod
    def device_save_steps(console: ConsoleDumper) -> None:
        logger.debug(f"Sending enter")
        console.write_wait(b"", wait_str=None)
        buffer = console.telnet.read_until(console.wait_str, 1)
        if b"config" in buffer:
            console.write_wait(b"end")
        console.write_wait(b"copy run start")
