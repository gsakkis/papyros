'''A small platform independent parallel processing package.

B{papyros} provides a simple uniform interface for executing tasks concurrently
in multiple threads or processes, local or on remote hosts.

@var log: Internal papyros logger.
'''

import logging
log = logging.getLogger('papyros')

def config_logger(logger=log, stderr=True, logfile=None, mode='a',
        level=logging.INFO, datefmt='%m/%d/%Y %H:%M:%S',
        fmt='[%(levelname)s] %(asctime)s %(process)d/%(threadName)s: %(message)s'):
    '''Convenience function for configuring a C{Logger} with some basic options.

    Mainly used internally by papyros, but can be also used by clients.

    @param logger: The C{logging.Logger} to be configured (C{papyros.log} by
        default).
    @param stderr: If True, log to standard error.
    @param logfile: If not None, log to the given logfile. It can be combined
        with C{stderr=True}.
    @param mode: The write mode for the logfile; typically 'a' or 'w'.
    @param level: The logger's level.
    @param fmt: The format string to be passed to the C{logging.Formatter}.
    @param datefmt: The date format string to be passed to the C{logging.Formatter}.
    '''
    handlers = []
    if stderr:
        handlers.append(logging.StreamHandler())
    if logfile:
        handlers.append(logging.FileHandler(logfile, mode))
    for handler in handlers:
        handler.setFormatter(logging.Formatter(fmt,datefmt))
        logger.addHandler(handler)
    logger.setLevel(level)


class PapyrosError(Exception):
    '''Base class of all papyros-specific exceptions.'''

class TimeoutError(PapyrosError):
    '''An operation exceeded the maximum specified time limit.'''

from papyros.base import *
from papyros.task import *
from papyros.multithreaded import *
from papyros.dummy import *

try: import Pyro; del Pyro
except ImportError: pass
else: from papyros.distributed import *
