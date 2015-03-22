'''A non-concurrent implementation of the papyros API.

Basically for sake of completeness and as a fallback, not really useful.
'''

__all__ = ['DummyTaskDispatcher']

from papyros.base import TaskDispatcher, Worker


class DummyTaskDispatcher(TaskDispatcher,Worker):
    '''A non-concurrent L{TaskDispatcher} and L{Worker} at the same time.

    It executes tasks as soon as they are pushed to it.
    '''

    def __init__(self, size=0):
        TaskDispatcher.__init__(self, size)
        Worker.__init__(self, self)

    def _push_task(self, task, task_queue, timeout):
        '''Push the given task from the given task queue to this dispatcher.

        This implementation also executes the task right after pushing it (since
        it's both L{TaskDispatcher} and L{Worker}).

        @param timeout: It must be None; timeouts can't be enforced for
            single-threaded workers.
        @raises ValueError: If C{timeout} is not None.
        '''
        if timeout is not None:
            raise ValueError('Cannot set timeout when pushing to a dummy dispatcher')
        # XXX ignore timeout when pushing; this might raise a TimeoutError
        TaskDispatcher._push_task(self, task, task_queue, timeout=0)
        self.execute_task()
