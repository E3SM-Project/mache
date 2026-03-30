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


def test_check_call_list_commands_use_direct_popen_without_shell(
    monkeypatch, tmp_path: Path
):
    recorded = {}

    def fake_popen(commands, **kwargs):
        recorded['commands'] = commands
        recorded['kwargs'] = kwargs
        return _FakeProcess(stdout=['hello\n'])

    monkeypatch.setattr(bootstrap.subprocess, 'Popen', fake_popen)

    result = bootstrap.check_call(
        ['pixi', 'install'],
        str(tmp_path / 'bootstrap.log'),
        quiet=True,
        capture_output=True,
    )

    assert result.stdout == 'hello\n'
    assert recorded['commands'] == ['pixi', 'install']
    assert recorded['kwargs']['shell'] is False
    assert 'executable' not in recorded['kwargs']


def test_build_pixi_env_unsets_nested_pixi_variables(monkeypatch):
    monkeypatch.setenv('PIXI_PROJECT_MANIFEST', 'manifest')
    monkeypatch.setenv('PIXI_PROJECT_ROOT', 'root')
    monkeypatch.setenv('PIXI_ENVIRONMENT_NAME', 'env')
    monkeypatch.setenv('PIXI_IN_SHELL', '1')
    monkeypatch.setenv('KEEP_ME', 'ok')

    env = bootstrap.build_pixi_env()

    assert 'PIXI_PROJECT_MANIFEST' not in env
    assert 'PIXI_PROJECT_ROOT' not in env
    assert 'PIXI_ENVIRONMENT_NAME' not in env
    assert 'PIXI_IN_SHELL' not in env
    assert env['KEEP_ME'] == 'ok'


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


def test_write_bootstrap_pixi_toml_with_mache_preserves_wildcard_version(
    monkeypatch, tmp_path: Path
):
    monkeypatch.setattr(bootstrap, '_get_pixi_platform', lambda: 'linux-64')

    pixi_toml = tmp_path / 'pixi.toml'
    bootstrap._write_bootstrap_pixi_toml_with_mache(
        pixi_toml_path=pixi_toml,
        software='polaris',
        mache_version='3.0.2.*',
        python_version='3.12',
    )

    text = pixi_toml.read_text(encoding='utf-8')
    assert 'mache = "3.0.2.*"' in text
    assert 'mache = "==3.0.2.*"' not in text


def test_parse_args_accepts_new_pixi_path_flag(monkeypatch):
    monkeypatch.setattr(
        bootstrap.sys,
        'argv',
        [
            'bootstrap.py',
            '--software',
            'polaris',
            '--python',
            '3.12',
            '--mache-version',
            '3.0.0',
            '--pixi-path',
            '/tmp/pixi-env',
        ],
    )

    args = bootstrap._parse_args()

    assert args.pixi_path == '/tmp/pixi-env'


def test_parse_args_accepts_legacy_prefix_flag(monkeypatch):
    monkeypatch.setattr(
        bootstrap.sys,
        'argv',
        [
            'bootstrap.py',
            '--software',
            'polaris',
            '--python',
            '3.12',
            '--mache-version',
            '3.0.0',
            '--prefix',
            '/tmp/pixi-env',
        ],
    )

    args = bootstrap._parse_args()

    assert args.pixi_path == '/tmp/pixi-env'


def test_write_bootstrap_pixi_toml_with_mache_uses_mache_dev_for_rc(
    monkeypatch, tmp_path: Path
):
    monkeypatch.setattr(bootstrap, '_get_pixi_platform', lambda: 'linux-64')

    pixi_toml = tmp_path / 'pixi.toml'
    bootstrap._write_bootstrap_pixi_toml_with_mache(
        pixi_toml_path=pixi_toml,
        software='polaris',
        mache_version='3.3.0rc1',
        python_version='3.12',
    )

    text = pixi_toml.read_text(encoding='utf-8')
    assert (
        'channels = ["https://conda.anaconda.org/conda-forge/label/'
        'mache_dev", "conda-forge"]'
    ) in text


