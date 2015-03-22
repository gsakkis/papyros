'''A distributed process implementation of the papyros API.

Both the L{TaskDispatcher} and each L{Worker} is a separate process, running on
one or more interconnected machines.

@requires: U{Pyro 3.7 <http://pyro.sourceforge.net/>}.
'''

__all__ = [
    'NonRemoteMethodError', 'set_nameserver', 'PyroTaskDispatcher', 'PyroWorker'
]

import os
import time
import socket
import traceback

import Pyro, Pyro.core, Pyro.naming
from Pyro.errors import NamingError, ConnectionClosedError, ProtocolError

from papyros import log
from papyros.base import TaskDispatcher, TaskQueue, Worker, ClosedTaskDispatcherError

PYRO_DAEMON = None
ROOT_GROUP = ':Papyros'
NAME_SERVER_LOCATOR = None


class NonRemoteMethodError(Exception):
    '''Tried to call remotely a method allowed to be called locally only.'''

def set_nameserver(host=None, port=None):
    '''Specify the Pyro NameServer address.

    If this function is not called, the NameServer is attempted to be discovered
    automatically by a broadcast lookup.

    @param host: The hostname that is initially tried to find the NameServer on,
        or when the broadcast lookup mechanism fails.
    @param port: The socket number on which the Name Server will listen for
        incoming requests.
    '''
    if host: Pyro.config.PYRO_NS_HOSTNAME = host
    if port: Pyro.config.PYRO_NS_PORT = port

#========== PyroTaskDispatcher =================================================

class PyroTaskDispatcher(TaskDispatcher, Pyro.core.ObjBase):
    '''A L{TaskDispatcher} run as a (potentially remote) process.'''

    def __init__(self, size=0, group=None):
        '''Initialize this dispatcher.

        @param size: See L{TaskDispatcher.__init__}.
        @param group: The identifier of this dispatcher's distributed group.
        '''
        init_pyro(server=True)
        TaskDispatcher.__init__(self, size)
        Pyro.core.ObjBase.__init__(self)
        self.__name = self._get_name(group)

    @classmethod
    def get_proxy(cls, group=None):
        '''Get a proxy object to a running L{PyroTaskDispatcher}.

        @param group: The identifier of the dispatcher's distributed group.
        '''
        init_pyro(server=False)
        proxy = NAME_SERVER_LOCATOR.getNS().resolve(cls._get_name(group)).getProxy()
        proxy.__class__ = PyroTaskDispatcherProxy # XXX HACK
        return proxy

    def run(self):
        '''Start the event loop of this dispatcher.'''
        uri = register(self, self.__name, force=True)
        log.info('%s is now registered (%s)', self, uri)
        try:
            try: PYRO_DAEMON.requestLoop()
            except KeyboardInterrupt:
                log.info('%s exiting gracefully', self)
        finally:
            PYRO_DAEMON.disconnect(self)
            PYRO_DAEMON.shutdown()

    def __str__(self):
        return self.__name

    def _make_queue(self, size=0):
        return PyroTaskQueue(self,size)

    @classmethod
    def _get_name(cls, group=None):
        '''Return the full name of a L{PyroTaskDispatcher}.

        @param group: The identifier of the dispatcher's distributed group.
        '''
        parts = [ROOT_GROUP, 'Dispatcher']
        if group: parts.insert(1, group)
        return '.'.join(parts)


class PyroTaskDispatcherProxy(Pyro.core.DynamicProxy):
    '''A proxy class of L{PyroTaskDispatcher}.

    Clients interact with instances of this class instead of actual
    L{PyroTaskDispatcher} instances. The differences are that L{execute} is
    invoked locally on the client and that L{close} and L{run} are not
    accesible remotely.
    '''
    execute = PyroTaskDispatcher.execute.im_func
    def run(self): raise NonRemoteMethodError()
    def close(self): raise NonRemoteMethodError()

#========== PyroTaskQueue ======================================================

class PyroTaskQueue(TaskQueue, Pyro.core.ObjBase):
    '''A L{TaskQueue} used for distributed execution.'''

    def __init__(self, dispatcher, size=0):
        init_pyro(server=True)
        TaskQueue.__init__(self, dispatcher, size)
        Pyro.core.ObjBase.__init__(self)
        PYRO_DAEMON.connect(self)

    def close(self):
        try: TaskQueue.close(self)
        finally: PYRO_DAEMON.disconnect(self)

    def _get_proxy(self):
        '''Return a proxy to this queue as it is to be known by its dispatcher.'''
        proxy = self.getProxy()
        proxy.__class__ = PyroTaskQueueProxy # XXX HACK
        return proxy


