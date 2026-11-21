"""No-audio-change tests for Windows absolute volume mapping."""
import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from windows_volume import get_master_volume_percent, set_master_volume_percent


class WindowsVolumeTests(TestCase):
    def test_full_range_and_midpoint(self):
        for percent in (0, 1, 30, 50, 75, 99, 100):
            with self.subTest(percent=percent), patch("windows_volume._volume_call") as call:
                set_master_volume_percent(percent)
                call.assert_called_once_with(percent / 100)

    def test_rejects_outside_range(self):
        for value in (-1, 101, float("nan"), float("inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    set_master_volume_percent(value)

    def test_read_only_value(self):
        with patch("windows_volume._volume_call", return_value=0.3) as call:
            self.assertEqual(get_master_volume_percent(), 30)
            call.assert_called_once_with(None)
