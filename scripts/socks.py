import socket
import ssl
import select
import threading
import os
import argparse
import logging
import resource

from urllib.parse import urlparse
from typing import List, Tuple, Union, Optional
from enum import Enum

__author__ = 'Glemison C. Dutra'
__version__ = '1.0.2'

resource.setrlimit(resource.RLIMIT_NOFILE, (65536, 65536))

logger = logging.getLogger(__name__)

DEFAULT_RESPONSE = b'HTTP/1.1 101 Connection Established\r\n\r\n'
REMOTES_ADDRESS = {
    'ssh': ('0.0.0.0', 22),
    'openvpn': ('0.0.0.0.0', 1194),
    'v2ray': ('0.0.0.0', 1080),
}


class Counter:
    def __init__(self):
        self.__count = 0

    def increment(self):
        self.__count += 1

    def decrement(self):
        self.__count -= 1

    @property
    def count(self):
        return self.__count


class ConnectionCounter:
    __counter = Counter()
    __lock = threading.Lock()

    @classmethod
    def increment(cls):
        with cls.__lock:
            cls.__counter.increment()

    @classmethod
    def decrement(cls):
        with cls.__lock:
            cls.__counter.decrement()

    @classmethod
    def count(cls):
        with cls.__lock:
            return cls.__counter.count


connection_counter = ConnectionCounter()


class RemoteTypes(Enum):
    SSH = 'ssh'
    OPENVPN = 'openvpn'
    V2RAY = 'v2ray'


class ParserType:
    def __init__(self, data: bytes) -> None:
        if not isinstance(data, bytes):
            raise TypeError('data must be bytes')

        self.data = data
        self.type = None
        self.address = None

    def parse(self) -> None:
        if self.data.startswith(b'\x0068'):
            self.type = RemoteTypes.OPENVPN
            self.address = REMOTES_ADDRESS[self.type.value]
            return

        if self.data.startswith(b'\x00'):
            self.type = RemoteTypes.V2RAY
            self.address = REMOTES_ADDRESS[self.type.value]

        if self.data.startswith(b'SSH-'):
            self.type = RemoteTypes.SSH
            self.address = REMOTES_ADDRESS[self.type.value]


class HttpParser:
    def __init__(self) -> None:
        self.method = None
        self.body = None
        self.url = None
        self.headers = {}

    def parse(self, data: bytes) -> None:
        data = data.decode('utf-8')
        lines = data.split('\r\n')

        self.method, self.url, self.version = lines[0].split()
        self.url = urlparse(self.url)

        self.headers.update(
            {k: v.strip() for k, v in [line.split(':', 1) for line in lines[1:] if ':' in line]}
        )

        self.body = (
            '\r\n'.join(lines[-1:])
            if not self.headers.get('Content-Length')
            else '\r\n'.join(lines[-1 : -1 * int(self.headers['Content-Length'])])
        )

    def build(self) -> bytes:
        base = f'{self.method} {self.url.path} {self.version}\r\n'
        headers = '\r\n'.join(f'{k}: {v}' for k, v in self.headers.items()) + '\r\n' * 2
        return base.encode('utf-8') + headers.encode('utf-8') + self.body.encode('utf-8')


class Connection:
    def __init__(self, conn: Union[socket.socket, ssl.SSLSocket], addr: Tuple[str, int]):
        self.__conn = conn
        self.__addr = addr
        self.__buffer = b''
        self.__closed = False

    @property
    def conn(self) -> Union[socket.socket, ssl.SSLSocket]:
        if not isinstance(self.__conn, (socket.socket, ssl.SSLSocket)):
            raise TypeError('Connection is not a socket')

        if not self.__conn.fileno() > 0:
            raise ConnectionError('Connection is closed')

        return self.__conn

    @conn.setter
    def conn(self, conn: Union[socket.socket, ssl.SSLSocket]):
        if not isinstance(conn, (socket.socket, ssl.SSLSocket)):
            raise TypeError('Connection is not a socket')

        if not conn.fileno() > 0:
            raise ConnectionError('Connection is closed')

        self.__conn = conn

    @property
    def addr(self) -> Tuple[str, int]:
        return self.__addr

    @addr.setter
    def addr(self, addr: Tuple[str, int]):
        self.__addr = addr

    @property
    def buffer(self) -> bytes:
        return self.__buffer

    @buffer.setter
    def buffer(self, data: bytes) -> None:
        self.__buffer = data

    @property
    def closed(self) -> bool:
        return self.__closed

    @closed.setter
    def closed(self, value: bool) -> None:
        self.__closed = value

    def close(self):
        self.conn.close()
        self.closed = True

    def read(self, size: int = 4096) -> Optional[bytes]:
        data = self.conn.recv(size)
        return data if len(data) > 0 else None

    def write(self, data: Union[bytes, str]) -> int:
        if isinstance(data, str):
            data = data.encode()

        if len(data) <= 0:
            raise ValueError('Write data is empty')

        return self.conn.send(data)

    def queue(self, data: Union[bytes, str]) -> int:
        if isinstance(data, str):
            data = data.encode()

        if len(data) <= 0:
            raise ValueError('Queue data is empty')

        self.__buffer += data
        return len(data)

    def flush(self) -> int:
        sent = self.write(self.__buffer)
        self.__buffer = self.__buffer[sent:]
        return sent


