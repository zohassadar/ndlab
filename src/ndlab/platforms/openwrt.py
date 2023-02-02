from __future__ import annotations

import logging
import re

import ndlab.common as common

import ndlab.device as device
import typing as T

if T.TYPE_CHECKING:
    from ndlab.console import ConsoleDumper

logger = logging.getLogger(__name__)


class OpenWRT(device.DefaultNetworkDevice):
    NAME = "openwrt"
    RAM = 2048
    IMAGE_PATTERN = re.compile(
        r"openwrt-(?P<version>.*)-x86-generic-generic-ext4-combined\.img$",
    )
    NIC_COUNT = 2
    MGMT_PORT = False
    NIC_ADAPTER = "virtio-net-pci"

    @staticmethod
    def device_save_steps(console: ConsoleDumper) -> None:
        logger.debug(f"Save steps not necessary for OpenWRT")

    @staticmethod
    def device_build_steps(console: ConsoleDumper):
        """Do the actual bootstrap config"""
        # self.logger.info("applying bootstrap configuration")
        # # Get a prompt
        # self.wait_write("\r", None)
        # # Set root password (ssh login prerequisite)
        # self.wait_write("passwd", "#")
        # self.wait_write(self.password, "New password:")
        # self.wait_write(self.password, "Retype password:")
        # # Create vrnetlab user
        # self.wait_write(
        #     "echo '%s:x:501:501:%s:/home/%s:/bin/ash' >> /etc/passwd"
        #     "echo '%s:x:501:501:%s:/home/%s:/bin/ash' >> /etc/passwd"
        #     % (self.username, self.username, self.username),
        #     "#",
        # )
        # self.wait_write("passwd %s" % (self.username))
        # self.wait_write(self.password, "New password:")
        # self.wait_write(self.password, "Retype password:")
        # # Add user to root group
        # self.wait_write("sed -i '1d' /etc/group", "#")
        # self.wait_write("sed -i '1i root:x:0:%s' /etc/group" % (self.username))
        # # Create home dir
        # self.wait_write("mkdir -p /home/%s" % (self.username))
        # self.wait_write("chown %s /home/%s" % (self.username, self.username))
        # self.logger.info("completed bootstrap configuration")
        # time.sleep(3)
        # self.installed = True
