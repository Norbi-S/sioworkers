from __future__ import absolute_import
from twisted.internet.protocol import ServerFactory
from twisted.internet import defer
from sio.protocol import rpc
from twisted.logger import Logger

log = Logger()


class DuplicateWorker(Exception):
    """A worker connected twice"""

class WorkerRejected(Exception):
    """This worker was rejected for some reason."""


class WorkerServer(rpc.WorkerRPC):
    def __init__(self):
        rpc.WorkerRPC.__init__(self, server=True)
        self.ready.addCallback(self.established)
        self.name = None
        self.uniqueID = None

    def established(self, ignore=None):
        addr = self.transport.getPeer()
        self.clientInfo['host'] = (addr.host, addr.port)
        self.name = self.clientInfo.get('name', '<unnamed>')
        self.uniqueID = '%s@%s:%d' % (self.name, addr.host, addr.port)
        log.info('{addr!s} connected, name: {name}',
                addr=addr, name=self.name)
        return self.factory.workerConnected(self)

    def connectionLost(self, reason):
        rpc.WorkerRPC.connectionLost(self, reason)
        self.factory.workerDisconnected(self)
        log.info('{addr!s} disconnected, reason: {reason!r}',
                addr=self.transport.getPeer(), reason=reason)

class WorkerServerFactory(ServerFactory):
    protocol = WorkerServer
    workers = {}

    def __init__(self, manager):
        self.manager = manager
        self.ignore_set = set()

    @defer.inlineCallbacks
    def workerConnected(self, proto):
        self.workers[proto.uniqueID] = proto
        try:
            yield self.manager.newWorker(proto.uniqueID, proto)
        except (DuplicateWorker, WorkerRejected):
            self.ignore_set.add(proto.uniqueID)
            raise

    def workerDisconnected(self, proto):
        if proto.uniqueID in self.ignore_set:
            self.ignore_set.remove(proto.uniqueID)
            return
        del self.workers[proto.uniqueID]
        self.manager.workerLost(proto)
