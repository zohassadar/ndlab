""""
payload = 4 bytes (network order) describing size + packet
packet = the payload without the 4 bytes describing size

"""
from __future__ import annotations

import asyncio
import ipaddress
import itertools
import logging
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
    import pathlib
    import re

    FLAGS = "flags"
    PROMISCUOUS_FLAG = 0x100
    SYS_DEVICES = "/sys/devices/"
    logger.debug(f"is_device_promiscuous called for {interface!r}")
    for file in pathlib.Path(SYS_DEVICES).rglob(interface):
        logger.debug(f"Found {file!r}")
        if not (flagsfile := (file / FLAGS)).exists():
            raise RuntimeError(f"{FLAGS} not found in {file}")
        try:
            flags = open(flagsfile).read().strip()
        except:
            logger.error(f"Unable to open {flagsfile}", exc_info=True)
            raise
        logger.debug(f"Flag file contents: {flags}")
        if not re.match(r"0x\d+", flags):
            raise RuntimeError(f"Unexpected flag file contents {flagsfile}: {flags!r}")
        return bool(eval(flags) & PROMISCUOUS_FLAG)
    raise RuntimeError(f"Directory {interface!r} not found in {SYS_DEVICES!r}")


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
    error_exit(f"{signal} received.  Exiting.")


def error_exit(msg):
    logger.critical(f"Error condition: {msg}")
    print(msg, file=sys.stderr)
    sys.exit(1)


def get_packet_from_payload(payload: bytes) -> bytes:
    packet_length = len(payload)
    if packet_length < LENGTH:
        logger.error(f"Invalid length {packet_length}.  Returning empty result")
        return b""

    reported_size_packed, packet = payload[:LENGTH], payload[LENGTH:]
    reported_size_unpacked = struct.unpack("I", reported_size_packed)[0]
    reported_size = socket.ntohl(reported_size_unpacked)

    packet_length = len(packet)
    if packet_length != reported_size:
        logger.error(
            f"Claim of {reported_size} does not match size {packet_length}.  Returning empty result.",
        )
        return b""

    return packet


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
        physical_endpoint: PhysicalNetworkInterfaceClient | None = None,
        sniffer_endpoint: TCPSnifferServer | None = None,
    ):
        self.name = name
        self.tcp_endpoints = tcp_endpoints
        self.physical_endpoint = physical_endpoint
        self.sniffer_endpoint = sniffer_endpoint
        self._combined: list[ConnectionEndpoint] = self.tcp_endpoints  # type: ignore
        if self.physical_endpoint:
            self._combined.append(self.physical_endpoint)  # type: ignore
        if self.sniffer_endpoint:
            self._combined.append(self.sniffer_endpoint)  # type: ignore
        self.task: asyncio.Task | None = None

    async def connect(self):
        for endpoint, other_endpoint in itertools.permutations(self._combined, 2):
            other_endpoint.send_queues.append(endpoint.receive_queue)
        logger.debug(f"Awaiting tasks for connection {self.name}")
        await asyncio.gather(*[endpoint.connect() for endpoint in self._combined])


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
        logger.info(f"{self!s} Attempting to connect to port {self.port}")
        self.reader, self.writer = await asyncio.open_connection(
            self.ip_address,
            self.port,
        )
        await asyncio.gather(
            self.write_handler(self.writer),
            self.read_handler(self.reader),
        )

    async def read_handler(
        self,
        reader: asyncio.StreamReader,
    ):
        logger.info(f"{self!s} reading for {len(self.send_queues)} queues")
        while True:
            try:
                packet = await reader.read(MAX_READ)
                if not packet:
                    logger.error(f"{self!s} read empty packet.  Disconnecting.")
                    break
                logger.log(9, f"{self} read {len(packet)} bytes")
                queues = len(self.send_queues)
                for index, queue in enumerate(self.send_queues, start=1):
                    logger.log(9, f"{self!s} forwarding to queue {index} of {queues}")
                    await queue.put(packet)

            except ConnectionResetError:
                logger.error(f"{self!s}: Connection reset")
                break
            except asyncio.CancelledError:
                logger.error(f"{self!s}: Task Cancelled")
                break

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
                logger.debug(f"{self!s} received {len(packet)} bytes from queue")
                client_writer.write(packet)
                await client_writer.drain()
                logger.debug(f"{self!s} {len(packet)} bytes sent")

            except ConnectionResetError:
                stop = True
                logger.error(f"{self!s}: Connection reset")
            except asyncio.CancelledError:
                stop = True
                logger.error(f"{self!s}: Task Cancelled")
            except BaseException as exc:
                stop = True
                logger.error(f"Exception raised.  {exc!s}")
                raise


