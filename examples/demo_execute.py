#!/usr/bin/env python

import time
from itertools import izip
from optparse import Option

import papyros
from tasks import SlowSquare, PrimeFactors, random_task, info, exception_info, main

def test_execute(ordered, chunksize):
    info('\n* Testing execute(ordered=%s, chunksize=%d) - not expecting '
         'exceptions *', ordered, chunksize)
    num_results = 0
    iter_tasks = (SlowSquare(i) for i in xrange(num_tasks))
    for result in dispatcher.execute(iter_tasks, ordered=ordered, chunksize=chunksize):
        info('    Got %r', result)
        num_results += 1
    info('%d results', num_results)
    assert num_results == num_tasks

def test_execute_exception(ordered, chunksize):
    info('\n* Testing execute(ordered=%s, chunksize=%d) - expecting exceptions *',
         ordered, chunksize)
    num_results = num_failures = 0
    iter_tasks = (random_task(PrimeFactors) for i in xrange(num_tasks))
    iter_results = dispatcher.execute(iter_tasks, ordered=ordered, chunksize=chunksize)
    for i in xrange(num_tasks):
        try:
            info('    Got %r', iter_results.next())
            num_results += 1
        except Exception, ex:
            num_failures += 1
            exception_info(ex)
    info('%d results, %d failures', num_results, num_failures)
    assert num_results + num_failures == num_tasks

def test_multiple_queues(ordered=False, chunksize=1):
    info('\n* Testing execute(ordered=%s, chunksize=%d) - multiple queues *',
         ordered, chunksize)
    iter_tasks1 = (SlowSquare(i) for i in xrange(num_tasks))
    iter_results1 = dispatcher.execute(iter_tasks1, ordered=ordered, chunksize=chunksize)
    iter_tasks2 = (SlowSquare(float(i)) for i in xrange(num_tasks))
    iter_results2 = dispatcher.execute(iter_tasks2, ordered=ordered, chunksize=chunksize)
    num_results = 0
    for result1,result2 in izip(iter_results1,iter_results2):
        info('    Got (%r, %r)', result1, result2)
        num_results +=1
        assert isinstance(result1,int) and isinstance(result2,float)
    assert num_results == num_tasks

def test_close_execute():
    info('\n* Testing close() on execute() iterator *')
    iter_results = dispatcher.execute(SlowSquare(i) for i in xrange(num_tasks))
    for i in xrange(num_tasks//2):
        info('    Got %r', iter_results.next())
    iter_results.close()
    for i in xrange(num_tasks//2, num_tasks):
        try:
            info('    Got %r', iter_results.next())
        except papyros.ClosedTaskQueueError:
            info('    Task queue closed'); break
        except Exception, ex:
            # PyroTaskQueue may raise ProtocolError/ConnectionClosedError
            exception_info(ex); break

def test_autoclose():
    info('\n* Testing automatic close() / garbage collection *')
    time.sleep(0.1) # give time for any previously closed queues to die off
    num_queues = dispatcher.num_queues()
    assert not num_queues, 'Starting with %d queues instead of 0' % num_queues
    # starting the queues in a separate function to make sure that no locals are
    # kept around after it returns
    def closure():
        for i in xrange(num_tasks):
            task = random_task(PrimeFactors)
            info('  Task: %s', task)
            try: dispatcher.execute([task]).next()
            except Exception, ex: pass
    closure()
    time.sleep(0.1) # give time for all closed queues to die off
    num_queues = dispatcher.num_queues()
    assert not num_queues, 'Ending with %d queues instead of 0' % num_queues


if __name__ == '__main__':
    dispatcher,options = main(
        Option('-n', '--num_tasks', type='int', default=10,
            help='Number of tasks'),
        Option('-o', '--ordered', action='store_true', default=False,
               help='Yield the results in the same order with the tasks'),
        Option('-c', '--chunksize', type='int', default=1, metavar='SIZE',
               help='Break the tasks into into slices of SIZE'))
    num_tasks  = options.num_tasks
    ordered = options.ordered
    chunksize = options.chunksize
    test_execute(ordered, chunksize)
    test_execute_exception(ordered, chunksize)
    test_multiple_queues(ordered, chunksize)
    test_close_execute()
    test_autoclose()