def test_write_bootstrap_pixi_toml_with_mache_uses_conda_forge_for_release(
    monkeypatch, tmp_path: Path
):
    monkeypatch.setattr(bootstrap, '_get_pixi_platform', lambda: 'linux-64')

    pixi_toml = tmp_path / 'pixi.toml'
    bootstrap._write_bootstrap_pixi_toml_with_mache(
        pixi_toml_path=pixi_toml,
        software='polaris',
        mache_version='3.3.0',
        python_version='3.12',
    )

    text = pixi_toml.read_text(encoding='utf-8')
    assert 'channels = ["conda-forge"]' in text


def test_get_bootstrap_channels_for_mache_version_detects_rc():
    channels = bootstrap._get_bootstrap_channels_for_mache_version('3.3.0rc1')

    assert channels == [
        'https://conda.anaconda.org/conda-forge/label/mache_dev',
        'conda-forge',
    ]


def test_get_bootstrap_channels_for_mache_version_uses_release_channel():
    channels = bootstrap._get_bootstrap_channels_for_mache_version('3.3.0')

    assert channels == ['conda-forge']


def test_write_bootstrap_pixi_config_adds_label_mirror(tmp_path: Path):
    bootstrap._write_bootstrap_pixi_config(bootstrap_dir=tmp_path)

    config_toml = tmp_path / '.pixi' / 'config.toml'
    text = config_toml.read_text(encoding='utf-8')
    assert config_toml.is_file()
    assert '[mirrors]' in text
    assert '"https://conda.anaconda.org/conda-forge/label" = [' in text


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


def test_merge_pixi_toml_dependencies_merges_runtime_and_dev_deps(
    tmp_path: Path,
):
    source_repo = tmp_path / 'mache-source'
    source_repo.mkdir()
    (source_repo / 'pixi.toml').write_text(
        '[workspace]\n'
        'name = "mache-dev"\n'
        'channels = ["conda-forge"]\n'
        '\n'
        '[dependencies]\n'
        'python = ">=3.10,<3.15"\n'
        'lxml = "*"\n'
        'rsync = "*"\n'
        'ruff = "*"\n'
        '\n'
        '[feature.py314.dependencies]\n'
        'python = "3.14.*"\n',
        encoding='utf-8',
    )

    target = tmp_path / 'target-pixi.toml'
    target.write_text(
        '[workspace]\n'
        'name = "downstream-dev"\n'
        'channels = ["conda-forge"]\n'
        '\n'
        '[dependencies]\n'
        'python = "3.14.*"\n'
        'pip = "*"\n',
        encoding='utf-8',
    )

    bootstrap.merge_pixi_toml_dependencies(
        target_pixi_toml=str(target),
        source_repo_dir=str(source_repo),
        python_version='3.14',
    )

    text = target.read_text(encoding='utf-8')
    assert 'python = "3.14.*"' in text
    assert 'lxml = "*"' in text
    assert 'rsync = "*"' in text
    assert 'ruff = "*"' in text


def test_merge_pixi_toml_dependencies_adds_missing_channels(
    tmp_path: Path,
):
    source_repo = tmp_path / 'mache-source'
    source_repo.mkdir()
    (source_repo / 'pixi.toml').write_text(
        '[workspace]\n'
        'name = "mache-dev"\n'
        'channels = ["conda-forge", "custom"]\n'
        '\n'
        '[dependencies]\n'
        'python = ">=3.10,<3.15"\n'
        'requests = "*"\n',
        encoding='utf-8',
    )

    target = tmp_path / 'target-pixi.toml'
    target.write_text(
        '[workspace]\n'
        'name = "downstream-dev"\n'
        'channels = ["conda-forge"]\n'
        '\n'
        '[dependencies]\n'
        'python = "3.14.*"\n',
        encoding='utf-8',
    )

    bootstrap.merge_pixi_toml_dependencies(
        target_pixi_toml=str(target),
        source_repo_dir=str(source_repo),
        python_version='3.14',
    )

    text = target.read_text(encoding='utf-8')
    assert 'channels = ["conda-forge", "custom"]' in text
