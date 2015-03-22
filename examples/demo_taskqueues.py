#!/usr/bin/env python

import time
from optparse import Option

import papyros
from tasks import SlowSquare, random_task, info, exception_info, main

def test_pop_blocking():
    info('\n* Testing blocking pop() *')
    num_results = num_failures = 0
    taskqueue = dispatcher.make_queue()
    try:
        for i in xrange(num_tasks):
            taskqueue.push(random_task())
        for i in xrange(num_tasks):
            try:
                info('    Got %r', taskqueue.pop())
                num_results += 1
            except Exception, ex:
                num_failures += 1
                exception_info(ex)
    finally:
        taskqueue.close()
    info('%d results, %d failures', num_results, num_failures)

def test_pop_nonblocking(timeout=0):
    info('\n* Testing non-blocking pop(timeout=%.1f) *', timeout)
    num_results = num_failures = 0
    taskqueue = dispatcher.make_queue()
    try:
        for i in xrange(num_tasks):
            taskqueue.push(random_task())
        while num_results+num_failures < num_tasks:
            try:
                info('    Got %r', taskqueue.pop(timeout))
                num_results += 1
            except papyros.TimeoutError:
                info('    Got nothing within the %.1f seconds timeout: '
                     'will check again later', timeout)
                time.sleep(0.1)
            except Exception, ex:
                num_failures += 1
                exception_info(ex)
    finally:
        taskqueue.close()
    info('%d results, %d failures', num_results, num_failures)

def test_pop_many(timeout=0):
    info('\n* Testing pop_many(timeout=%1.f) *', timeout)
    taskqueue = dispatcher.make_queue()
    try:
        for i in xrange(num_tasks):
            taskqueue.push(random_task(SlowSquare))
        try:
            results = taskqueue.pop_many(timeout)
            info('%d results: %s', len(results), results)
        except Exception, ex:
            exception_info(ex)
    finally:
        taskqueue.close()

def test_close():
    info('\n* Testing close() *')
    taskqueue = dispatcher.make_queue()
    for i in xrange(num_tasks):
        taskqueue.push(random_task(SlowSquare))
    for i in xrange(num_tasks//2):
        info('    Got %r', taskqueue.pop())
    taskqueue.close()
    for i in xrange(num_tasks//2, num_tasks):
        try:
            info('    Got %r', taskqueue.pop())
        except papyros.ClosedTaskQueueError:
            info('    Task queue closed'); break
        except Exception, ex:
            # PyroTaskQueue may raise ProtocolError/ConnectionClosedError
            exception_info(ex); break

if __name__ == '__main__':
    dispatcher,options = main(Option('-n', '--num_tasks', type='int', default=10,
                                     help='Number of tasks'))
    num_tasks  = options.num_tasks
    test_pop_blocking()
    test_pop_nonblocking(timeout=0.5)
    test_pop_many(timeout=3)
    test_close()
