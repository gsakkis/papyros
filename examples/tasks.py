import sys
import time
import random
import logging
import traceback
from math import sqrt
from itertools import count, ifilter
from optparse import OptionParser, Option

import papyros

logger = logging.getLogger('demo')
papyros.config_logger(logger=logger, stderr=True, level=logging.INFO,
                      fmt='\t%(process)d/%(threadName)s: %(message)s')
show_tracebacks = False

#========== tasks ==============================================================

@papyros.Task.subclass()
def SlowSquare(n):
    t = random.randrange(50) / 10.0
    logger.info('Pretending to compute %s**2 for %.1f second(s)', n, t)
    time.sleep(t)
    return n*n

@papyros.Task.subclass(task_attr=True, traceback_attr=True)
def PrimeFactors (n):
    logger.info('Factorizing %s', n)
    factors = []
    nextprime = sieve().next
    candidate = nextprime()
    thresh = sqrt(n)
    while True:
        if candidate > thresh:
            factors.append(n)
            break
        d,m = divmod(n, candidate)
        if m == 0:
            factors.append(candidate)
            n = d; thresh = sqrt(n)
        else:
            candidate = nextprime()
    return factors

def sieve():
    # from Tim Hochberg's comment at
    # http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/117119
    seq = count(2)
    while True:
        p = seq.next()
        seq = ifilter(p.__rmod__, seq)
        yield p

#======== helpers ==============================================================

def random_task(task_type=None):
    if task_type is None:
        task_type = random.choice((SlowSquare, PrimeFactors))
    return task_type(random.randrange(-sys.maxint, sys.maxint))

def info(fmt, *args):
    if args: print fmt % args
    else: print fmt

def exception_info(ex):
    if show_tracebacks:
        ex_msg = getattr(ex, 'traceback', traceback.format_exc())
    else:
        ex_msg = ''.join(traceback.format_exception_only(ex.__class__,ex))
    return info('    Exception raised on %s: %s',
                getattr(ex,'task','<Unknown task>'), ex_msg)

#======== main =================================================================

def main(*extra_options):
    global show_tracebacks
    options = OptionParser(option_list = (
        Option('-d', '--dispatcher', default='dummy',
                    choices=('dummy','multithreaded','remote'),
                    help='Task dispatcher type'),
        Option('-t', '--threads', type='int', default=0,
                    help='Number of threads (if "--dispatcher=multithreaded")'),
        Option('-g', '--group',
                    help='Pyro group name (if "--dispatcher=remote")'),
        Option('-T', '--traceback', action='store_true',
                    help='Show exception tracebacks'),
    ) + extra_options).parse_args()[0]

    show_tracebacks = bool(options.traceback)
    if options.dispatcher == 'dummy':
        dispatcher = papyros.DummyTaskDispatcher()
    elif options.dispatcher == 'multithreaded':
        dispatcher = papyros.MultiThreadedTaskDispatcher(num_workers=options.threads)
    elif options.dispatcher == 'remote':
        ##papyros.set_nameserver('localhost')
        dispatcher = papyros.PyroTaskDispatcher.get_proxy(group=options.group)
    return dispatcher, options
