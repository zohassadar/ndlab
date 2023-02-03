""""
tcp_buffer = 4 bytes size header + packet (1 or more)
packet = layer2 packet
pcap = 16 byte pcap header + packet

"""
from __future__ import annotations

import asyncio
import collections
import fcntl
import ipaddress
import itertools
import logging
import os
import pathlib
import re
import signal
import socket
import struct
import sys
import time
import typing as T

import ndlab.common as common

MAX_CAPTURE_CONNECTIONS = 1

MTU = 1518

MAX_READ = 10000
MAX_WAIT = 5
LENGTH = 4


def is_device_promiscuous(interface: str) -> bool:
    FLAGS = "flags"
    PROMISCUOUS_FLAG = 0x100
    SYS_CLASS_NET = "/sys/class/net"
    if not os.name == "posix":
        raise RuntimeError(
            f"Unable to check if {interface} is promiscuous in non-linux"
        )
    logger.debug(f"is_device_promiscuous called for {interface!r}")
    flagsfile = pathlib.Path(SYS_CLASS_NET) / interface
    if not (flagsfile := (flagsfile / FLAGS)).exists():
        raise RuntimeError(f"{FLAGS} not found in {flagsfile}")
    try:
        flags = open(flagsfile, "r+").read().strip()
    except:
        logger.error(f"Unable to open {flagsfile}", exc_info=True)
        raise
    logger.debug(f"Flag file contents: {flags}")
    if not re.match(r"0x\d+", flags):
        raise RuntimeError(f"Unexpected flag file contents {flagsfile}: {flags!r}")
    return bool(eval(flags) & PROMISCUOUS_FLAG)


class PCAP:
    """
    https://wiki.wireshark.org/Development/LibpcapFileFormat
    """

    MAGIC_NUMBER = 0xA1B2C3D4  # unsigned 32 bit (I)
    VERSION_MAJOR = 2  # unsigned 16 bit (H)
    VERSION_MINOR = 4  # unsigned 16 bit (H)
    GMT_OFFSET = 0  # signed 32 bit (i)
    TIMESTAMP_ACCURACY = 0  # unsigned 32 bit (I)
    MAX_PACKET_LENGTH = 65535  # unsigned 32 bit (I)
    DATA_LINK_TYPE = 1  # unsigned 32 bit (I)

    HEADER = struct.pack(
        "!IHHiIII",
        MAGIC_NUMBER,
        VERSION_MAJOR,
        VERSION_MINOR,
        GMT_OFFSET,
        TIMESTAMP_ACCURACY,
        MAX_PACKET_LENGTH,
        DATA_LINK_TYPE,
    )

    PACKET_HEADER_FORMAT = "!IIII"

    @classmethod
    def get_pcap_from_packet(cls, packet: bytes) -> bytes:
        now = time.time()
        seconds = int(now)  # unsigned 32 bit (I)
        microseconds = int((now - seconds) * 1_000_000)  # unsigned 32 bit (I)
        reported_length = len(packet)  # unsigned 32 bit (I)
        actual_length = reported_length  # unsigned 32 bit (I)

        header = struct.pack(
            cls.PACKET_HEADER_FORMAT,
            seconds,
            microseconds,
            reported_length,
            actual_length,
        )
        return header + packet


"""
! = network = big
H = u16
h = s16

I = u32

guint32 magic_number;   /* magic number */
guint16 version_major;  /* major version number */
guint16 version_minor;  /* minor version number */
gint32  thiszone;       /* GMT to local correction */
guint32 sigfigs;        /* accuracy of timestamps */
guint32 snaplen;        /* max length of captured packets, in octets */
guint32 network;        /* data link type */


"""
# https://github.com/torvalds/linux/blob/0326074ff4652329f2a1a9c8685104576bd8d131/include/uapi/linux/if_ether.h#L132
ETH_P_ALL = 0x0003  # Every packet (be careful!!!)


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


def signal_handler(signal, frame):
    print(f"{signal} received.  Canceling.")
    try:
        asyncio.get_running_loop().stop()
    except Exception as exc:
        logger.error(f"Exception: {exc!s}")
    time.sleep(3)
    sys.exit("heh")