class Client(Connection):
    def __str__(self):
        return f'Cliente - {self.addr[0]}:{self.addr[1]}'


class Server(Connection):
    def __str__(self):
        return f'Servidor - {self.addr[0]}:{self.addr[1]}'

    @classmethod
    def of(cls, addr: Tuple[str, int]) -> 'Server':
        return cls(socket.socket(socket.AF_INET, socket.SOCK_STREAM), addr)

    def connect(self, addr: Tuple[str, int] = None, timeout: int = 5) -> None:
        self.addr = addr or self.addr
        self.conn = socket.create_connection(self.addr, timeout)
        self.conn.settimeout(None)

        logger.debug(f'{self} Conexão estabelecida')


class Proxy(threading.Thread):
    def __init__(self, client: Client, server: Optional[Server] = None) -> None:
        super().__init__()

        self.client = client
        self.server = server

        self.http_parser = HttpParser()
        self.parser_type = ParserType(bytes())

        self.__running = False

    @property
    def running(self) -> bool:
        if self.server and self.server.closed and self.client.closed:
            self.__running = False
        return self.__running

    @running.setter
    def running(self, value: bool) -> None:
        self.__running = value

    def _process_request(self, data: bytes) -> None:
        if self.parser_type.type is not None and self.server and not self.server.closed:
            self.server.queue(data)
            return

        self.parser_type.data = data
        if self.parser_type.type is None:
            self.parser_type.parse()

        host, port = (None, None)
        if self.parser_type.type is not None:
            host, port = self.parser_type.address

        if self.parser_type.type is None:
            self.http_parser.parse(data)

            if self.http_parser.method == 'CONNECT':
                host, port = self.http_parser.url.path.split(':')

        if host is not None and port is not None:
            self.server = Server.of((host, int(port)))
            self.server.connect()

        if self.http_parser.method == 'CONNECT' or self.parser_type.type is None:
            self.client.queue(DEFAULT_RESPONSE)
        elif self.parser_type.type is not None and self.server and not self.server.closed:
            self.server.queue(data)
        elif self.server and not self.server.closed:
            self.server.queue(self.http_parser.build())

        if self.parser_type.type:
            logger.info(
                f'{self.client} -> Modo {self.parser_type.type.value.upper()} - {host}:{port}'
            )
        else:
            logger.info(f'{self.client} -> Solicitação: {self.http_parser.build()}')

    def _get_waitable_lists(self) -> Tuple[List[socket.socket]]:
        r, w, e = [self.client.conn], [], []

        if self.server and not self.server.closed:
            r.append(self.server.conn)

        if self.client.buffer:
            w.append(self.client.conn)

        if self.server and not self.server.closed and self.server.buffer:
            w.append(self.server.conn)

        return r, w, e

    def _process_wlist(self, wlist: List[socket.socket]) -> None:
        if self.client.conn in wlist:
            sent = self.client.flush()
            logger.debug(f'{self.client} enviou {sent} Bytes')

        if self.server and not self.server.closed and self.server.conn in wlist:
            sent = self.server.flush()
            logger.debug(f'{self.server} enviou {sent} Bytes')

    def _process_rlist(self, rlist: List[socket.socket]) -> None:
        if self.client.conn in rlist:
            data = self.client.read()
            self.running = data is not None
            if data and self.running:
                self._process_request(data)
                logger.debug(f'{self.client} recebeu {len(data)} Bytes')

        if self.server and not self.server.closed and self.server.conn in rlist:
            data = self.server.read()
            self.running = data is not None
            if data and self.running:
                self.client.queue(data)
                logger.debug(f'{self.server} recebeu {len(data)} Bytes')

    def _process(self) -> None:
        self.running = True

        while self.running:
            rlist, wlist, xlist = self._get_waitable_lists()
            r, w, _ = select.select(rlist, wlist, xlist, 1)

            self._process_wlist(w)
            self._process_rlist(r)

    def run(self) -> None:
        try:
            logger.info(f'{self.client} Conectado')
            self._process()
        except Exception as e:
            logger.exception(f'{self.client} Erro: {e}')
        finally:
            self.client.close()
            if self.server and not self.server.closed:
                self.server.close()

            logger.info(f'{self.client} Desconectado')


