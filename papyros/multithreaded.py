'''A multithreaded implementation of the papyros API.'''

__all__ = ['MultiThreadedTaskDispatcher', 'MultiThreadedWorker', 'detect_cpus']

import os
import time
import weakref
from threading import Thread

from papyros import log
from papyros.base import TaskDispatcher, Worker, ClosedTaskDispatcherError


class MultiThreadedTaskDispatcher(TaskDispatcher):
    '''A multithreaded L{TaskDispatcher}.

    Each worker of this dispatcher is a separate thread.
    '''

    def __init__(self, size=0, num_workers=0, timeout=1.0):
        '''Initialize this dispatcher.

        @param size: See L{TaskDispatcher.__init__}.
        @param num_workers: The number of worker threads.
        @param timeout: How long does each worker wait for a task to be assigned
            on each loop.
        '''
        TaskDispatcher.__init__(self, size)
        if not num_workers:
            num_workers = detect_cpus()
        self.__workers = [MultiThreadedWorker(self, timeout, 'Worker-%d' % i)
                         for i in xrange(num_workers)]
        for worker in self.__workers:
            worker.start()
        log.debug('%s started %d worker threads', self, num_workers)


class MultiThreadedWorker(Thread, Worker):
    '''A L{Worker} implemented as a daemon thread.'''

    def __init__(self, dispatcher, timeout, name=None):
        '''Initialize this worker.

        @param dispatcher: If not None, L{connect} to this dispatcher.
        @param timeout: How long does this worker wait for a task to be assigned
            on each loop.
        @param name: The name of this thread.
        '''
        Thread.__init__(self, name=name)
        Worker.__init__(self, weakref.proxy(dispatcher))
        self.__timeout = timeout
        self.setDaemon(True)

    def run(self):
        '''Task execution loop.

        Executes assigned tasks continuously until disconnected.
        '''
        timeout = self.__timeout
        while self.is_connected():
            try:
                if not self.execute_task():
                    time.sleep(timeout)
            except (ClosedTaskDispatcherError, weakref.ReferenceError):
                self.disconnect()


def detect_cpus():
    '''Detect the number of CPUs on this machine.'''
    # Linux, Unix and MacOS
    if hasattr(os, 'sysconf'):
        if 'SC_NPROCESSORS_ONLN' in os.sysconf_names:
            # Linux & Unix
            ncpus = os.sysconf('SC_NPROCESSORS_ONLN')
            if isinstance(ncpus, int) and ncpus > 0:
                return ncpus
        else: # OSX
            return int(os.popen2('sysctl -n hw.ncpu')[1].read())
    # Windows
    if 'NUMBER_OF_PROCESSORS' in os.environ:
            ncpus = int(os.environ['NUMBER_OF_PROCESSORS']);
            if ncpus > 0:
                return ncpus
    return 1 # default
