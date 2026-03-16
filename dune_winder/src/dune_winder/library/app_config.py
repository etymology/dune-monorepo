"""Operator configuration loaded from configuration.toml at startup.

Replaces the old XML-based ``Configuration`` class.  All fields are typed
attributes on ``AppConfig``; reading them avoids the casting footgun of the
old ``config.get("key")`` → ``str | None`` interface.

``get()`` and ``set()`` are kept so the remote API handlers in
``api/commands.py`` can still do dynamic key look-ups.
"""

import dataclasses
import os
import pathlib
import tempfile
import tomllib
import typing


@dataclasses.dataclass
class AppConfig:
  VALID_PLC_MODES = ("REAL", "SIM")

  # PLC network address.
  plcAddress: str = "192.168.140.13"

  # PLC backend mode.
  plcMode: str = "REAL"

  # Camera FTP URL for last captured image.
  cameraURL: str = "ftp://admin@192.168.140.19/image.bmp"

  # Camera calibration: pixels per millimetre.
  pixelsPer_mm: int = 18

  # Manual calibration camera offsets (mm) per layer.
  manualCalibrationOffsetUX: float = 65.0
  manualCalibrationOffsetUY: float = -108.2
  manualCalibrationOffsetVX: float = 65.0
  manualCalibrationOffsetVY: float = -108.2
  manualCalibrationOffsetXX: float = 65.0
  manualCalibrationOffsetXY: float = -108.2
  manualCalibrationOffsetGX: float = 65.0
  manualCalibrationOffsetGY: float = -108.2

  # UI command server.
  serverAddress: str = "127.0.0.1"
  serverPort: int = 6626

  # Web server port.
  webServerPort: int = 8080

  # Machine calibration file name (relative to config/).
  machineCalibrationFile: str = "machineCalibration.json"

  # Velocity and acceleration limits.
  maxVelocity: int = 1020
  maxSlowVelocity: float = 25.4
  maxAcceleration: int = 5000
  maxDeceleration: int = 5000

  @classmethod
  def normalizePlcMode(cls, value: typing.Any) -> str:
    mode = str(value).strip().upper()
    if mode not in cls.VALID_PLC_MODES:
      raise ValueError(
        "configuration.toml: 'plcMode' must be one of " + ", ".join(cls.VALID_PLC_MODES)
      )
    return mode

  def __post_init__(self) -> None:
    self.plcMode = self.normalizePlcMode(self.plcMode)
    # Not a dataclass field — stores the file path for save().
    self._path: typing.Optional[pathlib.Path] = None

  # ------------------------------------------------------------------
  @classmethod
  def load(cls, path: pathlib.Path) -> "AppConfig":
    """Load from *path* (TOML).

    If the file does not exist the instance is initialised with defaults
    and ``_path`` is set so a subsequent ``save()`` writes the file.

    Raises ``ValueError`` on unknown keys or wrong-typed values.
    """
    if not path.exists():
      # Migration: if configuration.xml exists alongside the missing
      # .toml, read it and immediately save as TOML so future starts
      # use the new format.
      xml_path = path.with_suffix(".xml")
      if xml_path.exists():
        instance = cls._load_from_xml(xml_path)
        instance._path = path
        instance.save()
        return instance
      instance = cls()
      instance._path = path
      return instance

    with path.open("rb") as f:
      raw = tomllib.load(f)

    hints = typing.get_type_hints(cls)
    valid_fields = {field.name for field in dataclasses.fields(cls)}

    unknown = set(raw) - valid_fields
    if unknown:
      raise ValueError(f"configuration.toml: unknown keys: {sorted(unknown)!r}")

    kwargs: dict = {}
    for name in valid_fields:
      if name not in raw:
        continue
      val = raw[name]
      expected = hints[name]
      # TOML represents whole-number floats as int; coerce silently.
      if expected is float and isinstance(val, int):
        val = float(val)
      elif not isinstance(val, expected):
        raise ValueError(
          f"configuration.toml: '{name}' expected "
          f"{expected.__name__}, got {type(val).__name__}"
        )
      kwargs[name] = val

    instance = cls(**kwargs)
    instance._path = path
    return instance

  # ------------------------------------------------------------------
  @classmethod
  def _load_from_xml(cls, xml_path: pathlib.Path) -> "AppConfig":
    """Read the legacy configuration.xml and return an AppConfig instance."""
    import xml.dom.minidom

    doc = xml.dom.minidom.parse(str(xml_path))
    hints = typing.get_type_hints(cls)
    valid_fields = {field.name for field in dataclasses.fields(cls)}
    kwargs: dict = {}
    for name in valid_fields:
      nodes = doc.getElementsByTagName(name)
      if not nodes:
        continue
      child = nodes[0].firstChild
      text = (child.nodeValue or "").strip() if child is not None else ""
      expected = hints[name]
      try:
        kwargs[name] = expected(text)
      except (TypeError, ValueError):
        pass
    return cls(**kwargs)

  # ------------------------------------------------------------------
  def save(self) -> None:
    """Write configuration to TOML atomically.

    No-op if the instance was not created via ``load()`` (no path stored).
    """
    if self._path is None:
      return

    lines: list[str] = []
    for field in dataclasses.fields(self):
      val = getattr(self, field.name)
      if isinstance(val, str):
        lines.append(f'{field.name} = "{val}"')
      elif isinstance(val, bool):
        lines.append(f"{field.name} = {'true' if val else 'false'}")
      else:
        lines.append(f"{field.name} = {val}")

    content = "\n".join(lines) + "\n"
    fd, tmp = tempfile.mkstemp(dir=self._path.parent)
    try:
      with os.fdopen(fd, "w") as f:
        f.write(content)
      os.replace(tmp, self._path)
    except Exception:
      try:
        os.unlink(tmp)
      except OSError:
        pass
      raise

  # ------------------------------------------------------------------
  def get(self, key: str) -> typing.Any:
    """Return the value of a configuration key, or ``None`` if unknown.

    Kept for compatibility with the remote API command handlers that
    perform dynamic key look-ups.
    """
    return getattr(self, key, None)

  # ------------------------------------------------------------------
  def set(self, key: str, value: typing.Any) -> None:
    """Set *key* to *value*, coerce to the declared type, and save.

    Raises ``KeyError`` for unknown keys.
    """
    valid_fields = {field.name for field in dataclasses.fields(self)}
    if key not in valid_fields:
      raise KeyError(f"Unknown configuration key: {key!r}")

    hints = typing.get_type_hints(self.__class__)
    expected = hints[key]

    if expected is float and isinstance(value, int):
      value = float(value)
    elif not isinstance(value, expected):
      try:
        value = expected(value)
      except (TypeError, ValueError):
        raise ValueError(
          f"Cannot convert {type(value).__name__!r} to "
          f"{expected.__name__!r} for key {key!r}"
        )

    if key == "plcMode":
      value = self.normalizePlcMode(value)

    setattr(self, key, value)
    self.save()
