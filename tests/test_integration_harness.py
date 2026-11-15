import sys

import pytest

from integration_smoke import Smoke


@pytest.mark.parametrize('code', [0, 7])
def test_wait_reports_unexpected_child_exit_with_its_log(tmp_path, code):
    smoke = Smoke(18080, tmp_path, timeout=2.)
    child = smoke.start_command('crashed-demo', [sys.executable, '-c', f'raise SystemExit({code})'])
    try:
        child.wait(timeout=2.)
        with pytest.raises(AssertionError, match=f'crashed-demo exited unexpectedly with code {code}') as error:
            smoke.wait(lambda: False, 'topic discovery')
        assert str(tmp_path / 'crashed-demo.log') in str(error.value)
        assert 'topic discovery' in str(error.value)
    finally:
        smoke.stop(child)
        for _, _, log in smoke.processes:
            log.close()


def test_wait_ignores_a_child_after_explicit_stop(tmp_path):
    smoke = Smoke(18080, tmp_path, timeout=2.)
    child = smoke.start_command('finished-demo', [sys.executable, '-c', 'pass'])
    child.wait(timeout=2.)
    smoke.stop(child)
    try:
        assert smoke.wait(lambda: 'ready', 'next phase') == 'ready'
    finally:
        for _, _, log in smoke.processes:
            log.close()
