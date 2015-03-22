#!/usr/bin/env python

from distutils.core import setup

setup(
    name            = 'papyros',
    version         = '0.2.1',
    packages        = ['papyros'],
    scripts         = ['start-papyros'],
    author          = 'George Sakkis',
    author_email    = 'george.sakkis@gmail.com',
    url             = 'http://code.google.com/p/papyros/',
    description     = 'Pythonic parallel processing',
    long_description= '''
**papyros** is a small platform independent parallel processing package. It
provides a simple uniform interface for executing tasks concurrently in multiple
threads or processes, local or on remote hosts.
''',
    classifiers     = [
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: System :: Distributed Computing',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
)