def error_exit(msg):
    logger.critical(f"Error condition: {msg}")
    print(msg, file=sys.stderr)
    sys.exit(1)


class TCPBuffer:
    def __init__(self):
        self._buffer = collections.deque()

    def _empty_buffer(self):
        while self._buffer:
            self._buffer.pop()

    def _current_buffer_size(self):
        return len(self._buffer)

    def get_packets_from_tcp_data(self, data: bytes) -> list[bytes]:
        packets = []
        self._buffer.extend(data)
        while self._buffer:
            try:
                reported_size_packed = bytes(
                    self._buffer.popleft() for _ in range(LENGTH)
                )
            except IndexError:
                logger.error(f"Unable to read size from tcp buffer")
                break
            reported_size_bytes = struct.unpack("I", reported_size_packed)[0]
            reported_size_int = socket.ntohl(reported_size_bytes)
            if reported_size_int > MTU:
                self._empty_buffer()
                logger.error(f"Unreasonable size {reported_size_int}.  Clearing buffer")
                break
            if reported_size_int > self._current_buffer_size():
                reported_size_list = list(reported_size_packed)
                while reported_size_list:
                    self._buffer.appendleft(reported_size_list.pop())
                logger.info(f"Storing bytes in the buffer for the next round")
                break

            logger.debug(
                f"Attempting to read {reported_size_int} bytes with {self._current_buffer_size()} bytes left"
            )
            try:
                packet = bytes(self._buffer.popleft() for _ in range(reported_size_int))
            except IndexError:
                logger.error(f"Unable to read {reported_size_int} bytes from payload")
                break
            logger.debug(f"Found a packet with {reported_size_int} bytes")
            packets.append(packet)

        return packets


def get_payload_from_packet(packet: bytes) -> bytes:
    length = len(packet)
    logger.debug(f"Packing length {length}")
    payload = struct.pack("I", socket.htonl(length)) + packet
    return payload


class ConnectionEndpoint(T.Protocol):
    receive_queue: asyncio.Queue
    send_queues: list[asyncio.Queue]

    async def connect(self):
        ...


class Bridge:
    def __str__(self):
        return f"Bridge {self.name})"

    def __init__(
        self,
        name: str,
        tcp_endpoints: list[TCPClient],
        sniffer_endpoint: TCPSnifferServer | None = None,
        physical_endpoint: PhysicalNetworkInterfaceClient | None = None,
        tap_endpoint: TapInterfaceClient | None = None,
    ):
        self.name = name
        self.tcp_endpoints = tcp_endpoints
        self.physical_endpoint = physical_endpoint
        self.sniffer_endpoint = sniffer_endpoint
        self.tap_endpoint = tap_endpoint
        self._combined: list[ConnectionEndpoint] = self.tcp_endpoints  # type: ignore
        if self.sniffer_endpoint:
            self._combined.append(self.sniffer_endpoint)  # type: ignore
        if self.physical_endpoint:
            self._combined.append(self.physical_endpoint)  # type: ignore
        if self.tap_endpoint:
            self._combined.append(self.tap_endpoint)  # type: ignore
        self.task: asyncio.Task | None = None

    async def connect(self):
        for endpoint, other_endpoint in itertools.permutations(self._combined, 2):
            other_endpoint.send_queues.append(endpoint.receive_queue)
        logger.debug(f"Awaiting tasks for connection {self.name}")
        group = asyncio.gather(*[endpoint.connect() for endpoint in self._combined])
        try:
            await group
        except asyncio.CancelledError:
            logger.error("Connect cancelled")
            group.cancel()
            logger.error("All tasks cancelled")
        return


