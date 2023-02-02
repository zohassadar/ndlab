from __future__ import annotations

import logging
import pathlib

import ndlab.common as common

logger = logging.getLogger(__name__)

SEPARATOR = "_"

from ndlab.device import DefaultNetworkDevice
from ndlab.platforms.csr import CiscoCSR
from ndlab.platforms.eos import AristaVEOS
from ndlab.platforms.iosv import CiscoVIOS, CiscoVIOSL2
from ndlab.platforms.openwrt import OpenWRT
from ndlab.platforms.routeros import MikrotikRouterOS
from ndlab.platforms.xrv9k import CiscoXRV9K

PLATFORMS: list[common.VirtualNetworkDevice] = [
    CiscoCSR,
    AristaVEOS,
    CiscoVIOS,
    CiscoVIOSL2,
    OpenWRT,
    MikrotikRouterOS,
    CiscoXRV9K,
    DefaultNetworkDevice,
]  # type: ignore

PLATFORM_MAPPING = {P.NAME: P for P in PLATFORMS}


def get_build_tag(base_tag: str, build_tag: str) -> str:
    return f"{base_tag}{SEPARATOR}{build_tag}"


def get_name_version_build_tag(tag: str) -> tuple[str, str, str]:
    import re

    if result := re.search(
        rf"([^{SEPARATOR}]+){SEPARATOR}([^{SEPARATOR}]+)(?:{SEPARATOR}([^{SEPARATOR}]+))?",
        tag,
    ):
        return result.groups()
    raise RuntimeError(f"Unable to extract tag info from {tag}")


def get_device_by_imagename(filename) -> common.VirtualNetworkDevice:
    logger.info(f"Looking for the class for {filename}")
    filename = pathlib.Path(filename).name
    if not (platform := search_platform_patterns(filename)):
        raise RuntimeError(f"No platforms identified: {filename}")
    return PLATFORM_MAPPING[platform]


def search_platform_patterns(filename) -> str | None:
    logger.info(f"Looking for the platform name for {filename}")
    for platform in PLATFORMS:
        logger.debug(f"Evalulating {platform.NAME} ({type(platform).__name__})")
        if platform.IMAGE_PATTERN.search(filename):
            logger.info(f"Found {platform.NAME}")
            return platform.NAME


def find_images_in_directory(directory: pathlib.Path | str = common.IMAGES_DIRECTORY):
    images = {}
    directory = pathlib.Path(directory)
    for filename in directory.iterdir():
        if platform := search_platform_patterns(filename.name):
            images[filename.name] = platform
    return images


def auto_discover_tags(
    images_directory: pathlib.Path | str = common.IMAGES_DIRECTORY,
    builds_directory: pathlib.Path | str = common.BUILDS_DIRECTORY,
):
    import re
    import collections

    logger.info(f"Searching for images/tags in {images_directory}")

    get_numbers = re.compile(r"\d+").findall
    images = {}
    images_directory = pathlib.Path(images_directory)
    builds_directory = pathlib.Path(builds_directory)
    for filename in images_directory.iterdir():
        logger.debug(f"Evaluating: {filename}")
        if not (platform := search_platform_patterns(filename.name)):
            logger.debug(f"Image {filename.name} does not match any pattern")
            continue
        logger.debug(f"Searching for version in: {filename.name}")
        version = PLATFORM_MAPPING[platform].version_from_imagename(
            filename.name,
        )
        tag = f"{platform}{SEPARATOR}{version}"
        # tags_per_platform[platform].append(tag)
        images[tag] = filename.absolute()
        logger.info(f"Found tag: {tag} for image {filename.name}")

    for build_tag_dir in builds_directory.iterdir():
        build_tag = build_tag_dir.name
        if not build_tag_dir.is_dir():
            continue
        for filename in build_tag_dir.iterdir():
            if not (platform := search_platform_patterns(filename.name)):
                logger.debug(
                    f"Build Image {build_tag}/{filename.name} does not match any pattern",
                )
                continue
            version = PLATFORM_MAPPING[platform].version_from_imagename(
                filename.name,
            )
            tag = f"{platform}{SEPARATOR}{version}{SEPARATOR}{build_tag}"
            images[tag] = filename.absolute()
            logger.info(f"Found tag: {tag} for image {filename.name}")

    return dict(sorted(list(images.items()), key=lambda kv: kv[0]))
