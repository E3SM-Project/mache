import argparse
import subprocess
from pathlib import Path

import pytest

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


def test_check_call_logs_effective_working_directory(
    monkeypatch, tmp_path: Path
):
    working_dir = tmp_path / 'workdir'
    working_dir.mkdir()

    def fake_popen(commands, **kwargs):
        return _FakeProcess(stdout=['hello\n'])

    monkeypatch.setattr(bootstrap.subprocess, 'Popen', fake_popen)

    log_filename = tmp_path / 'bootstrap.log'
    bootstrap.check_call(
        ['pixi', 'install'],
        str(log_filename),
        quiet=True,
        capture_output=True,
        cwd=working_dir,
    )

    log_text = log_filename.read_text(encoding='utf-8')
    assert f' Running from:\n   {working_dir}\n' in log_text
    assert ' Running:\n   pixi install\n' in log_text


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


def test_build_pixi_env_pins_default_cache_dir(monkeypatch):
    monkeypatch.delenv('PIXI_CACHE_DIR', raising=False)
    monkeypatch.setattr(
        bootstrap, 'default_pixi_cache_dir', lambda env: '/disk/pixi-cache'
    )

    env = bootstrap.build_pixi_env()

    assert env['PIXI_CACHE_DIR'] == '/disk/pixi-cache'


def test_build_pixi_env_leaves_cache_dir_to_pixi_without_default(
    monkeypatch,
):
    monkeypatch.delenv('PIXI_CACHE_DIR', raising=False)
    monkeypatch.setattr(bootstrap, 'default_pixi_cache_dir', lambda env: None)

    env = bootstrap.build_pixi_env()

    assert 'PIXI_CACHE_DIR' not in env


def test_default_pixi_cache_dir_prefers_scheduler_scratch(tmp_path: Path):
    job_dir = tmp_path / 'job'
    job_dir.mkdir()
    env = {
        'USER': 'someone',
        'SLURM_TMPDIR': str(job_dir),
        'TMPDIR': str(tmp_path),
    }

    cache_dir = bootstrap.default_pixi_cache_dir(env, mounts=[('/', 'ext4')])

    assert cache_dir == str(job_dir / 'pixi-cache-someone')


def test_default_pixi_cache_dir_skips_memory_backed_candidates(
    tmp_path: Path,
):
    ram_dir = tmp_path / 'ram'
    ram_dir.mkdir()
    disk_dir = tmp_path / 'disk'
    disk_dir.mkdir()
    env = {
        'LOGNAME': 'someone',
        'SLURM_TMPDIR': str(ram_dir),
        'TMPDIR': str(disk_dir),
    }
    mounts = [('/', 'ext4'), (str(ram_dir), 'tmpfs')]

    cache_dir = bootstrap.default_pixi_cache_dir(env, mounts=mounts)

    assert cache_dir == str(disk_dir / 'pixi-cache-someone')


def test_default_pixi_cache_dir_skips_missing_and_unwritable(
    tmp_path: Path,
):
    unwritable = tmp_path / 'unwritable'
    unwritable.mkdir(mode=0o500)
    disk_dir = tmp_path / 'disk'
    disk_dir.mkdir()
    env = {
        'USER': 'someone',
        'SLURM_TMPDIR': str(tmp_path / 'missing'),
        'PBS_JOBFS': str(unwritable),
        'TMPDIR': str(disk_dir),
    }
    try:
        cache_dir = bootstrap.default_pixi_cache_dir(
            env, mounts=[('/', 'ext4')]
        )
    finally:
        unwritable.chmod(0o700)

    assert cache_dir == str(disk_dir / 'pixi-cache-someone')


def test_default_pixi_cache_dir_falls_back_to_scratch(tmp_path: Path):
    scratch = tmp_path / 'scratch'
    scratch.mkdir()
    env = {'USER': 'someone', 'SCRATCH': str(scratch)}

    # Everything is memory-backed, so no local candidate qualifies.
    cache_dir = bootstrap.default_pixi_cache_dir(env, mounts=[('/', 'tmpfs')])

    assert cache_dir == str(scratch / 'pixi-cache')


def test_default_pixi_cache_dir_leaves_choice_to_pixi(tmp_path: Path):
    env = {'USER': 'someone', 'SCRATCH': str(tmp_path / 'missing')}

    cache_dir = bootstrap.default_pixi_cache_dir(env, mounts=[('/', 'tmpfs')])

    assert cache_dir is None


