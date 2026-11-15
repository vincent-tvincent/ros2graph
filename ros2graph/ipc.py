"""Bounded JSON frames for local graph metadata; no application command client."""
import json
import struct

MAX_BYTES=16*1024*1024

def receive(sock):
    def exact(count):
        data=bytearray()
        while len(data)<count:
            part=sock.recv(count-len(data))
            if not part:raise EOFError()
            data.extend(part)
        return bytes(data)
    size=struct.unpack('!I',exact(4))[0]
    if size>MAX_BYTES:raise ValueError('Graph IPC message too large')
    return json.loads(exact(size))

def send(sock,value):
    data=json.dumps(value,allow_nan=False,separators=(',',':')).encode()
    if len(data)>MAX_BYTES:raise ValueError('Graph IPC response too large')
    sock.sendall(struct.pack('!I',len(data))+data)