class TCPClient:
    def __repr__(self):
        return f"{type(self).__name__}({self.port},{self.ip_address})"

    def __init__(
        self,
        port: int,
        ip_address: str = common.LOCALHOST,
    ):
        self.ip_address = ip_address
        self.port = port
        self.send_queues: list[asyncio.Queue] = []
        self.receive_queue = asyncio.Queue()
        self.stopped = False
        self.writer: asyncio.StreamWriter | None = None
        self.reader: asyncio.StreamReader | None = None

    async def connect(self):
        try:
            logger.info(f"{self!s} Attempting to connect to port {self.port}")
            self.reader, self.writer = await asyncio.open_connection(
                self.ip_address,
                self.port,
            )
            await asyncio.gather(
                self.write_handler(self.writer),
                self.read_handler(self.reader),
            )
        except asyncio.CancelledError:
            logger.error("TCP Client cancelled")
            return

    async def read_handler(
        self,
        reader: asyncio.StreamReader,
    ):
        # tcp_buffer = TCPBuffer()
        logger.info(f"{self!s} reading for {len(self.send_queues)} queues")
        tcp_buffer = TCPBuffer()
        while True:
            try:
                data = await reader.read(MAX_READ)
                logger.log(9, f"{self} read {len(data)} bytes")
                if not data:
                    logger.error(f"{self!s} read empty packet.  Disconnecting.")
                    break

                packets = tcp_buffer.get_packets_from_tcp_data(data)
                queues = len(self.send_queues)
                for packet in packets:
                    for index, queue in enumerate(self.send_queues, start=1):
                        logger.log(
                            9, f"{self!s} forwarding to queue {index} of {queues}"
                        )
                        await queue.put(packet)

            except ConnectionResetError:
                logger.error(f"{self!s}: Connection reset")
                break
            except asyncio.CancelledError:
                logger.error(f"{self!s}: tcp reader Cancelled")
                raise

    async def write_handler(
        self,
        client_writer: asyncio.StreamWriter,
    ):
        stop = False
        while True:
            if stop:
                logger.info(f"Stopping write handler")
                break
            if not self.writer:
                logger.info(f"Writer closed. Ending")
                break
            try:
                packet = await self.receive_queue.get()
                logger.debug(
                    f"{self} receive queue is {self.receive_queue.qsize()} items big!"
                )
                payload = get_payload_from_packet(packet)
                logger.debug(f"{self!s} received {len(payload)} bytes from queue")
                client_writer.write(payload)
                await client_writer.drain()
                logger.debug(f"{self!s} {len(payload)} bytes sent")

            except ConnectionResetError:
                stop = True
                logger.error(f"{self!s}: Connection reset")
            except asyncio.CancelledError:
                stop = True
                logger.error(f"{self!s}: tcp writer Cancelled")
                raise
            except BaseException as exc:
                stop = True
                logger.error(f"Exception raised.  {exc!s}")
                raise


class TapInterfaceClient:
    TUNSETIFF = 0x400454CA
    IFF_TAP = 0x0002
    IFF_NO_PI = 0x1000

    def __repr__(self):
        return f"{type(self).__name__}({self.interface})"

    def __init__(self, interface: str):
        self.interface = interface
        self.receive_queue = asyncio.Queue()
        self.send_queues: list[asyncio.Queue] = []
        # setup tap side

        self.tap = os.open("/dev/net/tun", os.O_RDWR)
        args = struct.pack(
            "16sH",
            interface.encode(),
            self.IFF_TAP | self.IFF_NO_PI,
        )
        fcntl.ioctl(
            self.tap,
            self.TUNSETIFF,
            args,
        )

    async def disconnect(self):
        logger.info(f"Closing connection")
        try:
            os.close(self.tap)
        except:
            logger.error(f"Unable to close tap", exc_info=True)

    async def connect(self):
        try:
            await asyncio.gather(
                self.write_tap(),
                self.read_tap(),
            )
        except asyncio.CancelledError:
            logger.error("Tap cancelled")
            return

    async def write_tap(self):
        while True:
            try:
                packet = await self.receive_queue.get()
            except asyncio.CancelledError:
                logger.info(f"Tap writer cancelled")
                raise

            logger.debug(
                f"{self} receive queue is {self.receive_queue.qsize()} items big!"
            )
            if not packet:
                logger.error(f"Tap received empty response from queue")
                continue
            logger.log(9, f"TAP forwarding {len(packet)} to interface")
            os.write(self.tap, packet)

    async def read_tap(self):
        loop = asyncio.get_running_loop()
        while True:
            try:
                packet = await loop.run_in_executor(
                    None,
                    os.read,
                    self.tap,
                    MAX_READ,
                )
                logger.log(9, f"Tap packet of length {len(packet)} from interface")
                queues = len(self.send_queues)
                for index, queue in enumerate(self.send_queues, start=1):
                    logger.log(
                        9,
                        f"Sending packet of length {len(packet)} to queue {index} of {queues}",
                    )
                    await queue.put(packet)
            except asyncio.CancelledError:
                logger.info("Tap reader cancelled.")
                raise


