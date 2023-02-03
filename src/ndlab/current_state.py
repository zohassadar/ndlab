from __future__ import annotations

import contextlib
import dataclasses
import logging
import pathlib
import re
import typing as T

import ndlab.common as common
import ndlab.images as images

logger = logging.getLogger(__name__)


DEVICE_INTERFACE_SEPARATOR = "/"
DEVICE_INTERFACE = re.compile(rf"\w[-\w]*{DEVICE_INTERFACE_SEPARATOR}\d+", re.I)
DEVICE_NAME_VALIDATE = re.compile(r"\w[-\w]*")
RAND_MAC_ATTEMPTS = 20


validate_oui = re.compile(r"[\da-f]{2}:[\da-f]{2}:[\da-f]{2}", re.I).search


class NDLabStateException(Exception):
    pass


class TagOutput(T.TypedDict):
    tag: str
    image: str


class DeviceOutput(T.TypedDict):
    name: str
    console_port: int | None
    qemu_port: int | None
    state: str


class TCPEndpointOutput(T.TypedDict):
    bridge: str
    state: str
    device: str
    index: int
    port: int | None


class TapEndpointOutput(T.TypedDict):
    bridge: str
    state: str
    interface: str


class NICEndpointOutput(T.TypedDict):
    bridge: str
    state: str
    interface: str


@dataclasses.dataclass
class InterfaceState:
    """
    Represents a device interface.

    tcp_port is set when device is started

    Connection is set when associated with a connection
    """

    tcp_port: int | None = None
    connection: str | None = None


@dataclasses.dataclass
class DeviceState:
    type: str
    image: str
    overlay: str
    build_tag: str | None
    base_mac_address: str
    console_ports: dict[int, int]
    interfaces: dict[int, InterfaceState]
    qemu_port: int | None = None
    pid: int | None = None


@dataclasses.dataclass
class TapEndpoint:
    interface: str


@dataclasses.dataclass
class TCPConnectionEndpoint:
    host: str
    port: int


@dataclasses.dataclass
class PhysicalConnectionEndpoint:
    interface: str


@dataclasses.dataclass
class ConnectionState:
    name: str
    sniffer_port: int | None = None
    pid: int | None = None