class TCP:
    def __init__(self, addr: Tuple[str, int] = None, backlog: int = 5):
        self.__addr = addr
        self.__backlog = backlog

        self.__sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def handle(self, conn: socket.socket, addr: Tuple[str, int]) -> None:
        raise NotImplementedError()

    def run(self) -> None:
        self.__sock.bind(self.__addr)
        self.__sock.listen(self.__backlog)

        logger.info(f'Servidor iniciado em {self.__addr[0]}:{self.__addr[1]}')

        try:
            while True:
                conn, addr = self.__sock.accept()
                self.handle(conn, addr)
        except KeyboardInterrupt:
            pass
        finally:
            logger.info('Finalizando servidor...')
            self.__sock.close()


class HTTP(TCP):
    def handle(self, conn: socket.socket, addr: Tuple[str, int]) -> None:
        client = Client(conn, addr)
        proxy = Proxy(client)
        proxy.daemon = True
        proxy.start()


class HTTPS(TCP):
    def __init__(self, addr: Tuple[str, int], cert: str, backlog: int = 5) -> None:
        super().__init__(addr, backlog)

        self.__cert = cert

    def handle_thread(self, conn: socket.socket, addr: Tuple[str, int]) -> None:
        conn = ssl.wrap_socket(
            sock=conn,
            keyfile=self.__cert,
            certfile=self.__cert,
            server_side=True,
            ssl_version=ssl.PROTOCOL_TLSv1_2,
        )

        client = Client(conn, addr)
        proxy = Proxy(client)
        proxy.daemon = True
        proxy.start()

    def handle(self, conn: socket.socket, addr: Tuple[str, int]) -> None:
        thread = threading.Thread(target=self.handle_thread, args=(conn, addr))
        thread.daemon = True
        thread.start()


def main():
    parser = argparse.ArgumentParser(description='Proxy', usage='%(prog)s [options]')

    parser.add_argument('--host', default='0.0.0.0', help='Host')
    parser.add_argument('--port', type=int, default=8080, help='Port')
    parser.add_argument('--backlog', type=int, default=5, help='Backlog')
    parser.add_argument('--openvpn-port', type=int, default=1194, help='OpenVPN Port')
    parser.add_argument('--ssh-port', type=int, default=22, help='SSH Port')
    parser.add_argument('--v2ray-port', type=int, default=1080, help='V2Ray Port')

    parser.add_argument('--cert', default='./cert.pem', help='Certificate')

    parser.add_argument('--http', action='store_true', help='HTTP')
    parser.add_argument('--https', action='store_true', help='HTTPS')

    parser.add_argument('--log', default='INFO', help='Log level')
    parser.add_argument('--usage', action='store_true', help='Usage')

    args = parser.parse_args()

    REMOTES_ADDRESS['openvpn'] = (args.host, args.openvpn_port)
    REMOTES_ADDRESS['ssh'] = (args.host, args.ssh_port)
    REMOTES_ADDRESS['v2ray'] = (args.host, args.v2ray_port)

    server = None

    if args.http:
        server = HTTP((args.host, args.port), args.backlog)

    if args.https:
        if not os.path.exists(args.cert):
            raise FileNotFoundError(f'Certicado {args.cert} não encontrado')

        server = HTTPS((args.host, args.port), args.cert, args.backlog)

    if server is None:
        parser.print_help()
        return

    logging.basicConfig(
        level=getattr(logging, args.log.upper()),
        format='[%(asctime)s] %(levelname)s: %(message)s',
    )

    server.run()


if __name__ == '__main__':
    main()
