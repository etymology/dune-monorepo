###############################################################################
# Name: RemoteSession.py
# Uses: Session management for remote clients.
# Date: 2016-07-18
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

import uuid  # <- To generate session IDs.
import datetime  # <- Keeping track of session age.
import os  # <- For streams of random data used for salt generation.
import hashlib  # <- To hash password.
import binascii  # <- To turn byte streams to hex.

from dune_winder.library.SystemSemaphore import SystemSemaphore


# ==============================================================================
class RemoteSession:
  # Time (in seconds) until session expires.
  # The two times prevent browsers that block cookies from creating a huge
  # number of unused sessions by requiring the sessions be used at least once
  # before using a longer expiration time.
  INITIAL_EXPIRATION = 3  # Sessions until they are used at least once.
  ACTIVE_EXPIRATION = 3600  # Sessions that are in use.

  # Bytes of salt data.
  SALT_SIZE = 16

  # $$$FUTURE - This should come from a configurtion file.
  PASSWORD = "PSL#Winder"

  # Current sessions.
  sessions: dict[str, "RemoteSession"] = {}
  sessionsSemaphore = SystemSemaphore(1)

  # ----------------------------------------------------------------------------
  @staticmethod
  def sessionSetup(sessionId=None):
    """
    Load or create a new session.

    Args:
      sessionId: Session id number.  None to create a new session.

    Returns:
      Instance of RemoteSession.
    """

    RemoteSession.sessionsSemaphore.acquire()

    # Update all sessions.
    removeQueue = []
    for id in RemoteSession.sessions:
      session = RemoteSession.sessions[id]
      if session._isExpired():
        # Queue session for removal (cannot remove from a list being traversed).
        removeQueue.append(id)

    # Remove any dead sessions.
    for id in removeQueue:
      RemoteSession.sessions.pop(id, 0)

    session = None

    # If session is registered...
    if sessionId in RemoteSession.sessions:
      # Use register session data.
      session = RemoteSession.sessions[sessionId]
      session._update()
    else:
      # Create new session.
      session = RemoteSession()
      sessionId = session.getId()
      RemoteSession.sessions[sessionId] = session

    RemoteSession.sessionsSemaphore.release()

    return session

  # ----------------------------------------------------------------------------
  @staticmethod
  def isAuthenticated(sessionId):
    """
    Check to see if a session is authenticated.

    Args:
      sessionId: Session id to check.

    Returns:
      True if authenticated, False if not.
    """
    RemoteSession.sessionsSemaphore.acquire()

    result = False
    if sessionId in RemoteSession.sessions:
      session = RemoteSession.sessions[sessionId]
      session._update()
      result = session._authenticated

    RemoteSession.sessionsSemaphore.release()

    return result

  # ----------------------------------------------------------------------------
  def _update(self):
    """
    Update session.  Called when session has been used to keep session alive.
    Internal function.
    """
    if self._updateCount > 0:
      self._timeToLive = RemoteSession.ACTIVE_EXPIRATION

    self._updateCount += 1

    self._lastUpdate = datetime.datetime.now()

  # ----------------------------------------------------------------------------
  def _isExpired(self):
    """
    Check to see if session is expired.  Internal function.

    Returns:
      True if session is expired.
    """
    now = datetime.datetime.now()
    then = self._lastUpdate
    delta = now - then

    return delta.total_seconds() > self._timeToLive

  # ----------------------------------------------------------------------------
  def getId(self):
    """
    Get session id number.

    Returns:
      Session id number.
    """
    return self._id

  # ----------------------------------------------------------------------------
  def getSalt(self):
    """
    Get the salt value used for hashing password.  Salt must be appended to
    password before hashing to produce the correct hash.

    Returns:
      Salt value as string.
    """
    return self._salt

  # ----------------------------------------------------------------------------
  def getAuthenticated(self):
    """
    See if session is authenticated (i.e. logged in).

    Returns:
      True if authenticated.
    """
    return self._authenticated

  # ----------------------------------------------------------------------------
  def setAuthenticated(self, isAuthenticated):
    """
    Force session authentication.

    Args:
      isAuthenticated: Desired authentication state.
    """
    self._authenticated = isAuthenticated

  # ----------------------------------------------------------------------------
  def _createSalt(self):
    """
    Create a new salt value.  Internal function.
    """

    # Salt consists of a random number (in hex) and the session id number.
    # The session id number makes the salt value session specific.
    self._salt = str(binascii.hexlify(os.urandom(self.SALT_SIZE))) + self._id

  # ----------------------------------------------------------------------------
  def checkPassword(self, passwordHash, password=None):
    """
    Verify a password hash.

    Args:
      passwordHash: Incoming hash of password.
      password: Actual password to check against.
    """
    if password is None:
      password = RemoteSession.PASSWORD

    hasedData = self._salt + password

    hashValue = hashlib.sha256(hasedData).hexdigest()

    isOk = passwordHash == hashValue
    self.setAuthenticated(isOk)

    if not isOk:
      self._createSalt()

    return isOk

  # ----------------------------------------------------------------------------
  def __init__(self):
    """
    Construct.
    """

    # Session id number is a UUID.
    self._id = str(uuid.uuid4())

    # Session has not yet been authenticated.
    self._authenticated = False

    # Setup salt.
    self._salt = None
    self._createSalt()

    # Setup session lifetime.
    self._updateCount = 0
    self._timeToLive = RemoteSession.INITIAL_EXPIRATION
    self._lastUpdate = None
    self._update()
