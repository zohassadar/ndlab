import dataclasses
import logging
import pathlib

import ndlab
import ndlab.common as common
import ndlab.images as images
import pytest
import yaml

logger = logging.getLogger(__name__)


TEST_DATA = [
    {
        "filename": "chr-6.48.6.vmdk",
        "format": "vmdk",
        "name": "chr",
        "platform": "MikrotikRouterOS",
        "version": "6.48.6",
    },
    {
        "filename": "chr-7.6.vmdk",
        "format": "vmdk",
        "name": "chr",
        "platform": "MikrotikRouterOS",
        "version": "7.6",
    },
    {
        "filename": "csr1000v-universalk9.17.03.05-serial.qcow2",
        "format": "qcow2",
        "name": "csr",
        "platform": "CiscoCSR",
        "version": "17.03.05",
    },
    {
        "filename": "csr1000v-universalk9.17.03.06-serial.qcow2",
        "format": "qcow2",
        "name": "csr",
        "platform": "CiscoCSR",
        "version": "17.03.06",
    },
    {
        "filename": "openwrt-21.02.5-x86-generic-generic-ext4-combined.img",
        "format": "raw",
        "name": "openwrt",
        "platform": "OpenWRT",
        "version": "21.02.5",
    },
    {
        "filename": "openwrt-22.03.2-x86-generic-generic-ext4-combined.img",
        "format": "raw",
        "name": "openwrt",
        "platform": "OpenWRT",
        "version": "22.03.2",
    },
    {
        "filename": "vEOS-lab-4.28.5M.vmdk",
        "format": "vmdk",
        "name": "veos",
        "platform": "AristaVEOS",
        "version": "4.28.5M",
    },
    {
        "filename": "vEOS-lab-4.29.1F.vmdk",
        "format": "vmdk",
        "name": "veos",
        "platform": "AristaVEOS",
        "version": "4.29.1F",
    },
    {
        "filename": "vios-adventerprisek9-m.SPA.154-3M8.qcow2",
        "format": "qcow2",
        "name": "iosv",
        "platform": "CiscoVIOS",
        "version": "154-3M8",
    },
    {
        "filename": "viosl2-adventerpriseK9-M_152_May_2018.qcow2",
        "format": "qcow2",
        "name": "iosvl2",
        "platform": "CiscoVIOS",
        "version": "152",
    },
    {
        "filename": "xrv9k-fullk9-x-7.4.2.qcow2",
        "format": "qcow2",
        "name": "xrv9k",
        "platform": "CiscoXRV9K",
        "version": "7.4.2",
    },
    {
        "filename": "xrv9k-fullk9-x-7.5.2.qcow2",
        "format": "qcow2",
        "name": "xrv9k",
        "platform": "CiscoXRV9K",
        "version": "7.5.2",
    },
]


@pytest.mark.parametrize(
    "filename,name",
    [(td["filename"], td["name"]) for td in TEST_DATA],
)
def test_name(filename, name):
    assert images.search_platform_patterns(filename) == name


@pytest.mark.parametrize(
    "filename,version",
    [(td["filename"], td["version"]) for td in TEST_DATA],
)
def test_version(filename, version):
    device = images.get_device_by_imagename(filename)
    assert device.version_from_imagename(filename) == version


@pytest.mark.parametrize(
    "filename,format",
    [(td["filename"], td["format"]) for td in TEST_DATA],
)
def test_format(filename, format):
    device = images.get_device_by_imagename(filename)
    assert (
        device(
            name="test",
            image=filename,
            base_mac="00:00:00:00:00:00",
            build_tag=None,
        ).image_format()
        == format
    )
