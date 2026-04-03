import unittest

from dune_winder.core.x_backlash_compensation import XBacklashCompensation


class XBacklashCompensationTests(unittest.TestCase):
  def test_zero_backlash_is_noop(self):
    compensation = XBacklashCompensation(0.0)

    self.assertEqual(compensation.getEffectiveX(100.0), 100.0)
    self.assertEqual(compensation.getCommandedRawX(100.0, 120.0), 120.0)

  def test_positive_direction_applies_backlash_bias(self):
    compensation = XBacklashCompensation(2.0)

    compensation.noteCommand(100.0, 110.0)

    self.assertEqual(compensation.getDirection(), 1)
    self.assertEqual(compensation.getEffectiveX(112.0), 110.0)
    self.assertEqual(compensation.getCommandedRawX(112.0, 115.0), 117.0)

  def test_reversal_to_negative_removes_positive_bias(self):
    compensation = XBacklashCompensation(2.0)
    compensation.noteCommand(100.0, 110.0)

    rawTarget = compensation.getCommandedRawX(112.0, 109.0)
    compensation.noteCommand(112.0, 109.0)

    self.assertEqual(rawTarget, 109.0)
    self.assertEqual(compensation.getDirection(), -1)
    self.assertEqual(compensation.getEffectiveX(109.0), 109.0)

  def test_reset_clears_direction_bias(self):
    compensation = XBacklashCompensation(2.0)
    compensation.noteCommand(100.0, 110.0)

    compensation.reset()

    self.assertEqual(compensation.getDirection(), 0)
    self.assertEqual(compensation.getEffectiveX(112.0), 112.0)


if __name__ == "__main__":
  unittest.main()
