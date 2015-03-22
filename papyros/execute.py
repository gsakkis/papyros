'''Implementation of L{TaskDispatcher.execute}.

Normally there is no need to be imported directly by clients.
'''

__all__ = ['ExecuteIterator']

import heapq
import threading
from copy import copy
from itertools import takewhile, imap, starmap, islice, repeat

from papyros.task import Task

try: from Pyro.core import DynamicProxy
except ImportError:
    def get_proxy(obj): return obj
else:
    # Pyro proxies cannot be shared across threads by default; they must be copied
    def get_proxy(obj):
        if isinstance(obj, DynamicProxy): return copy(obj)
        else: return obj

#========== ExecuteIterator ====================================================

class ExecuteIterator(object):
    '''An iterator over results of executed tasks.'''

    def __init__(self, task_queue, tasks, timeout=None, ordered=False, chunksize=1):
        '''Initialize this iterator.

        @param task_queue: The L{TaskQueue} to push the given tasks and pop the
            task results from.
        @param tasks, timeout, ordered, chunksize: See L{TaskDispatcher.execute}.
        '''
        executioner = DefaultTaskExecutioner(task_queue,timeout)
        # the order is important: first apply the CompositeExecutionDecorator
        # (if necessary) and then the OrderedExecutionDecorator (if necessary)
        # so that tasks are first ordered and then bundled into chunks (decorators
        # are called in the reverse order they are applied)
        if chunksize > 1:
            executioner= CompositeExecutionDecorator(executioner,chunksize)
        if ordered:
            executioner = OrderedExecutionDecorator(executioner)
        executioner.submit(executioner.adapt_tasks(tasks))
        self.__executioner = executioner

    def __iter__(self): return self
    def next(self): return self.__executioner.next()
    def close(self): return self.__executioner.close()
    __del__ = close

#========== TaskExecutioner ====================================================

class TaskExecutioner(object):
    '''Abstract base class for iterators over results of executed tasks.

    Mainly for documentation reasons, not strictly necessary in Python.
    '''
    def __iter__(self):
        return self

    def next(self):
        '''Return the result of an executed task.

        @raises StopIteration: If all results have been returned.
        '''
        raise NotImplementedError('Abstract method')

    def submit(self, tasks):
        '''Submit the given tasks to this iterator to execute them in the
        background.

        This can be effectively called only once for a given L{TaskExecutioner}.
        '''
        raise NotImplementedError('Abstract method')

    def adapt_tasks(self, tasks):
        '''Intended for subclasses that expect tasks to be adapted somehow before
        being submitted. By default it just returns the given tasks.
        '''
        return tasks

    def close(self):
        '''Perform any necessary cleanup.'''
        pass

#========== DefaultTaskExecutioner =============================================

class DefaultTaskExecutioner(TaskExecutioner):
    '''Principal task execution iterator.'''

    def __init__(self, task_queue, timeout=None):
        '''Initialize this iterator.

        @param task_queue: See L{ExecuteIterator.__init__}.
        @param timeout: See L{TaskDispatcher.execute}.
        '''
        self.__task_queue = get_proxy(task_queue)
        self.__timeout = timeout
        self.__started = False
        self.__finished = False
        self.__remaining = 0
        self.__condition = threading.Condition()

    def next(self):
        '''Pop and return a finished result from the L{TaskQueue}.

        @raises TimeoutError: If a L{timeout <__init__>} was specified and it
            expires before a result is available.
        '''
        condition = self.__condition
        while True:
            condition.acquire()
            try:
                if self.__remaining > 0: # there is a pending item; return it
                    self.__remaining -= 1
                    break
                elif self.__finished:   # no pending items and producer is done
                    raise StopIteration()
                else:                   # no pending items but producer not done
                    condition.wait()
            finally:
                condition.release()
        return self.__task_queue.pop(self.__timeout)

    def submit(self, tasks):
        '''Starts a new thread for pushing the given tasks to the L{TaskQueue}.'''
        condition = self.__condition
        def produce_all():
            try:
                produce = get_proxy(self.__task_queue).push
                for task in tasks:
                    condition.acquire()
                    try:
                        if self.__finished: break
                        produce(task)
                        self.__remaining += 1
                        condition.notify()
                    finally:
                        condition.release()
            finally:
                self.__abort()
        condition.acquire()
        try:
            if not self.__started:
                producer = threading.Thread(target=produce_all)
                producer.setDaemon(True)
                producer.start()
                self.__started = True
        finally:
            condition.release()

    def close(self):
        '''Cancels the submission of any still unsubmitted task and closes the
        L{TaskQueue}.
        '''
        self.__abort()
        # call task_queue.close() through a new proxy just to be on the safe
        # side since __del__ might be called from a different thread. Also guard
        # from exceptions since the queue might be gone already
        try: get_proxy(self.__task_queue).close()
        except: pass

    def __abort(self):
        '''Declares that no more tasks are going to be submitted.'''
        if not self.__finished:
            condition = self.__condition
            condition.acquire()
            try:
                self.__finished = True
                condition.notifyAll()
            finally:
                condition.release()

