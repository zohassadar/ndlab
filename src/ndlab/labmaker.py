from __future__ import annotations
import pathlib
import collections
import itertools
import logging
import pprint
import sys
import typing as T

import yaml


def sanitize_name(name: str) -> str:
    import re

    return re.sub(r"^[\w-\.]", "_", name)


logger = logging.getLogger(__name__)

INDEX = "index"
DEVICE = "device"
DEVICES = "devices"
BRIDGES = "bridges"
MULTIPOINT = "multipoint"


LINKS_BY_DEVICE = "links_by_device"

FULL_MESH_P2P = "full_mesh_p2p"

POINT_TO_POINT = "point_to_point"


class Device(T.TypedDict):
    name: str
    tag: str


class NICEndPoint(T.TypedDict):
    interface: str


class TAPEndPoint(T.TypedDict):
    interface: str


class TCPEndPointDict(T.TypedDict):
    device: str
    index: int


class BridgeDict(T.TypedDict):
    name: str
    tcp_endpoints: list[TCPEndPointDict]
    tap_endpoint: TAPEndPoint | None
    interface_endpoint: NICEndPoint | None


class LowLevelDict(T.TypedDict):
    devices: list[Device]
    bridges: list[BridgeDict]
    links_by_devices: dict[str, dict[int, str]]


class Topology:
    def __init__(self, high_level_data: dict):
        logger.debug(
            f"Topology received the following for parsing:\n{pprint.pformat(high_level_data)}",
        )
        self.high_level_data = high_level_data
        self.devices: list[Device] = high_level_data.get(DEVICES, [])
        self.validate_devices()
        self.bridges: list[BridgeDict] = []
        self.next_available_interface = collections.defaultdict(int)

        for device, neighbors in high_level_data.get(POINT_TO_POINT, {}).items():
            for neighbor in neighbors:
                logger.debug(f"{POINT_TO_POINT} adding {device=} {neighbor=}")
                point_to_point = self.get_new_point_to_point(device, neighbor)
                self.bridges.append(point_to_point)

        for links in high_level_data.get(FULL_MESH_P2P, []):
            for left, right in itertools.combinations(links, 2):
                logger.debug(f"Fullmesh adding {left=} {right=}")
                point_to_point = self.get_new_point_to_point(left, right)
                self.bridges.append(point_to_point)

        for hubname, devices in high_level_data.get(MULTIPOINT, {}).items():
            tcp_endpoints = []
            bridge = BridgeDict(
                name=hubname,
                tcp_endpoints=tcp_endpoints,
                tap_endpoint=None,
                interface_endpoint=None,
            )
            for device in devices:
                logger.debug(f"Hub {hubname} adding {device=}")
                tcp_endpoint = self.get_new_tcp_endpoint(device)
                bridge["tcp_endpoints"].append(tcp_endpoint)
            self.bridges.append(bridge)

        device_links = collections.defaultdict(dict)
        for bridge in self.bridges:
            for tcp_endpoint in bridge["tcp_endpoints"]:
                device_links[tcp_endpoint["device"]][tcp_endpoint["index"]] = bridge[
                    "name"
                ]

        self.links_by_device: dict[str, dict[int, str]] = {
            k: dict(v) for k, v in device_links.items()
        }

        self.low_level = LowLevelDict(
            devices=self.devices,
            bridges=self.bridges,
            links_by_devices=self.links_by_device,
        )

    @classmethod
    def from_yaml(cls, filename: str | pathlib.Path) -> Topology:
        with open(filename, "r+") as file:
            data = yaml.safe_load(file)
        return cls(high_level_data=data)

    def validate_devices(self):
        for device in [dict(d) for d in self.devices]:
            for key in Device.__required_keys__:
                if not device.pop(key, None):
                    raise RuntimeError(f"Missing key {key}")
            if device:
                raise RuntimeError(f"Invalid device key(s): {','.join(device)}")
        self.devices = [Device(**d) for d in self.devices]

    def get_new_point_to_point(self, device_a: str, device_b: str) -> BridgeDict:
        _device_a = self.get_new_tcp_endpoint(device_a)
        _device_b = self.get_new_tcp_endpoint(device_b)
        name = f"{device_a}_{_device_a['index']}-" f"-{device_b}_{_device_b['index']}"
        return BridgeDict(
            name=name,
            tcp_endpoints=[_device_a, _device_b],
            tap_endpoint=None,
            interface_endpoint=None,
        )

    def get_new_tcp_endpoint(self, device: str) -> TCPEndPointDict:
        index = self.get_next_available_interface(device)
        return TCPEndPointDict(device=device, index=index)

    def get_next_available_interface(self, device: str) -> int:
        for _device in self.devices:
            if device == _device["name"]:
                break
        else:
            raise RuntimeError(f"The device {device!r} not found in topology")
        index = self.next_available_interface.setdefault(device, 0)
        self.next_available_interface[device] = index + 1
        logger.debug(f"Device {device} allocated interface {index}")
        return index


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    high_level = yaml.safe_load(open(str(sys.argv[1])))
    print(yaml.safe_dump(Topology(high_level).low_level, sort_keys=False))
