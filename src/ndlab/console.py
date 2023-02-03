from __future__ import annotations
import logging
import telnetlib
import typing as T

import ndlab.common as common

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WAIT_CYCLE_LIMIT = 100
WAIT_CYCLE_TIMEOUT = 15
DEFAULT_WAIT_STR = object()


class ConsoleDumper:
    def __init__(
        self,
        port: int,
        hostname: str = common.LOCALHOST,
        username: str | None = common.DEFAULT_USERNAME,
        password: str | None = common.DEFAULT_PASSWORD,
        wait_str: bytes = b"#",
        tail: bytes = b"\r\n",
        expects: dict[bytes, bytes] = {},
        save_wait: tuple[bytes, ...] | None = None,
        device_build_steps: T.Callable[[ConsoleDumper], None] | None = None,
        device_save_steps: T.Callable[[ConsoleDumper], None] | None = None,
    ):
        self.port = port
        self.hostname = hostname
        self.username = username
        self.password = password
        self.wait_str = wait_str
        self.tail = tail
        self.expects = expects
        self.save_wait = save_wait
        self.device_build_steps = device_build_steps
        self.device_save_steps = device_save_steps

        self.started = False
        self.trigger_handlers = {}
        self.handlers_by_index = {}
        self.ip_address = None
        self.telnet = telnetlib.Telnet()
        self.expect_list = list(e for e in self.expects)
        self.respond_by_index = {
            i: handler for i, handler in enumerate(self.expects.values())
        }

    def knock(self):
        KNOCKS = 1
        logger.info(f"Knocking.  Sending {self.tail!r} * {KNOCKS}")
        for _ in range(KNOCKS):
            self.telnet.write(self.tail)

    def expect(self):
        # todo: rewrite this to be less clever and more functional
        if not self.telnet:
            raise RuntimeError(f"No active telnet session")
        if not self.started:
            self.knock()
        idx, match, result = self.telnet.expect(self.expect_list, WAIT_CYCLE_TIMEOUT)
        logger.info(f"Received: {result!r}")
        if not match:
            logger.info("No match")
            self.knock()
            return
        self.started = True
        response = self.respond_by_index[idx]
        if response is common.DEVICE_IS_READY:
            logger.info(f"Device is ready to be configured")
            return True
        if response is common.DEVICE_REQUIRES_BUILD and self.device_build_steps is None:
            raise RuntimeError(f"device build steps not defined")
        elif response is common.DEVICE_REQUIRES_BUILD and self.device_build_steps:
            logger.info(f"Device requires build steps")
            self.device_build_steps(self)
            return True

        logger.info(f"Sending: {response!r}")
        self.telnet.write(response + self.tail)

    def wait_until_ready(self):
        for attempt_no in range(1, WAIT_CYCLE_LIMIT + 1):
            logger.debug(
                f"{attempt_no} of {WAIT_CYCLE_LIMIT}: Running expect cycle. Waiting {WAIT_CYCLE_TIMEOUT} seconds.",
            )
            if self.expect():
                break
        else:
            raise RuntimeError("Device was never ready")

    def save(self):
        if self.save_wait is None:
            logger.info("No SAVE_WAIT configured")
            return

        self.write_wait(*self.save_wait)

    def _wait_config(
        self,
        show_command: str,
        expected_output: str,
    ):
        show_command_b = show_command.encode()
        expected_output_b = expected_output.encode()
        for attempt_no in range(1, WAIT_CYCLE_LIMIT + 1):
            logger.debug(
                f"{attempt_no} of {WAIT_CYCLE_LIMIT}: "
                f"Running {show_command!r} looking for {expected_output!r}. "
                f"Waiting {WAIT_CYCLE_TIMEOUT} seconds.",
            )
            self.write_wait(show_command_b, wait_str=None)
            response = self.telnet.read_until(
                expected_output_b,
                timeout=WAIT_CYCLE_TIMEOUT,
            )
            logger.debug(f"Received {response!r}")
            if expected_output_b in response:
                logger.info(f"Found: {expected_output}")
                return True
        raise RuntimeError(f"Ran {show_command!r} and never found {expected_output!r}")

    def write_wait(
        self,
        line: bytes,
        *,
        wait_str: bytes | None | object = DEFAULT_WAIT_STR,
        timeout: int = WAIT_CYCLE_TIMEOUT,
    ):
        if not self.telnet:
            raise RuntimeError("No telnet")
        if wait_str is DEFAULT_WAIT_STR:
            wait_str = self.wait_str

        if wait_str is None:
            logger.debug(f"Writing {line!r} without waiting")
        else:
            logger.debug(f"Writing {line!r} and waiting for {wait_str!r}")

        self.telnet.write(line + self.tail)
        if wait_str and wait_str is not DEFAULT_WAIT_STR:
            wait_str = T.cast(bytes, wait_str)
            resultb = self.telnet.read_until(wait_str, timeout)
            result = resultb.decode("ascii")
            if wait_str not in resultb:
                logger.error(f"{wait_str!r} not found in {result!r}")
            logger.debug(f"Received: {result!r}")

    def send_config(self, config: list[str]):
        try:
            self.telnet.open(self.hostname, self.port)
            self.wait_until_ready()
            for line in config:
                logger.debug(f"Sending line: {line}")
                lineb = line.encode()
                self.write_wait(lineb)
            if self.device_save_steps:
                self.device_save_steps(self)
        finally:
            self.telnet.close()