class PhysicalNetworkInterfaceClient:
    def __repr__(self):
        return f"{type(self).__name__}({self.interface})"

    def __init__(self, interface: str):
        self.interface = interface
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

        await asyncio.gather(
            self.write_physical(),
            self.read_physical(),
        )

    async def write_physical(self):

        while True:
            payload = await self.receive_queue.get()
            packet = get_packet_from_payload(payload)
            if not packet:
                logger.error(f"Physical received empty response from queue")
                continue
            logger.log(9, f"Physical forwarding {len(packet)} to interface")
            self.socket.send(packet)

    async def read_physical(self):
        loop = asyncio.get_running_loop()
        while True:
            packet = await loop.sock_recv(self.socket, MAX_READ)
            logger.log(9, f"Physical packet of length {len(packet)} from interface")
            queues = len(self.send_queues)
            payload = get_payload_from_packet(packet)
            for index, queue in enumerate(self.send_queues, start=1):
                logger.log(
                    9,
                    f"Sending payload of length {len(payload)} to queue {index} of {queues}",
                )
                await queue.put(payload)


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
            payload = await self.receive_queue.get()
            if not self.capture_queues:
                logger.log(9, f"Discarding payload of {len(payload)}.  Empty Queue")
            packet = get_packet_from_payload(payload)
            pcap = PCAP.get_pcap_from_packet(packet)
            forwarding_queues = len(self.capture_queues)
            for index, capture_queue in enumerate(self.capture_queues, start=1):
                logger.log(
                    9,
                    f"Forwarding pcap of {len(pcap)} to client {index} of {forwarding_queues}",
                )
                await capture_queue.put(pcap)

    async def connect(self):
        logger.info(f"Starting TCP Sniffer server")
        server = asyncio.start_server(
            self.start_session,
            host=self.bind_address,
            port=self.port,
            limit=MAX_CAPTURE_CONNECTIONS,
        )

        await asyncio.gather(
            server,
            self.forward_payloads_to_sessions(),
        )

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
                packet = await queue.get()
                logger.log(9, f"Received packet of {len(packet)} received.  Writing")
                client_writer.write(packet)
                await client_writer.drain()

            except ConnectionResetError:
                logger.error(f"Connection reset.  Breaking")
                break
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
    await connection.connect()


def start_bridge(
    name: str,
    log_file: str,
    tcp_endpoints: list[str],
    physical_endpoint: str,
    sniffer_endpoint: str,
    debug: bool = False,
):
    common.set_logging(debug, file=log_file)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    tcp_instances = []

    physical_instance = None
    if physical_endpoint:
        physical_instance = PhysicalNetworkInterfaceClient(physical_endpoint)
    sniffer_instance = None
    if sniffer_endpoint:
        try:
            host, port = sniffer_endpoint.split(":")
            port = int(port)
            ipaddress.IPv4Address(host)
        except Exception as exc:
            error_exit(
                f"Invalid input: {sniffer_endpoint!r} {type(exc).__name__}: {exc!s}",
            )
        sniffer_instance = TCPSnifferServer(port=port, bind_address=host)

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
            sniffer_endpoint=sniffer_instance,
        )
        asyncio.run(connect(bridge))
        error_exit("exiting")

    except Exception as exc:
        error_exit(f"Problem! {type(exc).__name__}: {exc!s}")