@dataclasses.dataclass
class State:
    devices: dict[str, DeviceState] = dataclasses.field(default_factory=dict)
    bridges: dict[str, ConnectionState] = dataclasses.field(default_factory=dict)
    tap_endpoints: dict[str, TapEndpoint] = dataclasses.field(
        default_factory=dict,
    )
    phyical_endpoints: dict[str, PhysicalConnectionEndpoint] = dataclasses.field(
        default_factory=dict,
    )

    tags: dict[str, str] = dataclasses.field(default_factory=dict)

    def __post_init__(self):
        logger.debug(f"State initialized")
        self.filename = None

    def get_base_tags(self) -> list[str]:
        base_tags = []
        for tag in self.tags:
            _, _, build = images.get_name_version_build_tag(tag)
            if not build:
                base_tags.append(tag)
        return base_tags

    def get_active_build_tags(self) -> list[str]:
        logger.debug(f"Retrieving build tags for active build devices")
        tags = []
        for device_name, device in self.devices.items():
            logger.debug(f"Evaluating {device!r}")
            if device.build_tag:
                tags.append(device_name)
        return tags

    @property
    def used_mac_addresses(self) -> list[str]:
        result = [d.base_mac_address.lower() for d in self.devices.values()]
        logger.debug(f"Used mac addresses: {result!r}")
        return result

    def asdict(self) -> dict:
        return dataclasses.asdict(self)

    def _error_raise(self, msg):
        import sys

        logger.critical(f"exit condition: msg")
        print(msg, file=sys.stderr)
        raise NDLabStateException(msg)

    def _split_device_interface_index(self, endpoint) -> tuple[str, int]:
        try:
            device_name, index = endpoint.split(DEVICE_INTERFACE_SEPARATOR)
            index = int(index)
            return device_name, index

        except Exception as exc:
            self._error_raise(f"Invalid device and interface index: {endpoint}")

    def _validate_nic(self, physical_nic):
        import psutil

        if not psutil.net_if_addrs():
            self._error_raise(f"Invalid NIC: {physical_nic}")

    def _validate_tcp_endpoints(self, tcp_endpoints: list[str]) -> None:
        for tcp_endpoint in tcp_endpoints:
            logger.debug(
                f"Evaluating {tcp_endpoint} for validity against {DEVICE_INTERFACE.pattern!r}",
            )
            if not DEVICE_INTERFACE.match(tcp_endpoint):
                self._error_raise(
                    f"Invalid input.  Format is device{DEVICE_INTERFACE_SEPARATOR}index",
                )
            device_name, index = self._split_device_interface_index(tcp_endpoint)
            index = int(index)
            if not self.devices.get(device_name):
                self._error_raise(f"No device named {device_name}")
            if not self.devices[device_name].interfaces.get(index):
                self._error_raise(f"Index {index} is invalid for {device_name}")
            if self.devices[device_name].interfaces[index].connection:
                self._error_raise(
                    f"{device_name}{DEVICE_INTERFACE_SEPARATOR}{index} is already in use",
                )
            logger.debug(f"{tcp_endpoint} is valid")

    def _stop_pid(self, pid: int | None) -> None:
        import os
        import signal
        import psutil

        if pid is None:
            logger.debug(f"Cannot stop None")
            return
        if not pid:
            logger.debug(f"Not killing ourselves")
            return
        if not psutil.pid_exists(pid):
            logger.debug(f"{pid} not running.  Cannot kill")
            return
        try:
            logger.debug(f"Attempting to kill {pid}")
            os.kill(pid, signal.SIGINT)
        except:
            logger.error(f"Unable to kill {pid}", exc_info=True)

    def _is_pid_running(self, pid: int) -> bool:
        import psutil

        logger.debug(f"Checking for existance of {pid}")
        return psutil.pid_exists(pid)

    def _wait_command(self, command: list[str]) -> None:
        import subprocess

        logger.debug(f"Attempting to run: {' '.join(command)!r}")
        try:
            subprocess.Popen(command).communicate()
        except Exception as exc:
            logger.error(f"Unable to run: {' '.join(command)!r}", exc_info=True)

    def _background_command(self, command: list[str]) -> int | None:
        if "sudo" in command:
            print(" ".join(command))
            return

        import subprocess

        logger.debug(f"Attempting to run: {' '.join(command)!r}")
        try:
            return subprocess.Popen(command).pid
        except Exception as exc:
            logger.error(f"Unable to run: {' '.join(command)!r}", exc_info=True)

    def copy(self) -> State:
        import dacite

        data = dataclasses.asdict(self)
        state = dacite.from_dict(data_class=State, data=data)
        return state

    def send_config(self, device_name, config=None):
        self.get_running_device_state(device_name)
        if config is None:
            config = []
        device = self.load_device_from_state(device_name, preserve_ports=True)
        device.debug_print()
        if device.console:
            device.console.send_config(config)

    def check_state(self):
        devices_to_stop = []
        bridges_to_stop = []
        for device_name, device in self.devices.items():

            if not device.pid:
                continue

            if self._is_pid_running(device.pid):
                logger.debug(
                    f"Device: {device_name} {device.pid} Looks like it's still running.  Carrying on",
                )
                continue

            logger.error(f"{device_name} {device.pid} no longer running.  Stopping")
            devices_to_stop.append(device_name)

        for bridge_name, bridge in self.bridges.items():

            if not bridge.pid:
                continue

            if self._is_pid_running(bridge.pid):
                logger.debug(
                    f"Bridge: {bridge_name} {bridge.pid} Looks like it's still running.  Carrying on",
                )
                continue

            logger.error(f"{bridge_name} {bridge.pid} no longer running.  Stopping")
            bridges_to_stop.append(bridge_name)

        for bridge in bridges_to_stop:
            self.stop_bridge(bridge)

        for device_name in devices_to_stop:
            self.stop_device(device_name)

    def output_devices(self) -> list[DeviceOutput]:
        output = []
        for device_name, device in self.devices.items():
            output.append(
                DeviceOutput(
                    name=device_name,
                    console_port=device.console_ports.get(0),
                    qemu_port=device.qemu_port,
                    state="running" if device.pid else "stopped",
                ),
            )
        output.sort(key=lambda t: t["name"])
        return output

    def output_tags(self) -> list[TagOutput]:
        output = []
        for tag, image in self.tags.items():
            output.append(
                TagOutput(
                    tag=tag,
                    image=image,
                ),
            )
        output.sort(key=lambda t: t["tag"])
        return output

    def output_bridges(
        self,
    ) -> tuple[
        list[TCPEndpointOutput],
        list[TapEndpointOutput],
        list[NICEndpointOutput],
    ]:
        tcp_outputs = []
        sniffer_outputs = []
        nic_outputs = []
        bridge_state = (
            lambda bridge: "running" if self.bridges[bridge].pid else "stopped"
        )
        for bridge, interface in self.tap_endpoints.items():
            sniffer_outputs.append(
                TapEndpointOutput(
                    bridge=bridge,
                    state=bridge_state(bridge),
                    interface=interface.interface,
                ),
            )
        for bridge, interface in self.phyical_endpoints.items():
            nic_outputs.append(
                NICEndpointOutput(
                    bridge=bridge,
                    state=bridge_state(bridge),
                    interface=interface.interface,
                ),
            )
        for device_name, device in self.devices.items():
            for index, interface in device.interfaces.items():
                if interface.connection:
                    tcp_outputs.append(
                        TCPEndpointOutput(
                            bridge=interface.connection,
                            state=bridge_state(interface.connection),
                            device=device_name,
                            index=index,
                            port=interface.tcp_port,
                        ),
                    )

        return tcp_outputs, sniffer_outputs, nic_outputs

    def get_open_interfaces(self) -> list[str]:
        open_interfaces = []
        for device_name, device in self.devices.items():
            for index, interface in device.interfaces.items():
                if interface.connection:
                    logger.debug(
                        f"Passing over {device_name}{DEVICE_INTERFACE_SEPARATOR}{index}"
                        f" because it's in use by {interface.connection}",
                    )
                    continue
                open_interface = f"{device_name}{DEVICE_INTERFACE_SEPARATOR}{index}"
                open_interfaces.append(open_interface)
        open_interfaces.sort()
        return open_interfaces

    def add_tag(
        self,
        tag: str,
        image: pathlib.Path | str,
        overwrite: bool = False,
    ):
        if (existing := self.tags.get(tag)) and not overwrite:
            self._error_raise(f"{tag} already in use by {existing}")
        elif existing := self.tags.get(tag):
            logger.debug(f"Updating {tag} from {existing}")
        logger.info(f"{tag} -> {image}")
        self.tags[tag] = str(image)

    def delete_tag(self, tag: str):
        if not self.tags.get(tag):
            self._error_raise(f"{tag} not found")
        logger.info(f"Deleting {tag}")
        self.tags.pop(tag)

    def add_bridge(
        self,
        name: str,
        tcp_endpoints: list[str],
        nic_endpoint: str | None = None,
        tap_endpoint: str | None = None,
    ):
        endpoints = 0

        if self.bridges.get(name):
            self._error_raise(f"Bridge {name} already exists")

        self._validate_tcp_endpoints(tcp_endpoints)
        for _ in tcp_endpoints:
            endpoints += 1
        if tap_endpoint:
            self._validate_nic(tap_endpoint)
            endpoints += 1
        if nic_endpoint:
            self._validate_nic(nic_endpoint)
            endpoints += 1
        if endpoints < 2:
            self._error_raise(f"Can only create bridge with at least 2 endpoints")

        if nic_endpoint:
            self.phyical_endpoints[name] = PhysicalConnectionEndpoint(
                interface=nic_endpoint,
            )

        if tap_endpoint:
            self.tap_endpoints[name] = TapEndpoint(interface=tap_endpoint)
        for tcp_endpoint in tcp_endpoints:
            device_name, index = self._split_device_interface_index(tcp_endpoint)
            self.devices[device_name].interfaces[index].connection = name
        self.bridges[name] = ConnectionState(name=name)

    def get_unused_base_mac(self, oui: str = common.QEMU_OUI):
        import random

        if not validate_oui(oui):
            raise RuntimeError(f"Invalid OUI: {oui}")
        for _ in range(RAND_MAC_ATTEMPTS):
            rnd = random.randint(0, 0xFFFF)
            rand_base = f"{oui}:{rnd >> 8:02x}:{rnd & 0xff:02x}:00".lower()
            if rand_base not in self.used_mac_addresses:
                logger.debug(f"Returning fresh random mac {rand_base}")
                return rand_base
        raise RuntimeError(
            f"Random mac address could not be found within {RAND_MAC_ATTEMPTS} attempts.  Is something wrong?",
        )

    def stop_bridge(self, bridge_name: str, delete: bool = False):
        for device_name, device in [d for d in self.devices.items() if delete]:
            for index, interface in list(device.interfaces.items()):
                if not interface.connection == bridge_name:
                    continue
                logger.debug(
                    f"{bridge_name} being deleted.  Clearing: {device_name}{DEVICE_INTERFACE_SEPARATOR}{index}",
                )
                interface.connection = None
        if bridge := self.bridges.get(bridge_name):
            self._stop_pid(bridge.pid)
            self.bridges[bridge_name].pid = None
            self.bridges[bridge_name].sniffer_port = None
            if not delete:
                logger.info(f"Not deleting {bridge_name}")
                return
        else:
            # Clean up anyway
            delete = True

        logger.info(f"Deleting bridge {bridge}")
        self.bridges.pop(bridge_name, None)
        self.tap_endpoints.pop(bridge_name, None)
        self.phyical_endpoints.pop(bridge_name, None)

    def stop_device(self, device_name: str, delete=False):
        if not (device := self.devices.get(device_name)):
            self._error_raise(f"Device {device_name} does not exist.")
        logger.info(f"Stopping {device_name}")
        if device.pid:
            self._stop_pid(device.pid)
            device.pid = None
        connections_to_stop: set[str] = set()
        for index, interface in list(device.interfaces.items()):
            if not interface.connection:
                continue
            interface.tcp_port = None
            logger.debug(
                f"Stopping {device_name}{DEVICE_INTERFACE_SEPARATOR}{index} - {interface.connection}",
            )
            connections_to_stop.add(interface.connection)
        for connection in connections_to_stop:
            self.stop_bridge(connection, delete=delete)

    def start_bridge(self, bridge_name: str):
        logger.info(f"Attempting to start bridge {bridge_name}")
        bridge_state = self.get_bridge_state(bridge_name)
        if bridge_state.pid:
            self._error_raise(f"Bridge {bridge_name} already running")
        bridge_state.sniffer_port = common.get_free_port()
        command = self.get_bridge_command(bridge_name, bridge_state.sniffer_port)
        self.bridges[bridge_name].pid = self._background_command(command)

    def get_bridge_command(
        self,
        bridge_name: str,
        sniffer_port: int,
    ):
        tcp_endpoints = []
        for device_name, device in self.devices.items():
            for index, interface in device.interfaces.items():
                if interface.connection != bridge_name:
                    continue
                logger.debug(
                    f"Evaluating {device_name}{DEVICE_INTERFACE_SEPARATOR}{index} for {bridge_name}",
                )
                if not device.pid:
                    self._error_raise(
                        f"Cannot get command for {bridge_name} while {device_name} is stopped",
                    )
                tcp_endpoints.append(f"127.0.0.1:{interface.tcp_port}")
        log_file = (common.NDLAB_DIRECTORY / f"bridge-{bridge_name}.log").absolute()
        ndlab = __name__.split(".")[0]
        import shutil

        if not (ndlab_path := shutil.which(ndlab)):
            self._error_raise(f"Cannot locate path for {ndlab}")
        command = [ndlab_path]
        command.append("launch-bridge")
        command.extend(["--name", bridge_name])
        command.extend(["--log-file", str(log_file)])
        command.extend(
            [
                "--sniffer-port",
                str(sniffer_port),
            ],
        )
        for tcp_endpoint in tcp_endpoints:
            command.extend(
                [
                    "--tcp-endpoint",
                    tcp_endpoint,
                ],
            )
        if tap_endpoint := self.tap_endpoints.get(bridge_name):
            command.extend(
                [
                    "--tap-endpoint",
                    tap_endpoint.interface,
                ],
            )
        if physical_endpoint := self.phyical_endpoints.get(bridge_name):
            command.extend(
                [
                    "--physical-endpoint",
                    physical_endpoint.interface,
                ],
            )
            command.insert(0, "sudo")
            command.extend(
                [
                    "&",
                    ndlab_path,
                    "bridge",
                    "register-bridge-pid",
                    bridge_name,
                    "$!",
                ],
            )
        return command

    def register_bridge_pid(self, bridge_name: str, pid: int) -> None:
        bridge_state = self.get_bridge_state(bridge_name)
        bridge_state.pid = pid

    def get_bridge_state(self, bridge_name: str) -> ConnectionState:
        if not (bridge_state := self.bridges.get(bridge_name)):
            self._error_raise(f"Bridge {bridge_name} does not exist")
        return bridge_state

    def get_running_bridge_state(self, bridge_name: str) -> ConnectionState:
        bridge_state = self.get_bridge_state(bridge_name)
        if not bridge_state.pid:
            self._error_raise(f"bridge {bridge_name} not running")
        return bridge_state

    def delete_device(self, name: str, leave_overlay: bool = False):
        import os

        logger.debug(f"Deleting {name}")
        self.stop_device(name, delete=True)
        deleted_device = self.devices.pop(name)
        if leave_overlay:
            return

        overlay = pathlib.Path(deleted_device.overlay)
        overlay_parent = overlay.parent

        logger.debug(f"Attempting to clean up {overlay}")
        try:
            os.remove(overlay)
        except FileNotFoundError:
            logger.error(f"{overlay.name} does not exist.")

        logger.debug(f"Attempting to clean up {overlay_parent}")
        try:
            os.rmdir(overlay_parent)
        except FileNotFoundError:
            logger.error(f"{overlay.name} does not exist.")
        except OSError:
            logger.error(f"{overlay_parent.name} is not empty.  Leaving")
        logger.debug(f"Deleted {name}")

    def get_device_state(self, device_name) -> DeviceState:
        if not (device_state := self.devices.get(device_name)):
            self._error_raise(f"Device {device_name} has not been loaded")
        return device_state

    def get_running_device_state(self, device_name) -> DeviceState:
        device_state = self.get_device_state(device_name)
        if not device_state.pid:
            self._error_raise(f"{device_name} not running")
        return device_state

    def load_running_device_from_state(
        self,
        device_name,
        preserve_ports=False,
    ) -> common.VirtualNetworkDevice:
        self.get_running_device_state(device_name)
        return self.load_device_from_state(
            device_name=device_name,
            preserve_ports=preserve_ports,
        )

    def load_device_from_state(
        self,
        device_name,
        preserve_ports=False,
    ) -> common.VirtualNetworkDevice:
        device_state = self.get_device_state(device_name)
        ethernet_ports = {}
        console_ports = {}
        qemu_port = None
        if preserve_ports:
            console_ports = device_state.console_ports
            qemu_port = device_state.qemu_port
            ethernet_ports = {
                index: intf.tcp_port
                for index, intf in device_state.interfaces.items()
                if intf.tcp_port is not None
            }
        logger.debug(f"{ device_state.interfaces.items()=}")
        if not (device_type := images.PLATFORM_MAPPING.get(device_state.type)):
            self._error_raise(f"Device type {device_type} is unknown")
        device = device_type(
            name=device_name,
            image=device_state.image,
            base_mac=device_state.base_mac_address,
            build_tag=device_state.build_tag,
            qemu_port=qemu_port,
            ethernet_ports=ethernet_ports,
            console_ports=console_ports,
        )
        device.ethernet_ports
        logger.debug(f"device instantiated: {device!r}")
        return device

    def get_device_console_port(self, device_name, console_index):
        device_state = self.get_device_state(device_name)
        if not device_state.pid:
            self._error_raise(f"Device {device_name} not running")
        logger.debug(f"{device_state.console_ports}")
        if not (console_port := device_state.console_ports.get(console_index)):
            self._error_raise(
                f"{device_name} does not have console port {console_index}",
            )
        return console_port

    def get_qemu_port(self, device_name: str):
        device_state = self.get_running_device_state(device_name)
        if not device_state.qemu_port:
            self._error_raise(f"No qemu port assigned to {device_name}")
        return device_state.qemu_port

    def get_qemu_image_cmd(self, device_name: str, create_directory: bool = False):
        device = self.load_device_from_state(device_name)
        logger.debug(device.get_qemu_img_cmd(create_directory=create_directory))
        return device.get_qemu_img_cmd()

    def start_device(self, device_name):
        if not (device_state := self.devices.get(device_name)):
            self._error_raise(f"Device not loaded")
        if device_state.pid:
            self._error_raise(f"Device already running")
        device = self.load_device_from_state(device_name)
        qemu_img_cmd = device.get_qemu_img_cmd(create_directory=True)
        qemu_cmd = device.get_qemu_cmd()
        device_state = self.devices[device_name]
        if qemu_img_cmd:
            self._wait_command(qemu_img_cmd)
        device_state.pid = self._background_command(qemu_cmd)
        device_state.qemu_port = device.qemu_port
        device_state.console_ports = device.console_ports.copy()
        for index, port in device.ethernet_ports.items():
            device_state.interfaces.setdefault(index, InterfaceState()).tcp_port = port

    def load_device(
        self,
        name: str,
        tag: str,
        build_tag: str | None = None,
    ):

        if not (image_path := self.tags.get(tag)):
            self._error_raise(f"tag {tag} does not exist.  Cannot load")

        if self.devices.get(name):
            self._error_raise(f"Device {name} exists already.")

        try:
            device_type = images.get_device_by_imagename(image_path)
        except RuntimeError:
            self._error_raise(f"Unable to load {image_path}")

        base_mac = self.get_unused_base_mac()
        image_path_str = str(pathlib.Path(image_path).absolute())
        logger.debug(
            f"Loading device of type {device_type} with base mac {base_mac} using {image_path_str}",
        )

        device = device_type(
            name=name,
            image=image_path_str,
            base_mac=base_mac,
            build_tag=build_tag,
        )

        device_state = DeviceState(
            pid=0,
            type=device.NAME,
            image=str(device.image),
            overlay=str(device.overlay),
            build_tag=device.build_tag,
            base_mac_address=device.base_mac,
            qemu_port=None,
            console_ports={},
            interfaces={index: InterfaceState() for index in range(device.NIC_COUNT)},
        )
        self.devices[name] = device_state

    def get_qemu_cmd(self, device_name: str):
        device = self.load_device_from_state(device_name)
        return device.get_qemu_cmd()

    @classmethod
    @contextlib.contextmanager
    def auto_saving_open(cls, filename: str | pathlib.Path):
        import shutil
        import tempfile

        full_path = pathlib.Path(filename)
        state = cls.from_file(
            filename,
            write_mode=True,
        )
        yield state
        filename = full_path.name
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_file = pathlib.Path(temp_dir) / filename
            state.save(temp_file)
            shutil.copy(temp_file, full_path)

    @classmethod
    def from_file(
        cls,
        filename: str | pathlib.Path,
        write_mode: bool = False,
    ) -> State:

        import dacite
        import yaml

        try:
            with open(filename, "r+") as file:
                state = dacite.from_dict(data_class=State, data=yaml.safe_load(file))

        except (OSError, TypeError):
            state = cls()
            if write_mode:
                logger.warning(f"{filename} not found.  Creating new file")
                pathlib.Path(filename).parent.mkdir(parents=True, exist_ok=True)
                state.save(filename)
        state.filename = filename
        if write_mode:
            state.check_state()
        return state

    def save(self, filename: pathlib.Path | str | None = None):
        import shutil

        import yaml

        filename = filename or self.filename
        if not filename:
            raise RuntimeError(f"Cannot save state without filename")
        filename = pathlib.Path(str(filename))
        parent = filename.parent
        if filename.exists():
            backup_name = parent / f"{filename.name}.bak"
            shutil.copy(filename, backup_name)
        with open(filename, "w+") as file:
            yaml.safe_dump(
                dataclasses.asdict(self),
                stream=file,
                sort_keys=False,
            )