#========== TaskExecutionDecorator =============================================

class TaskExecutionDecorator(TaskExecutioner):
    '''Implements the decorator pattern for L{TaskExecutioner}s.

    This class delegates all calls to the decorated component.
    '''
    def __init__(self, executioner): self.__decorated = executioner
    def next(self): return self.__decorated.next()
    def adapt_tasks(self, tasks): return self.__decorated.adapt_tasks(tasks)
    def close(self): return self.__decorated.close()
    def submit(self, tasks): return self.__decorated.submit(tasks)

#========== OrderedExecutionDecorator ==========================================

@Task.subclass()
def IndexedTask(index, task):
    '''A task associated with an index.'''
    task.execute()
    return (index, task)

class OrderedExecutionDecorator(TaskExecutionDecorator):
    '''Decorates a L{TaskExecutioner} so that it yields results in the same order
    the respective tasks were submitted.
    '''

    def __init__(self, executioner):
        super(OrderedExecutionDecorator,self).__init__(executioner)
        self.__index = 0     # index of the next task to be yielded by next
        self.__pending = []  # heap of the returned (index, task) tuples

    def adapt_tasks(self, tasks):
        '''Wrap tasks as L{IndexedTask}s and pass them to the
        L{adapt_tasks <TaskExecutioner.adapt_tasks>} of the decorated component.
        '''
        indexed_tasks = starmap(IndexedTask, enumerate(tasks))
        return super(OrderedExecutionDecorator,self).adapt_tasks(indexed_tasks)

    def next(self):
        heappush = heapq.heappush
        pending, index = self.__pending, self.__index
        supernext = super(OrderedExecutionDecorator,self).next
        while not pending or pending[0][0] > index:
            try: heappush(pending, supernext())
            except StopIteration: break
        if pending:
            assert pending[0][0] == index, pending
            self.__index += 1
            return heapq.heappop(pending)[1].result()
        else:
            raise StopIteration()

#========== CompositeExecutionDecorator ========================================

@Task.subclass()
def CompositeTask(tasks):
    '''A task composed of other subtasks.'''
    for task in tasks: task.execute()
    return tasks

class CompositeExecutionDecorator(TaskExecutionDecorator):
    '''Decorates a L{TaskExecutioner} so that it bundles tasks into chunks
    of a given size.
    '''

    def __init__(self, executioner, chunksize):
        super(CompositeExecutionDecorator,self).__init__(executioner)
        self.__chunksize = chunksize
        self.__chunk = []

    def adapt_tasks(self, tasks):
        '''Wrap tasks as L{CompositeTask}s and pass them to the
        L{adapt_tasks <TaskExecutioner.adapt_tasks>} of the decorated component.
        '''
        composite_tasks = imap(CompositeTask, iterchunks(tasks, self.__chunksize))
        return super(CompositeExecutionDecorator,self).adapt_tasks(composite_tasks)

    def next(self):
        if not self.__chunk:
            self.__chunk.extend(super(CompositeExecutionDecorator,self).next())
        try: task = self.__chunk.pop()
        except IndexError:
            raise StopIteration()
        return task.result()


def iterchunks(iterable, chunksize, chunktype=list):
    '''Break C{iterable} into chunks of C{chunksize}.

    @type chunksize: int
    @param chunksize: The size of each chunk. The last chunk (in case of finite
        iterables) may actually be smaller.
    @param chunktype: A container type for the chunks. It must be a callable
        f(iterable) that returns a container instance. The container must satisfy
        C{bool(container) == False} if and only if it is empty.
    '''
    return takewhile(bool,
                     imap(chunktype,
                          starmap(islice,
                                  repeat((iter(iterable),chunksize)))))
