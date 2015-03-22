'''Core papyros API classes.'''

__all__ = [
    'TaskDispatcher', 'TaskQueue', 'Worker',
    'ClosedTaskDispatcherError', 'ClosedTaskQueueError'
]

import time
import threading
from Queue import Queue, Empty, Full

from papyros.task import Task
from papyros.execute import ExecuteIterator
from papyros import log, PapyrosError, TimeoutError


#========== TaskDispatcher =====================================================

class ClosedTaskDispatcherError(PapyrosError):
    '''Attempted to modify a closed L{TaskDispatcher}.'''

class TaskDispatcher(object):
    '''A I{TaskDispatcher} receives L{tasks <Task>} from a L{TaskQueue} and
    dispatches them to L{workers <Worker>}.
    '''

    def __init__(self, size=0):
        '''Initialize this dispatcher.

        @param size: The maximum number of unassigned tasks (unlimited by default).
            Trying to push a new L{Task} when C{size} tasks are unassigned blocks
            or raises L{TimeoutError}.
        '''
        self.__unassigned = Queue(size)
        self.__task_queues = set()

    def make_queue(self, size=0):
        '''Create a new L{TaskQueue} and associate it with this dispatcher.

        @param size: The L{size <TaskQueue.__init__>} of the new task queue.
        @returns: The new L{TaskQueue}.
        '''
        if self.__unassigned is None:
            raise ClosedTaskDispatcherError()
        task_queue = self._make_queue(size)._get_proxy()
        self.__task_queues.add(task_queue)
        return task_queue

    def execute(self, tasks, timeout=None, ordered=False, chunksize=1, qsize=0):
        '''Execute the given tasks.

        @param tasks: An iterable of L{tasks <Task>} to be executed.
        @param timeout: An upper bound of how long is a task expected to take.
            Useful to prevent waiting for tasks that take forever to complete
            for whatever reason.
        @param ordered: If True, the order of the yielded results matches the
            the order of the tasks that generated them. If False, the results'
            order is unspecified.
        @param chunksize: The C{tasks} iterable is chunked into slices of this
            size (or less) before being submitted to the dispatcher and workers.
        @param qsize: The L{size <TaskQueue.__init__>} of the underlying task queue.
        @returns: An iterator over the results of the executed tasks.
        @raises TimeoutError: If a call to the returned iterator's C{next()}
            exceeds the C{timeout}.
        '''
        return ExecuteIterator(self.make_queue(qsize), tasks,
                               timeout=timeout, ordered=ordered, chunksize=chunksize)

    def num_queues(self):
        'Return the number of active L{task queues <TaskQueue>} of this dispatcher.'
        return len(self.__task_queues)

    def num_tasks(self):
        '''Return the (approximate) number of unassigned L{tasks <Task>} of this
        dispatcher.
        '''
        return self.__unassigned.qsize()

    def close(self):
        '''Release the resources associated with this dispatcher.

        A subsequent attempt to modify the dispatcher raises L{ClosedTaskDispatcherError}.
        '''
        self.__task_queues.clear()
        self.__unassigned = None

    def _discard_queue(self, task_queue):
        '''Disassociate the given queue from this dispatcher.

        All still unassigned tasks of this queue will be dropped. Attempting to
        push a new task by this queue will raise a RuntimeError.
        '''
        self.__task_queues.discard(task_queue)
        log.debug('%s discarded %s', self, task_queue)

    def _push_task(self, task, task_queue, timeout):
        '''Push the given task from the given task queue to this dispatcher.

        @param timeout: If C{timeout is None} and the dispatcher is full, wait
            until a slot becomes available. If C{timeout > 0} and the dispatcher
            remains full after C{timeout} seconds, or if C{timeout <= 0}
            and the dispatcher is full now, raise L{TimeoutError}.
        @raises TimeoutError: If C{timeout} expires before pushing the task.
        '''
        if task_queue in self.__task_queues:
            block = timeout is None or timeout>0
            try: self.__unassigned.put((task,task_queue), block, timeout)
            except Full: raise TimeoutError()
            log.debug('%s received new task %s from %s', self, task, task_queue)
        else:
            raise RuntimeError('%s is not authorized at this dispatcher' % task_queue)

    def _assign_task(self):
        '''Pop and return the next unassigned non cancelled task.

        This method is to called by a L{Worker} of this dispatcher.

        @returns: An unassigned (task, task_queue) tuple, or None if there are
            no unassigned tasks.
        '''
        while True:
            if self.__unassigned is None:
                raise ClosedTaskDispatcherError()
            try: task,task_queue = self.__unassigned.get_nowait()
            except Empty:
                return None
            if task_queue in self.__task_queues:
                log.debug('%s assigned task %s', self, task)
                return (task, task_queue)
            else:
                log.debug('%s discarded task %s from removed queue %s',
                          self, task, task_queue)

    def _make_queue(self, size=0):
        '''Create a new L{TaskQueue}.

        Can be overriden by subclasses.

        @param size: The L{size <TaskQueue.__init__>} of the new task queue.
        @returns: The new L{TaskQueue}.
        '''
        return TaskQueue(self, size)

#========== TaskQueue ==========================================================

class ClosedTaskQueueError(PapyrosError):
    '''Attempted to modify a closed L{TaskQueue}.'''

