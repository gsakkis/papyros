Papyros: Pythonic parallel processing
=====================================

**papyros** is a small platform independent parallel processing package. It provides a simple uniform interface for executing tasks concurrently in multiple threads or processes, locally or on remote hosts. This is a quickstart guide to the package; for more details, consult the documentation_.

.. contents::

Requirements
------------
- Python_ 2.4+
- Pyro_ 3.7+. This is required only for distributed processing.

Installation
------------
From this directory run with root priviledges (or specify a user-writable ``--prefix`` otherwise)::

    python setup.py install

Basic usage
-----------
The typical steps to use ``papyros`` are the following:

1. Create the task type(s)
~~~~~~~~~~~~~~~~~~~~~~~~~~
A callable to be processed concurrently has to be wrapped as a Task_ instance. The simplest way to define a Task type is through the `Task.subclass`_ decorator factory::

    import papyros

    @papyros.Task.subclass()
    def factorize(n):
        '''Return the prime factors of an integer.'''
        # do the real work here
        return (n, factors)

Now ``factorize`` is a Task subclass. A specific task can be instantiated by ``factorize(12345)``; note that this does not invoke the callable. Any number of positional and keyword arguments are allowed [1]_.

If you don't want to rebind the original callable's name, just call ``subclass()`` explicitly::

    def factorize(n):
        '''Return the prime factors of an integer.'''
        # do the real work here
        return (n, factors)

    FactorizeTask = papyros.Task.subclass()(factorize, 'FactorizeTask')
    # factorize still refers to the function

Note that in this case the name of the subclass should be specified explicitly as the second argument to the factory.

2. Get a task dispatcher
~~~~~~~~~~~~~~~~~~~~~~~~
A TaskDispatcher_ is responsible for dispatching tasks to workers. Currently three dispatcher types are provided:

- **MultiThreadedTaskDispatcher**: Each worker is a separate thread.
  ::

    # create a dispatcher with 4 worker threads
    dispatcher = papyros.MultiThreadedTaskDispatcher(num_workers=4)

- **PyroTaskDispatcher**: Each worker is a separate (possibly remote) process. This dispatcher requires Pyro_.

  To use a ``PyroTaskDispatcher``, three steps have to be taken before. Each may be run on a different host of the same network.

  a. Start the Pyro name server::

      pyro-ns

  b. Start the dispatcher::

      start-papyros dispatcher [options]

    Several optional switches can be specified at the command line but none is required. To see all the available options, run ``start-papyros dispatcher --help``.

  c. Start ``n`` worker processes::

      start-papyros workers [-n NUM] [options]

    If '-n' is not specified, it defaults to the number of CPUs of the current host.  To see all the available options, run ``start-papyros workers --help``. Finally, repeat this step for all worker machines [2]_.

  Now the client can get a proxy to the dispatcher::

      dispatcher = papyros.PyroTaskDispatcher.get_proxy()

- **DummyTaskDispatcher**: This is a non-concurrent version, mainly as a proof of concept and for sake of completeness::

      dispatcher = papyros.DummyTaskDispatcher()

3. Generate the tasks and execute them
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The main interface to ``papyros`` is the execute_ method. It accepts an iterable of tasks and returns an iterator over the results of these tasks. If the tasks are not expected to raise an exception or if exceptions are not to be handled, the method can be called simply as::

    for n,factors in dispatcher.execute(factorize(i) for i in xrange(1, 1000)):
        print "%d: %s" % (n,factors)

If a task may raise an exception which should be handled without breaking the loop, call explicitly the ``next`` method of the iterator::

    iter_results = dispatcher.execute(factorize(i) for i in xrange(1, 1000))
    for i in xrange(1,1000):
        try:
            print "%d: %s" % iter_results.next()
        except Exception, ex:
            print "Exception raised: %s" % ex

``execute`` also accepts several optional arguments, including:

- ``ordered``: By default, the results are not necessarily yielded in the same order their respective task was submitted. If the order should be preserved, specify ``ordered=True``.
- ``timeout``: If no task is completed within ``timeout`` from the previous one, a TimeoutError_ is raised. By default there is no timeout.
- ``chunksize``: Bundles tasks in chunks of the given size when sending/receiving from workers. The less time each task is expected to take, the larger ``chunksize`` should be, otherwise the cost of communication may surpass the cost of computation.

Advanced usage
--------------
``TaskDispatcher.execute`` should cover most common needs. The rest API provides a more fine-grained control of how tasks are sent and received between the client and the dispatcher as well as other less common features.

