- tasks.py
  Defines two task types: SlowSqrt, an (artificially) slow non cpu intensive task that does not raise an exception and PrimeFactors, a (potentially) cpu intensive task that may raise an exception.

- demo_execute.py
  Demonstrates the main API, the execute() method. To see all the available options, run: 
    python demo_execute.py --help
  For instance, to run the demo using a multithreaded dispatcher with 3 workers for 10 tasks, give:
    python demo_execute.py --dispatcher=multithreaded -t3 -n10

- demo_taskqueues.py
  Demonstrates the (low-level) task queue API. To see all the available options, run: 
    python demo_taskqueues.py --help
  
NOTE: For "--dispatcher=remote" , first make sure that the Pyro name server is running and that both the dispatcher and all the workers are started in this directory ("examples"), so that tasks.py is in the PYTHONPATH.
