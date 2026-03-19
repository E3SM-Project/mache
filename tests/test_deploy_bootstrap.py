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


def test_write_bootstrap_pixi_toml_with_mache_includes_platform(
    monkeypatch, tmp_path: Path
):
    monkeypatch.setattr(bootstrap, '_get_pixi_platform', lambda: 'linux-64')

    pixi_toml = tmp_path / 'pixi.toml'
    bootstrap._write_bootstrap_pixi_toml_with_mache(
        pixi_toml_path=pixi_toml,
        software='polaris',
        mache_version='3.0.0',
        python_version='3.12',
    )

    text = pixi_toml.read_text(encoding='utf-8')
    assert 'platforms = ["linux-64"]' in text
    assert 'mache = "==3.0.0"' in text


def test_clone_mache_repo_uses_local_source_override(
    monkeypatch, tmp_path: Path
):
    monkeypatch.chdir(tmp_path)

    source_repo = tmp_path / 'local-mache'
    source_repo.mkdir()
    (source_repo / 'pixi.toml').write_text(
        '[workspace]\nname = "mache-dev"\n',
        encoding='utf-8',
    )

    monkeypatch.setenv(bootstrap.LOCAL_MACHE_SOURCE_ENV, str(source_repo))

    bootstrap._clone_mache_repo(
        mache_fork='ignored',
        mache_branch='ignored',
        log_filename=str(tmp_path / 'bootstrap.log'),
        quiet=True,
        recreate=False,
    )

    cloned_repo = tmp_path / 'deploy_tmp' / 'build_mache' / 'mache'
    assert cloned_repo.exists()
    assert (cloned_repo / 'pixi.toml').is_file()