Task queues
~~~~~~~~~~~
Clients do not interact directly with the dispatcher; instead they interact with TaskQueue_ objects created by (and associated with) a dispatcher by calling make_queue_. Each task queue acts as a separate channel between the client and the dispatcher. A single dispatcher can handle tasks from multiple task queues while ensuring that the executed tasks return to the correct destination.

Given a task queue, a client can push_ a new task and pop_ a result of an executed task. Both ``push`` and ``pop`` take an optional ``timeout``, raising TimeoutError_ if the call is not completed within the given timeout. A client may also ask for as many results as possible within a given timeout by calling pop_many_. Finally, a task queue should be closed_ after it is not needed any more so that the dispatcher can release the resources associated with it.

Exceptions
~~~~~~~~~~
An exception raised while a task is being executed remotely is reraised on the client when ``execute(tasks).next()`` or ``task_queue.pop()/task_queue.pop_many()`` is called. By default, neither the task that raised the exception nor the original (remote) traceback are saved. To preserve them, pass to Task.subclass_ ``task_attr=True`` and ``traceback_attr=True``, respectively. A raised exception instance then has two extra attributes: ``.task`` references the task that raised the exception [3]_ and ``.traceback`` is the string representation of the original traceback::

        try:
            print "Result: %s" % task_queue.pop()
        except Exception, ex:
            print "Exception raised on task %s: %s" % (ex.task, ex)
            print "Original traceback follows\n%s" % ex.traceback

Distributed groups
~~~~~~~~~~~~~~~~~~
Often there is no reason to have more than one distributed process group; different threads and processes may all share it by creating separate task queues, either implicitly (when calling ``execute``) or explicitly. Some times though it may be desired -- for performance, robustness, security or other reasons -- to have more than one separate dispatchers and associated worker processes. ``papyros`` supports starting and connecting to multiple distributed groups, each of them identified by a unique user-specified name. To start the dispatcher and workers for a given group, provide the ``--group`` option::

      start-papyros dispatcher --group=MyGroup [options]
      start-papyros workers --group=MyGroup [options]

A client can then access a given dispatcher by specifying its group name::

      dispatcher = papyros.PyroTaskDispatcher.get_proxy(group='MyGroup')

Size bounds
~~~~~~~~~~~
By default, dispatchers are unbounded, meaning that an arbitrarily large number of tasks can be pushed to them. Likewise, task queues are unbounded, meaning that an arbitrarily large number of results can be returned to them, waiting to be popped. Both dispatchers and task queues can be bounded in order to limit resource consumption by specifying ``size=N`` to `TaskDispatcher.__init__`_ and `TaskDispatcher.make_queue`_, respectively. Trying to push to a full dispatcher or task queue will either block until it becomes non-full or raise ``TimeoutError`` if a timeout is specified.

---------

.. [1] In the case of remote execution, the module defining the tasks (as well as all the modules it imports, recursively), have to be importable from all hosts. In the future this restriction may be raised by enabling the PYRO_MOBILE_CODE feature.
.. [2] Actually the workers may be started before the dispatcher; in this case they will connect automatically once their dispatcher starts.
.. [3] Actually it references a copy of the task, not the original task instance, so this attribute should not be used for identity checks.

.. _Python: http://www.python.org/
.. _Pyro: http://pyro.sourceforge.net/
.. _Task: docs/papyros.task.Task-class.html
.. _TaskDispatcher: docs/papyros.base.TaskDispatcher-class.html
.. _TaskQueue: docs/papyros.base.TaskQueue-class.html
.. _documentation: docs/index.html
.. _`Task.subclass`: docs/papyros.task.Task-class.html#subclass
.. _execute: docs/papyros.base.TaskDispatcher-class.html#execute
.. _`TaskDispatcher.__init__`: docs/papyros.base.TaskDispatcher-class.html#__init__
.. _make_queue: docs/papyros.base.TaskDispatcher-class.html#make_queue
.. _`TaskDispatcher.make_queue`: docs/papyros.base.TaskDispatcher-class.html#make_queue
.. _push: docs/papyros.base.TaskQueue-class.html#push
.. _pop: docs/papyros.base.TaskQueue-class.html#pop
.. _TimeoutError: docs/papyros.TimeoutError-class.html
.. _pop_many: docs/papyros.base.TaskQueue-class.html#pop_many
.. _closed: docs/papyros.base.TaskQueue-class.html#close
.. _TracebackedTask: docs/papyros.task.TracebackedTask-class.html