class PyroTaskQueueProxy(Pyro.core.DynamicProxy):
    '''A proxy class of L{PyroTaskQueue}.

    The only difference is that Pyro exceptions on remote calls to L{close} are
    silently ignored.
    '''
    def close(self):
        try: return self.__getattr__('close')()
        except (ProtocolError, ConnectionClosedError): pass

#========== PyroWorker =========================================================

class PyroWorker(Worker, Pyro.core.ObjBase):
    '''A L{Worker} run as a (potentially remote) process.'''

    def __init__(self, group=None):
        '''Initialize this worker.

        @param group: The identifier of this worker's distributed group.
        '''
        Worker.__init__(self)
        Pyro.core.ObjBase.__init__(self)
        self.__group = group
        self.__name = self._get_name(group)

    def __str__(self):
        return self.__name

    def run(self, timeout=10.0, tracebacks=False):
        '''Connect this worker to the dispatcher of its group and keep executing
        available tasks forever.
        '''
        init_pyro(server=True)
        name = str(self)
        dispatcher_name = PyroTaskDispatcher._get_name(self.__group)
        uri = register(self, name, force=True)
        log.info('%s is now registered (%s)', name, uri)
        while True:
            try:
                if not self.is_connected():
                    self.connect(PyroTaskDispatcher.get_proxy(self.__group))
                    log.info('%s connected to %s', name, dispatcher_name)
                if not self.execute_task():
                    time.sleep(timeout)
            except KeyboardInterrupt:
                log.info('%s exiting gracefully', name)
                break
            except Exception, ex:
                if tracebacks:
                    log.error(traceback.format_exc())
                else:
                    log.error(''.join(traceback.format_exception_only(ex.__class__,ex)))
                if self.is_connected():
                    self.disconnect()
                    log.info('%s disconnected from %s', name, dispatcher_name)
                time.sleep(timeout)
        PYRO_DAEMON.disconnect(self)

    @classmethod
    def _get_name(cls, group=None):
        '''Return the full name of a L{PyroWorker}.

        @param group: The identifier of the workers's distributed group.
        '''
        parts = [ROOT_GROUP, 'Worker', '%s.%d' % (socket.gethostname(), os.getpid())]
        if group: parts.insert(1, group)
        return '.'.join(parts)

#========== module privates ====================================================

def register(obj, name, force=False):
    '''Register C{obj} to the C{PYRO_DAEMON} with the given C{name}.

    @param obj: An C{ObjBase} instance.
    @param name: The fully qualified object's name. If it is a dotted name (e.g.
        'my.object.name' it creates all necessary intermedieate nameserver
        groups ('my', 'my.object').
    @param force: If False and there is already an entry for the given name,
        C{NamingError} is raised. If True, the previous object is unregistered
        and C{obj} is registered in its place.
    '''
    nameserver = NAME_SERVER_LOCATOR.getNS()
    parts = name.split('.')[:-1]
    if parts:
        group = parts.pop(0)
        while True:
            try: nameserver.createGroup(group)
            except NamingError: pass
            if not parts:
                break
            group += '.%s' % parts.pop(0)
    # unregister previous object with this name (if any)
    try: nameserver.resolve(name)
    except NamingError: pass
    else:
        if force:
            nameserver.unregister(name)
        else:
            raise NamingError('Name %s is already registered' % name)
    return PYRO_DAEMON.connect(obj, name)

def init_pyro(server):
    '''Ensure Pyro is initialized (or initialize it if not).

    @param server: If True, initialize Pyro as a server, otherwise as a client.
    '''
    global PYRO_DAEMON, NAME_SERVER_LOCATOR
    if PYRO_DAEMON is None:
        (server and Pyro.core.initServer or Pyro.core.initClient)(banner=False)
        PYRO_DAEMON = Pyro.core.Daemon()
        NAME_SERVER_LOCATOR = Pyro.naming.NameServerLocator()
        PYRO_DAEMON.useNameServer(NAME_SERVER_LOCATOR.getNS())