class PhysicalNetworkInterfaceClient:
    def __repr__(self):
        return f"{type(self).__name__}({self.interface})"

    def __init__(self, interface: str):
        self.interface = interface
        if not is_device_promiscuous(interface):
            raise RuntimeError(f"Interface {interface} is not in promiscuous mode.")
        self.receive_queue = asyncio.Queue()
        self.send_queues: list[asyncio.Queue] = []
        self.socket = socket.socket(
            socket.AF_PACKET,
            socket.SOCK_RAW,
            socket.ntohs(ETH_P_ALL),
        )
        self.socket.bind((interface, 0))
        self.socket.setblocking(False)

    async def disconnect(self):
        logger.info(f"Closing connection")
        if self.socket:
            self.socket.close()

    async def connect(self):
        try:
            await asyncio.gather(
                self.write_physical(),
                self.read_physical(),
            )
        except asyncio.CancelledError:
            logger.error("line 464")
            return

    async def write_physical(self):

        while True:
            try:
                packet = await self.receive_queue.get()
            except asyncio.CancelledError:
                logger.info(f"physical writer cancelled")
                raise
            logger.debug(
                f"{self} receive queue is {self.receive_queue.qsize()} items big!"
            )
            if not packet:
                logger.error(f"Physical received empty response from queue")
                continue
            logger.log(9, f"Physical forwarding {len(packet)} to interface")
            self.socket.send(packet)

    async def read_physical(self):
        loop = asyncio.get_running_loop()
        while True:
            try:
                packet = await loop.sock_recv(self.socket, MAX_READ)
                logger.log(9, f"Physical packet of length {len(packet)} from interface")
                queues = len(self.send_queues)
                for index, queue in enumerate(self.send_queues, start=1):
                    logger.log(
                        9,
                        f"Sending packet of length {len(packet)} to queue {index} of {queues}",
                    )
                    await queue.put(packet)
            except asyncio.CancelledError:
                logger.info(f"physical reader cancelled")
                raise


