###############################################################################
# Name: PrimaryThread.py
# Uses: Class for primary threads.
# Date: 2016-02-03
# Author(s):
#   Andrew Que <aque@bb7.com>
# Notes:
#   Used to keep a list of primary threads.  Such threads start when the
#   program loads and run until the program finishes.  They are signaled to
#   stop when PrimaryThread.isRunning to False.  When this occurs, each thread must
#   shutdown.
###############################################################################
import threading
import sys
import traceback
from dune_winder.library.system_semaphore import SystemSemaphore


class PrimaryThread(threading.Thread):
  thread_instances: list["PrimaryThread"] = []
  isRunning = False
  useGracefulException = True
  _stopContext = None
  _stopContextLock = threading.Lock()

  # ---------------------------------------------------------------------
  def __init__(self, name, log):
    """
    Constructor.

    Args:
      name: Name of thread.
    """

    threading.Thread.__init__(self, name=name)
    PrimaryThread.thread_instances.append(self)
    self._name = name
    self._log = log

  # ---------------------------------------------------------------------
  @staticmethod
  def _getLog():
    for instance in reversed(PrimaryThread.thread_instances):
      if getattr(instance, "_log", None) is not None:
        return instance._log

    return None

  # ---------------------------------------------------------------------
  @staticmethod
  def _rememberStopContext(reason, details=None):
    if details is None:
      details = []

    callerThread = threading.current_thread()
    with PrimaryThread._stopContextLock:
      isNew = PrimaryThread._stopContext is None
      if isNew:
        stack = traceback.format_stack(limit=12)
        if len(stack) > 0:
          stack = stack[:-1]

        PrimaryThread._stopContext = {
          "reason": str(reason),
          "thread": callerThread.name,
          "details": [str(detail) for detail in details],
          "stack": "".join(stack).strip(),
        }

    return PrimaryThread._stopContext, isNew

  # ---------------------------------------------------------------------
  @staticmethod
  def getStopContext():
    with PrimaryThread._stopContextLock:
      if PrimaryThread._stopContext is None:
        return None

      return {
        "reason": PrimaryThread._stopContext["reason"],
        "thread": PrimaryThread._stopContext["thread"],
        "details": list(PrimaryThread._stopContext["details"]),
        "stack": PrimaryThread._stopContext["stack"],
      }

  # ---------------------------------------------------------------------
  @staticmethod
  def getThreadStatus():
    return [
      {
        "name": instance._name,
        "alive": instance.is_alive(),
      }
      for instance in PrimaryThread.thread_instances
    ]

  # ---------------------------------------------------------------------
  @staticmethod
  def startAllThreads():
    """
    Start all threads. Call at start of program after thread creation.
    """

    with PrimaryThread._stopContextLock:
      PrimaryThread._stopContext = None

    PrimaryThread.isRunning = True

    log = PrimaryThread._getLog()
    if log:
      log.add(
        "PrimaryThread",
        "THREADS_START",
        "Starting all primary threads.",
        [instance._name for instance in PrimaryThread.thread_instances],
      )

    for instance in PrimaryThread.thread_instances:
      instance.start()

  # ---------------------------------------------------------------------
  @staticmethod
  def stopAllThreads(reason="unspecified", details=None):
    """
    Stop all threads. Call at end of program.
    """
    context, isNew = PrimaryThread._rememberStopContext(reason, details)
    log = PrimaryThread._getLog()
    if isNew and log:
      log.add(
        "PrimaryThread",
        "THREADS_STOP",
        "Stopping all primary threads.",
        [
          context["reason"],
          context["thread"],
          context["details"],
          context["stack"],
        ],
      )

    PrimaryThread.isRunning = False

    for instance in PrimaryThread.thread_instances:
      instance.stop()

    SystemSemaphore.releaseAll()

  # ---------------------------------------------------------------------
  def stop(self):
    """
    Stop this thread. Can be overloaded for custom shutdown.
    """
    pass

  # ---------------------------------------------------------------------
  def run(self):
    self._log.add(
      self.__class__.__name__,
      "THREAD_START",
      "Primary thread started.",
      [self._name, threading.current_thread().name],
    )

    try:
      self.body()
      if PrimaryThread.isRunning:
        self._log.add(
          self.__class__.__name__,
          "THREAD_EXIT",
          "Primary thread body returned while shutdown had not been requested.",
          [self._name],
        )
      else:
        self._log.add(
          self.__class__.__name__,
          "THREAD_EXIT",
          "Primary thread exited after shutdown request.",
          [self._name],
        )
    except BaseException as exception:
      PrimaryThread.stopAllThreads(
        "thread_exception",
        [self._name, exception.__class__.__name__, str(exception)],
      )
      exceptionType, exceptionValue, exceptionTraceback = sys.exc_info()
      tracebackString = repr(traceback.format_tb(exceptionTraceback))
      self._log.add(
        self.__class__.__name__,
        "ThreadException",
        "Thread had an exception.",
        [exception, exceptionType, exceptionValue, tracebackString],
      )

      if not PrimaryThread.useGracefulException:
        raise


# end class