def test_is_memory_backed_uses_longest_mount_prefix(tmp_path: Path):
    inner = tmp_path / 'inner'
    inner.mkdir()
    mounts = [
        ('/', 'ext4'),
        (str(tmp_path), 'tmpfs'),
        (str(inner), 'xfs'),
    ]

    assert bootstrap._is_memory_backed(str(tmp_path), mounts=mounts)
    assert not bootstrap._is_memory_backed(str(inner), mounts=mounts)
    assert not bootstrap._is_memory_backed('/', mounts=mounts)


def test_is_memory_backed_without_mount_table():
    assert not bootstrap._is_memory_backed('/tmp', mounts=[])


def test_read_mounts_decodes_escaped_mount_points(monkeypatch, tmp_path: Path):
    mounts_file = tmp_path / 'mounts'
    mounts_file.write_text(
        'tmpfs /tmp tmpfs rw,nosuid 0 0\n'
        '/dev/sda1 /mnt/with\\040space ext4 rw 0 0\n'
        'garbage\n',
        encoding='utf-8',
    )
    real_open = open

    def fake_open(path, *args, **kwargs):
        if path == '/proc/self/mounts':
            path = mounts_file
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr('builtins.open', fake_open)

    assert bootstrap._read_mounts() == [
        ('/tmp', 'tmpfs'),
        ('/mnt/with space', 'ext4'),
    ]


def test_read_mounts_tolerates_missing_proc(monkeypatch):
    def fake_open(path, *args, **kwargs):
        raise FileNotFoundError(path)

    monkeypatch.setattr('builtins.open', fake_open)

    assert bootstrap._read_mounts() == []


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


def _fail_check_call(failures, monkeypatch):
    """Make ``check_call`` fail ``failures`` times, then succeed."""
    calls = {'count': 0}

    def fake_check_call(commands, log_file, is_quiet, **kwargs):
        calls['count'] += 1
        if calls['count'] <= failures:
            raise subprocess.CalledProcessError(1, commands)
        return 'ok'

    monkeypatch.setattr(bootstrap, 'check_call', fake_check_call)
    monkeypatch.setattr(bootstrap.time, 'sleep', lambda seconds: None)
    return calls


def test_check_call_with_retries_skips_on_retry_when_first_try_works(
    monkeypatch, tmp_path: Path
):
    log_filename = str(tmp_path / 'bootstrap.log')
    _fail_check_call(0, monkeypatch)
    retries = []

    result = bootstrap.check_call_with_retries(
        ['pixi', 'install'],
        log_filename,
        True,
        on_retry=lambda: retries.append(1),
    )

    assert result == 'ok'
    assert retries == []


def test_check_call_with_retries_calls_on_retry_between_attempts(
    monkeypatch, tmp_path: Path
):
    log_filename = str(tmp_path / 'bootstrap.log')
    calls = _fail_check_call(2, monkeypatch)
    retries = []

    result = bootstrap.check_call_with_retries(
        ['pixi', 'install'],
        log_filename,
        True,
        on_retry=lambda: retries.append(1),
    )

    assert result == 'ok'
    assert calls['count'] == 3
    assert len(retries) == 2


def test_check_call_with_retries_never_calls_on_retry_after_last_failure(
    monkeypatch, tmp_path: Path
):
    log_filename = str(tmp_path / 'bootstrap.log')
    calls = _fail_check_call(5, monkeypatch)
    retries = []

    with pytest.raises(subprocess.CalledProcessError):
        bootstrap.check_call_with_retries(
            ['pixi', 'install'],
            log_filename,
            True,
            retries=3,
            on_retry=lambda: retries.append(1),
        )

    assert calls['count'] == 3
    assert len(retries) == 2


def test_check_call_with_retries_ignores_on_retry_failures(
    monkeypatch, tmp_path: Path
):
    log_filename = str(tmp_path / 'bootstrap.log')
    _fail_check_call(5, monkeypatch)

    def broken_on_retry():
        raise RuntimeError('cache clear exploded')

    with pytest.raises(subprocess.CalledProcessError):
        bootstrap.check_call_with_retries(
            ['pixi', 'install'],
            log_filename,
            True,
            retries=3,
            on_retry=broken_on_retry,
        )

    log_text = Path(log_filename).read_text(encoding='utf-8')
    assert 'cache clear exploded' in log_text