class TCPSnifferServer:
    def __repr__(self):
        return f"{type(self).__name__}({self.port})"

    def __init__(
        self,
        port: int,
        bind_address: str = common.LOCALHOST,
    ):
        self.port = port
        self.bind_address = bind_address
        self.receive_queue = asyncio.Queue()
        self.send_queues = []
        self.capture_queues: list[asyncio.Queue] = []

    async def forward_payloads_to_sessions(self):
        logging.debug(f"Forwarding payloads to sessions")
        while True:
            try:
                packet = await self.receive_queue.get()
                logger.debug(
                    f"{self} receive queue is {self.receive_queue.qsize()} items big!"
                )
                if not self.capture_queues:
                    logger.log(9, f"Discarding packet of {len(packet)}.  Empty Queue")
                pcap = PCAP.get_pcap_from_packet(packet)
                forwarding_queues = len(self.capture_queues)
                for index, capture_queue in enumerate(self.capture_queues, start=1):
                    logger.log(
                        9,
                        f"Forwarding pcap of {len(pcap)} to client {index} of {forwarding_queues}",
                    )
                    await capture_queue.put(pcap)
            except asyncio.CancelledError:
                logger.info(f"sniffer forwarder cancelled")
                raise

    async def connect(self):
        logger.info(f"Starting TCP Sniffer server")
        server = asyncio.start_server(
            self.start_session,
            host=self.bind_address,
            port=self.port,
            limit=MAX_CAPTURE_CONNECTIONS,
        )
        try:

            await asyncio.gather(
                server,
                self.forward_payloads_to_sessions(),
            )
        except asyncio.CancelledError:
            logger.info(f"Sniffer Server cancelled")
            return

    async def start_session(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ):
        logger.info(f"TCP Sniffer client connected")
        if len(self.capture_queues) >= MAX_CAPTURE_CONNECTIONS:
            logger.error(f"Max connections reached.  Dropping connection")
            client_writer.close()
            return await client_writer.wait_closed()
        capture_queue = asyncio.Queue()
        await capture_queue.put(PCAP.HEADER)
        self.capture_queues.append(capture_queue)
        try:
            await asyncio.gather(
                self.write_handler(capture_queue, client_writer),
                self.read_handler(client_reader),
            )
        finally:
            self.capture_queues.remove(capture_queue)

    async def write_handler(
        self,
        queue: asyncio.Queue,
        client_writer: asyncio.StreamWriter,
    ):
        while True:
            try:
                pcap = await queue.get()
                logger.log(9, f"Received pcap of {len(pcap)} received.  Writing")
                client_writer.write(pcap)
                await client_writer.drain()

            except ConnectionResetError:
                logger.error(f"Connection reset.  Breaking")
                break
            except asyncio.CancelledError:
                logger.error(f"sniffer write cancelled.")
                raise
            except Exception as exc:
                logger.error(f"Exception raised.  {exc!s}")
                break

    async def read_handler(
        self,
        client_reader: asyncio.StreamReader,
    ):
        while True:
            try:
                data = await client_reader.read(MAX_READ)
            except asyncio.CancelledError:
                logger.error(f"sniffer read cancelled.")
                raise
            except Exception as exc:
                logger.error(f"Exception raised.  {exc!s}")
                break
            if not data:
                logger.error(
                    f"Empty packet read from client.  Assumed to be disconnected",
                )
                break
            logger.info(
                f"Unexpected packet of length {len(data)} received.  Discarding",
            )


async def connect(connection: Bridge):
    logger.info(f"asyncio entrypoint into bridge connection")
    try:
        await connection.connect()
    except asyncio.CancelledError:
        error_exit("Cancelled in entrypoint")


def start_bridge(
    name: str,
    log_file: str,
    tcp_endpoints: list[str],
    physical_endpoint: str,
    tap_endpoint: str,
    sniffer_port: int | None = None,
    debug: bool = False,
):
    # common.set_logging(debug, file=log_file)
    common.set_logging(debug)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    tcp_instances = []

    physical_instance = None
    if physical_endpoint:
        physical_instance = PhysicalNetworkInterfaceClient(physical_endpoint)

    tap_instance = None
    if tap_endpoint:
        tap_instance = TapInterfaceClient(tap_endpoint)

    sniffer_instance = None
    if sniffer_port:
        sniffer_instance = TCPSnifferServer(
            port=sniffer_port, bind_address=common.LOCALHOST
        )

    for tcp_endpoint in tcp_endpoints:
        try:
            host, port = tcp_endpoint.split(":")
            ipaddress.IPv4Address(host)
            port = int(port)
            tcp_instances.append(
                TCPClient(
                    port=port,
                    ip_address=host,
                ),
            )
        except Exception as exc:
            error_exit(f"Invalid input: {tcp_endpoint!r} {type(exc).__name__}: {exc!s}")

    try:
        bridge = Bridge(
            name=name,
            tcp_endpoints=tcp_instances,
            physical_endpoint=physical_instance,
            tap_endpoint=tap_instance,
            sniffer_endpoint=sniffer_instance,
        )
        asyncio.run(connect(bridge))
        error_exit("exiting")

    except asyncio.CancelledError:
        logger.error("This has been reached?")
    except BaseException as exc:
        error_exit(f"Problem! {type(exc).__name__}: {exc!s}")


"""
ip tuntap add mod tap name <interface name with tap in it>
ip link set dev <tap_int> up
ip address add 192.168.13.1/24 dev <tap_int>
"""
