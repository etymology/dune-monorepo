import unittest

from dune_winder.library.remote_command import isReadOnlyRemoteCommand


class RemoteCommandTests(unittest.TestCase):
  def test_simple_getter_queries_are_read_only(self):
    self.assertTrue(isReadOnlyRemoteCommand('io.Z_Stage_Present.get()'))
    self.assertTrue(
      isReadOnlyRemoteCommand('configuration.get( "maxAcceleration" )')
    )
    self.assertTrue(isReadOnlyRemoteCommand("LowLevelIO.getInputs()"))
    self.assertTrue(isReadOnlyRemoteCommand("process._cameraURL"))

  def test_bracketed_getter_lists_are_read_only(self):
    self.assertTrue(
      isReadOnlyRemoteCommand(
        "[ io.Z_Stage_Present.get(), io.Z_Fixed_Present.get() ]"
      )
    )
    self.assertTrue(
      isReadOnlyRemoteCommand(
        "[ io.plc.isNotFunctional(), io.xAxis.isFunctional(),"
        + " io.yAxis.isFunctional(), io.zAxis.isFunctional(),"
        + " LowLevelIO.getInputs() ]"
      )
    )

  def test_mixed_list_with_mutating_call_is_not_read_only(self):
    self.assertFalse(
      isReadOnlyRemoteCommand(
        "[ io.Z_Stage_Present.get(), process.acknowledgeError() ]"
      )
    )

  def test_nested_call_in_getter_arguments_is_not_read_only(self):
    self.assertFalse(
      isReadOnlyRemoteCommand("configuration.get( process.acknowledgeError() )")
    )