def test_clear_pixi_repodata_cache_runs_pixi_clean_cache(
    monkeypatch, tmp_path: Path
):
    recorded = {}

    def fake_check_call(commands, log_filename, quiet, **kwargs):
        recorded['commands'] = commands
        recorded['kwargs'] = kwargs

    monkeypatch.setattr(bootstrap, 'check_call', fake_check_call)
    monkeypatch.setenv('PIXI_CACHE_DIR', str(tmp_path / 'pixi-cache'))

    bootstrap._clear_pixi_repodata_cache(
        pixi_exe='/path/to/pixi',
        log_filename=str(tmp_path / 'bootstrap.log'),
        quiet=True,
    )

    assert recorded['commands'] == [
        '/path/to/pixi',
        'clean',
        'cache',
        '--repodata',
        '-y',
    ]
    env = recorded['kwargs']['env']
    assert env['PIXI_CACHE_DIR'] == str(tmp_path / 'pixi-cache')
    assert 'PIXI_IN_SHELL' not in env


def test_clear_pixi_repodata_cache_tolerates_failure(
    monkeypatch, tmp_path: Path
):
    def fake_check_call(commands, log_filename, quiet, **kwargs):
        raise subprocess.CalledProcessError(1, commands)

    monkeypatch.setattr(bootstrap, 'check_call', fake_check_call)

    log_filename = tmp_path / 'bootstrap.log'
    bootstrap._clear_pixi_repodata_cache(
        pixi_exe='/path/to/pixi',
        log_filename=str(log_filename),
        quiet=True,
    )

    log_text = log_filename.read_text(encoding='utf-8')
    assert 'Could not clear the pixi repodata cache' in log_text


def _stub_bootstrap_run(monkeypatch, tmp_path: Path, *, dev_mache):
    """Stub out everything ``_run`` does apart from the pixi install."""
    monkeypatch.chdir(tmp_path)

    args = argparse.Namespace(
        software='polaris',
        quiet=True,
        mache_version='3.11.0',
        pixi=None,
        pixi_path=None,
        python='3.12',
        recreate=False,
        mache_fork='E3SM-Project/mache' if dev_mache else None,
        mache_branch='main' if dev_mache else None,
    )

    monkeypatch.setattr(bootstrap, '_parse_args', lambda: args)
    monkeypatch.setattr(bootstrap, 'check_location', lambda software: None)
    monkeypatch.setattr(
        bootstrap,
        '_get_pixi_executable',
        lambda pixi, log_filename, quiet: '/path/to/pixi',
    )
    monkeypatch.setattr(
        bootstrap,
        '_write_bootstrap_pixi_config',
        lambda bootstrap_dir: None,
    )
    monkeypatch.setattr(
        bootstrap,
        '_clone_mache_repo',
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        bootstrap,
        '_copy_mache_pixi_toml',
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        bootstrap,
        '_write_bootstrap_pixi_toml_with_mache',
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        bootstrap,
        'build_pixi_shell_hook_prefix',
        lambda **kwargs: 'prefix &&',
    )
    monkeypatch.setattr(
        bootstrap,
        'install_dev_mache',
        lambda **kwargs: None,
    )

    recorded = {}

    def fake_check_call_with_retries(commands, log_filename, quiet, **kwargs):
        recorded['commands'] = commands
        recorded['kwargs'] = kwargs

    monkeypatch.setattr(
        bootstrap,
        'check_call_with_retries',
        fake_check_call_with_retries,
    )

    cleared = []
    monkeypatch.setattr(
        bootstrap,
        '_clear_pixi_repodata_cache',
        lambda **kwargs: cleared.append(kwargs),
    )

    return recorded, cleared


@pytest.mark.parametrize('dev_mache', [True, False])
def test_run_clears_repodata_cache_between_install_attempts(
    monkeypatch, tmp_path: Path, dev_mache: bool
):
    recorded, cleared = _stub_bootstrap_run(
        monkeypatch, tmp_path, dev_mache=dev_mache
    )

    log_filename = str(tmp_path / 'bootstrap.log')
    bootstrap._run(log_filename)

    assert recorded['commands'] == ['/path/to/pixi', 'install']

    on_retry = recorded['kwargs']['on_retry']
    on_retry()

    assert cleared == [
        {
            'pixi_exe': '/path/to/pixi',
            'log_filename': log_filename,
            'quiet': True,
        }
    ]