class TaskQueue(object):
    '''An abstraction of a queue of L{tasks <Task>}.

    A I{TaskQueue} is used to L{push} new tasks to be executed and L{pop} results
    from finished tasks (or reraise the exception raised during task execution).
    Task queues should be L{closed <close>} after they are not needed anymore.

    Clients should not instantiate this class directly; they should call
    L{TaskDispatcher.make_queue} instead.
    '''

    def __init__(self, dispatcher, size=0):
        '''Initialize this task queue.

        @param dispatcher: The L{TaskDispatcher} to dispatch tasks pushed in
            this queue.
        @param size: The maximum number of completed tasks waiting to be popped
            (unlimited by default).
        '''
        self.__dispatcher = dispatcher
        self.__finished = Queue(size)

    def push(self, task, timeout=None):
        '''Add a new L{Task <task>} to this task queue.

        @param timeout: If C{timeout is None} and the queue's dispatcher is full,
            wait until a slot becomes available. If C{timeout > 0} and the
            dispatcher remains full after C{timeout} seconds, or if C{timeout <= 0}
            and the dispatcher is full now, raise L{TimeoutError}.

        @raises TimeoutError: If C{timeout} expires before pushing the task.
        @raises ClosedTaskQueueError: If the queue has been closed.
        '''
        if not isinstance(task, Task):
            raise TypeError('Task object expected; %r given' % task)
        if self.__finished is None:
            raise ClosedTaskQueueError()
        self.__dispatcher._push_task(task, self._get_proxy(), timeout)

    def pop(self, timeout=None):
        '''Pop a finished L{Task <task>} from this queue.

        @param timeout: If C{timeout is None} and there are no pending finished
            tasks, wait until one finishes. If C{timeout > 0} and no task has
            finished within C{timeout} seconds, or if C{timeout <= 0} and no
            finished task is available immediately, raise L{TimeoutError}.

        @returns: The result of a finished task.
        @raises TimeoutError: If C{timeout} expires before poping a task.
        @raises ClosedTaskQueueError: If the queue has been closed.
        @raises Exception: Any exception raised when executing the task is
            reraised here.
        '''
        if self.__finished is None:
            raise ClosedTaskQueueError()
        try: task = self.__finished.get(timeout is None or timeout>0, timeout)
        except Empty: raise TimeoutError()
        log.debug('%s popped finished task %s', self, task)
        return task.result()

    def pop_many(self, timeout=0):
        '''Pop several finished tasks within the given timeout.

        @param timeout: Keep popping finished tasks for C{timeout} seconds. If
        C{timeout <= 0}, pop all currently finished tasks.

        @rtype: list
        @returns: The results of the finished tasks within the given timeout.
        @raises ClosedTaskQueueError: If the queue has been closed.
        @raises Exception: Any exception raised when executing any of the popped
            tasks.
        '''
        if timeout is None:
            raise TypeError('timeout must be a number')
        finished = []
        now = time.time
        end = now() + timeout
        while timeout > 0:
            try: finished.append(self.pop(timeout))
            except TimeoutError: break
            timeout = end - now()
        return finished

    def close(self):
        '''Release the resources associated with this task queue.

        A subsequent attempt to modify the queue raises L{ClosedTaskQueueError}.
        '''
        self.__dispatcher._discard_queue(self._get_proxy())
        self.__finished = None

    def _get_finished(self, task):
        '''Push an executed task in the finished queue.

        Should be called by a L{Worker} only.
        '''
        if self.__finished is None:
            log.debug('%s dropped silently finished task %s', self, task)
        else:
            self.__finished.put(task)        # block here if the queue is full
            log.debug('%s received finished task %s', self, task)

    def _get_proxy(self):
        '''Return a proxy to this queue as it is to be known by its dispatcher.

        Basically added to support Pyro task queues; this implementation just
        returns self.
        '''
        return self

#========== Worker =============================================================

class Worker(object):
    '''A I{Worker} is assigned L{tasks <Task>} from a L{TaskDispatcher},
    executes them and returns them to the respective L{TaskQueue} that submitted
    the task.

    This class is not directly usable; it must be subclassed to provide a way to
    call L{execute_task}, typically in an infinite loop.
    '''

    def __init__(self, dispatcher=None):
        '''Initialize this worker.

        @param dispatcher: If not None, L{connect} to this dispatcher.
        '''
        self.__dispatcher = None
        if dispatcher is not None:
            self.connect(dispatcher)

    def connect(self, dispatcher):
        '''Associate this worker to the given L{TaskDispatcher}.'''
        if self.is_connected():
            self.disconnect()
        self.__dispatcher = dispatcher
        log.debug('%s connected to %s', self, dispatcher)

    def disconnect(self):
        '''Disassociate this worker from its L{TaskDispatcher}.'''
        if self.is_connected():
            self.__dispatcher = None
            log.debug('%s disconnected from %s', self, self.__dispatcher)

    def is_connected(self):
        '''Check whether this worker is L{connected <connect>}.'''
        return self.__dispatcher is not None

    def execute_task(self):
        '''Fetch an unassigned L{Task} from this worker's L{TaskDispatcher},
        execute it and send it back to the L{TaskQueue} it originated from.

        @rtype: bool
        @returns: True if a task was executed, False if there are no unassigned
            tasks in the dispatcher.
        @raises RuntimeError: If this worker is not L{connected <is_connected>}.
        '''
        if not self.is_connected():
            raise RuntimeError('Not connected to a dispatcher')
        assignment = self.__dispatcher._assign_task()
        if assignment is None:
            return False
        else:
            task,task_queue = assignment
            task.execute()
            task_queue._get_finished(task)
            log.debug('%s sent finished task %s back to %s', self, task, task_queue)
            return True
