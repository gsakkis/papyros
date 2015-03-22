'''Base L{Task} class and friends.'''

__all__ = ['Task', 'UnprocessedTaskError']

import sys
import traceback

from papyros import log


class UnprocessedTaskError(Exception):
    '''Attempted to get the result of a L{Task} that has not been executed yet.'''


class Task(object):
    '''Abstract base class of a callable to be called later.

    It stores the result or raised exception of the last time it is called.

    @cvar task_attr: If True, an exception C{exc} raised by this task refers to
        it (actually to a copy of it) as C{exc.task}.
    @cvar traceback_attr: If True, an exception C{exc} raised by this task
        refers to the string representation of the traceback as C{exc.traceback}.

    @ivar args: The positional arguments of this task.
    @ivar kwds: The keyword arguments of this task.
    @ivar _str: A string representation of this task.
    @ivar _exception: The exception last raised when executing this task, or None.
    @ivar _result: The result of the last execution of this task (if no exception
        was raised).
    '''

    __slots__ = ('args', 'kwds', '_str', '_exception', '_result')

    task_attr = False
    traceback_attr = False

    def __init__(self, *args, **kwds):
        '''Initialize this task.

        @param args, kwds: The positional and/or keyword arguments to be passed
        to the callable this task encapsulates.
        '''
        self.args = args
        self.kwds = kwds
        self._exception = None
        self._str = '%s.%s(%s)' % (self.__class__.__module__,
                                   self.__class__ .__name__,
                                   ', '.join(repr(arg) for arg in args))
        if kwds:
            self._str = self._str[:-1]
            if args: self._str += ', '
            self._str += '%s)' % ', '.join('%s=%r' % item for item in kwds.iteritems())

    def __repr__(self):
        return self._str

    def result(self):
        '''Return the computed result for this task.

        If an exception had been raised, it is reraised here. If the task has
        not been executed yet, L{UnprocessedTaskError} is raised.
        '''
        if self._exception is not None:
            raise self._exception
        try: return self._result
        except AttributeError:
            raise UnprocessedTaskError()

    def execute(self):
        '''Execute this task and store the result or raised exception.

        Intended to be called by L{workers <Worker>} only.
        '''
        try: self._result = self._execute(*self.args, **self.kwds)
        except Exception, ex:
            if self.traceback_attr:
                ex_type, ex, tb = sys.exc_info()
                # omit the current level of the traceback; start from the next
                ex.traceback = ''.join(traceback.format_exception(ex_type, ex,
                                                                  tb.tb_next))
                # break the cyclic reference between the traceback and this frame
                del tb
            if self.task_attr:
                ex.task = self.__class__(*self.args, **self.kwds)
            self._exception = ex
            log.debug('Failed to execute task %s', self)
        else:
            self._exception = None
            log.debug('Task %s was executed successfully', self)

    def _execute(self, *args, **kwds):
        '''Abstract method for executing this task.

        This method should have the same signature with __init__. It can be
        implemented either explicitly in a concrete subclass or implicitly by
        decorating a callable with the L{subclass} decorator.
        '''
        raise NotImplementedError('Abstract method')

    def __getstate__(self):
        if hasattr(self, '_result'):
            return (self.args, self.kwds, self._str, self._exception, self._result)
        else:
            return (self.args, self.kwds, self._str, self._exception)

    def __setstate__(self, state):
        if len(state) == 5:
            self.args, self.kwds, self._str, self._exception, self._result = state
        else:
            self.args, self.kwds, self._str, self._exception = state

    @classmethod
    def subclass(cls, **kwds):
        '''Return a decorator C{deco(f)} that binds a function C{f} as the
        L{_execute} method of a dynamically generated subclass of this class
        (C{cls}).

        @keyword task_attr: See L{Task.task_attr}.
        @keyword traceback_attr: See L{Task.traceback_attr}.
        '''
        for kwd in kwds:
            if not hasattr(cls, kwd):
                raise ValueError('Invalid keyword %r' % kwd)
        return lambda func,name=None: type(name is None and func.__name__ or name,
                                           (cls,), dict(
            __slots__   = cls.__slots__,
            __module__  = func.__module__,
            __doc__     = func.__doc__,
            _execute    = lambda self,*args,**kw: func(*args,**kw),
            **kwds))
