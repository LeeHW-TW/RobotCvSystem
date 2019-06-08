import asyncio
import socket
import struct
import errno
import logging

logger = logging.getLogger('SSDP')

SSDP_ADDR = '239.255.255.250'
SSDP_PORT = 1900
TYPE = 'urn:pirobot-huww98-cn:device:PiRobot:1'

# Mainly used to debug on PC
# Choose the correct inteface to use
LOCAL_ADDR = '0.0.0.0'

class ProtocolSSDP(asyncio.DatagramProtocol):
    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data: bytes, addr):
        lines = data.decode().splitlines()
        if lines[0] != 'M-SEARCH * HTTP/1.1':
            return
        st = [l for l in lines if l.startswith('ST:')]
        if len(st) != 1:
            return
        st = st[0][3:].strip()
        if st != TYPE:
            return

        logger.info('SEARCH received from %s', addr)
        # Response
        response = '\r\n'.join([
            'HTTP/1.1 200 OK',
            'Cache-Control: max-age=20',
            'EXT',
            'ST: ' + TYPE,
            '\r\n'
        ])
        logger.info('Sending response to %s', addr)

        self.transport.sendto(response.encode(), addr)

    def error_received(self, exc):
        if exc in  [errno.EAGAIN, errno.EWOULDBLOCK]:
            logger.error('Error received: %s', exc)
        else:
            raise IOError("Unexpected connection error") from exc

class SSDPService:
    def __init__(self):
        self.stopped = False

    def start(self):
        self.stopped = False
        return asyncio.gather(self.ssdp_response(), self.ssdp_notify())

    def stop(self):
        self.stopped = True

    async def ssdp_response(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        mreq = struct.pack('4s4s', socket.inet_aton(SSDP_ADDR), socket.inet_aton(LOCAL_ADDR))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            pass
        sock.bind(('', SSDP_PORT))
        loop = asyncio.get_event_loop()
        await loop.create_datagram_endpoint(ProtocolSSDP, sock=sock)
        logger.info("listening")

    async def ssdp_notify(self):
        loop = asyncio.get_event_loop()
        transport, protocol = await loop.create_datagram_endpoint(asyncio.DatagramProtocol,
                                                                  remote_addr=(SSDP_ADDR, SSDP_PORT),
                                                                  local_addr=(LOCAL_ADDR, 0))
        notify_message = '\r\n'.join([
            'NOTIFY * HTTP/1.1',
            'Host: {}:{}'.format(SSDPService, SSDP_PORT),
            'Cache-Control: max-age=20',
            'NT: ' + TYPE,
            'NTS: ssdp:alive',
            '\r\n'
        ])
        logger.info('Start sending NOTIFY')

        def send_notify():
            logger.debug('Sending alive NOTIFY')
            transport.sendto(notify_message.encode())

        for _ in range(3):
            await asyncio.sleep(0.2)
            send_notify()
        while not self.stopped:
            await asyncio.sleep(10.0)
            send_notify()

        logger.info('End sending NOTIFY')
