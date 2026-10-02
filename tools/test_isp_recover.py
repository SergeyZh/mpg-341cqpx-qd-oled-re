"""Host-only checks: recovery guards, watchdog write and original F1D path."""

import unittest
from unittest.mock import Mock, patch

import isp_read


class RecoveryTests(unittest.TestCase):
    def bridge(self, descriptor=b'\xAA' + bytes(8), shared=bytes(0x9A), ear=b'\0'):
        br = Mock(dry=False)
        registers = dict(enumerate(descriptor, 0xF1D0))
        registers.update(enumerate(shared, 0x3000))
        br.read_reg.side_effect = registers.__getitem__
        br.jedec.return_value = b'\xc8\x40\x19'
        br.spi.return_value = ear
        br.heartbeat.return_value = b'5b00110000\r'
        br.sample_recovery_state.return_value = (0, 0, 0, 0, 0, 0)
        return br

    @patch.object(isp_read.time, 'sleep')
    def test_empty_recovery(self, sleep):
        br = self.bridge()
        isp_read.recover_stbc(br)
        br.write_reg.assert_called_once_with(0xF0E0, 0x55)
        br.spi.assert_called_once_with([0xC8], 1)
        br.exit.assert_called_once()
        br.reconnect_after_reset.assert_called_once()
        br.sample_recovery_state.assert_not_called()
        sleep.assert_called_once_with(7.0)

    def test_nonempty_shared_refused(self):
        br = self.bridge(shared=bytes(153) + b'\1')
        with self.assertRaises(RuntimeError):
            isp_read.recover_stbc(br)
        br.write_reg.assert_not_called()

    @patch.object(isp_read.time, 'sleep')
    def test_after_ff_sector_cycle(self, sleep):
        br = self.bridge(shared=b'\xFF' * 0x9A)
        isp_read.recover_stbc(br)
        br.write_reg.assert_called_once_with(0xF0E0, 0x55)

    def test_wrong_bank_refused(self):
        br = self.bridge(ear=b'\1')
        with self.assertRaises(RuntimeError):
            isp_read.recover_stbc(br)
        br.write_reg.assert_not_called()

    def test_wrong_flash_refused(self):
        br = self.bridge()
        br.jedec.return_value = b'\xff\xff\xff'
        with self.assertRaises(RuntimeError):
            isp_read.recover_stbc(br)
        br.write_reg.assert_not_called()

    def test_unknown_descriptor_refused(self):
        for descriptor in (bytes(9), b'\x87' + bytes(8), b'\xAA\1' + bytes(7)):
            br = self.bridge(descriptor=descriptor)
            with self.assertRaises(RuntimeError):
                isp_read.recover_stbc(br)
            br.write_reg.assert_not_called()

    @patch.object(isp_read.time, 'sleep')
    def test_original_completed_f1d(self, sleep):
        br = self.bridge(descriptor=isp_read.STBC_FW034_DESCRIPTOR)
        isp_read.recover_stbc(br)
        br.write_reg.assert_called_once_with(0xF1D0, 0x87)
        br.spi.assert_not_called()
        br.sample_recovery_state.assert_called_once()

    def test_dry_run(self):
        br = self.bridge()
        br.dry = True
        isp_read.recover_stbc(br)
        br.write_reg.assert_not_called()

    @patch.object(isp_read.time, 'sleep')
    def test_timeout_does_not_repeat_reset(self, sleep):
        br = self.bridge()
        br.heartbeat.side_effect = TimeoutError('no response')
        with self.assertRaises(isp_read.RecoveryVerificationUnavailable):
            isp_read.recover_stbc(br)
        br.write_reg.assert_called_once_with(0xF0E0, 0x55)
        self.assertEqual(br.heartbeat.call_count, 5)

    @patch.object(isp_read.time, 'sleep')
    def test_missing_usb_is_unverified_not_failed_boot(self, sleep):
        br = self.bridge(shared=b'\xFF' * 0x9A)
        br.reconnect_after_reset.side_effect = TimeoutError('U7005 absent')
        with self.assertRaisesRegex(isp_read.RecoveryVerificationUnavailable, 'Power Off'):
            isp_read.recover_stbc(br)
        br.write_reg.assert_called_once_with(0xF0E0, 0x55)
        br.heartbeat.assert_not_called()

    @patch.object(isp_read.time, 'sleep')
    def test_cli_unverified_exit_code(self, sleep):
        br = self.bridge()
        br.reconnect_after_reset.side_effect = TimeoutError('U7005 absent')
        with patch.object(isp_read, 'Bridge', return_value=br), \
             patch.object(isp_read.sys, 'argv', ['isp_read.py', '--recover', '--reuse']):
            with self.assertRaises(SystemExit) as caught:
                isp_read.main()
        self.assertEqual(caught.exception.code, 2)
        br.write_reg.assert_called_once_with(0xF0E0, 0x55)

    @patch.object(isp_read.time, 'sleep')
    def test_original_f1d_usb_timeout_is_unverified(self, sleep):
        br = self.bridge(descriptor=isp_read.STBC_FW034_DESCRIPTOR)
        br.reconnect_after_reset.side_effect = TimeoutError('U7005 absent')
        with self.assertRaises(isp_read.RecoveryVerificationUnavailable):
            isp_read.recover_stbc(br)
        br.write_reg.assert_called_once_with(0xF1D0, 0x87)


if __name__ == '__main__':
    unittest.main()
