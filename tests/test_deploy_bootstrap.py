from pathlib import Path

from mache.deploy import bootstrap


class _FakeProcess:
    def __init__(self, stdout, returncode=0):
        self.stdout = stdout
        self.returncode = returncode

    def wait(self):
        return self.returncode


def test_check_call_uses_universal_newlines_for_text_mode(
    monkeypatch, tmp_path: Path
):
    recorded = {}

    def fake_popen(commands, **kwargs):
        recorded['commands'] = commands
        recorded['kwargs'] = kwargs
        return _FakeProcess(stdout=['hello\n'])

    monkeypatch.setattr(bootstrap.subprocess, 'Popen', fake_popen)

    result = bootstrap.check_call(
        'printf hello',
        str(tmp_path / 'bootstrap.log'),
        quiet=True,
        capture_output=True,
    )

    assert result.stdout == 'hello\n'
    assert recorded['commands'] == 'printf hello'
    assert 'text' not in recorded['kwargs']
    assert recorded['kwargs']['universal_newlines'] is True


def test_check_call_binary_mode_still_uses_popen_compatible_kwargs(
    monkeypatch, tmp_path: Path
):
    recorded = {}

    def fake_popen(commands, **kwargs):
        recorded['commands'] = commands
        recorded['kwargs'] = kwargs
        return _FakeProcess(stdout=[b'hello\n'])

    monkeypatch.setattr(bootstrap.subprocess, 'Popen', fake_popen)

    result = bootstrap.check_call(
        'printf hello',
        str(tmp_path / 'bootstrap.log'),
        quiet=True,
        capture_output=True,
        text=False,
    )

    assert result.stdout == 'hello\n'
    assert recorded['commands'] == 'printf hello'
    assert 'text' not in recorded['kwargs']
    assert recorded['kwargs']['universal_newlines'] is False
