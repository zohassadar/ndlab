from __future__ import annotations
import dataclasses
import ipaddress
import logging
import pprint
import typing as T

import ndlab

if T.TYPE_CHECKING:
    from ndlab.labmaker import Topology


logger = logging.getLogger(__name__)


LIMIT = 6
LOOP_NETWORKS = "10.0.0.0/16"
NETWORKS = "10.1.0.0/16"
NETWORK_LENGTH = 24

READY = object()


@dataclasses.dataclass
class InterfaceInfo:
    interface: int
    bridge: str
    ipaddress: ipaddress.IPv4Interface


@dataclasses.dataclass
class DeviceInfo:
    hostname: str
    loopback: str
    interfaces: list[InterfaceInfo]


class ConfigInformation:
    def __init__(
        self,
        topology: Topology,
        loopback_networks: str = LOOP_NETWORKS,
        networks: str = NETWORKS,
        length: int = NETWORK_LENGTH,
    ):
        self.topology = topology
        self.networks = networks
        self.loopback_networks = loopback_networks
        self.length = length
        self._indexes = iter(range(999))
        self._networks = ipaddress.IPv4Network(networks).subnets(new_prefix=length)
        self._loops = ipaddress.IPv4Network(loopback_networks).hosts()
        self._assigned_nets = {}

    def get_template_info(self) -> dict[str, DeviceInfo]:
        template_info = {}
        # for device
        for device in self.topology.devices:
            name = device["name"]
            interfaces = []
            device_info = DeviceInfo(
                hostname=name,
                loopback=self._get_loop(),
                interfaces=interfaces,
            )
            template_info[name] = device_info
            for index, bridge in self.topology.links_by_device.get(name, {}).items():
                interface = InterfaceInfo(
                    interface=index,
                    bridge=bridge,
                    ipaddress=self._get_ip_address_for_bridge(bridge),
                )
                interfaces.append(interface)

        return template_info

    def _get_index(self):
        return next(self._indexes)

    def _get_loop(self):
        return str(next(self._loops))

    def _get_ip_address_for_bridge(self, bridge) -> ipaddress.IPv4Interface:
        logger.debug(f"Requesting an IP for {bridge}")
        if not (network := self._assigned_nets.get(bridge)):
            network = next(self._networks)
            self._assigned_nets[bridge] = network.hosts()
            logger.debug(f"New network {network!s} chosen for {bridge}")
        else:
            logger.debug(f"Existing network chosen for {bridge}")

        ip_address = next(self._assigned_nets[bridge])
        logger.debug(f"Retrieved {ip_address}")
        interface_str = f"{ip_address!s}/{NETWORK_LENGTH}"
        logger.debug(f"Converting to {interface_str}")
        return ipaddress.IPv4Interface(interface_str)


if __name__ == "__main__":
    import sys

    import yaml

    import ndlab.labmaker

    logging.basicConfig(level=logging.DEBUG)
    high_level = yaml.safe_load(open(str(sys.argv[1])))
    topo = ndlab.labmaker.Topology(high_level)
    import pprint

    pprint.pprint(ConfigInformation(topo).get_template_info())
