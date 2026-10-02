"""Actual usb.c, with MMIO and the SDK's destructive SysTick delay modelled."""
import subprocess
import pytest
from conftest import PROJECT


@pytest.fixture(scope='session')
def usb_scheduler(tmp_path_factory):
    path = tmp_path_factory.mktemp('usb') / 'scheduler'
    subprocess.run([
        'cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
        '-I'+str(PROJECT/'tests/usb_mock'), '-I'+str(PROJECT/'include'),
        str(PROJECT/'src/usb.c'), str(PROJECT/'tests/usb_mock.c'), '-o', str(path),
    ], check=True)
    return path


@pytest.mark.parametrize('args', [[], ['mode-change']])
def test_reply_does_not_need_another_usb_request(usb_scheduler, args):
    subprocess.run([str(usb_scheduler), *args], check=True)
