import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def fixtures_dir() -> Path:
    return repo_root() / 'workflow_tests' / 'fixtures'


def mache_version() -> str:
    namespace: dict[str, str] = {}
    exec(
        (repo_root() / 'mache' / 'version.py').read_text(encoding='utf-8'),
        namespace,
    )
    return namespace['__version__']


def copy_fixture_repo(fixture_name: str, dest: Path) -> None:
    shutil.copytree(fixtures_dir() / fixture_name, dest)


def configure_generated_deploy_files(
    repo_root: Path, overrides_name: str
) -> dict[str, str]:
    return configure_deploy_files(
        repo_root,
        overrides_name,
        relpaths=('config.yaml.j2', 'pixi.toml.j2', 'load.sh'),
    )


def configure_deploy_files(
    repo_root: Path, overrides_name: str, relpaths: tuple[str, ...]
) -> dict[str, str]:
    deploy_dir = repo_root / 'deploy'
    overrides_dir = fixtures_dir() / overrides_name
    expected: dict[str, str] = {}

    for relpath in relpaths:
        source = overrides_dir / relpath
        text = source.read_text(encoding='utf-8')
        (deploy_dir / relpath).write_text(text, encoding='utf-8')
        expected[relpath] = text

    return expected


def run(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            cwd=cwd,
            env=env,
            check=True,
            text=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        stdout = exc.stdout or ''
        stderr = exc.stderr or ''
        raise AssertionError(
            'Subprocess failed.\n'
            f'args: {exc.cmd}\n'
            f'cwd: {cwd}\n'
            f'returncode: {exc.returncode}\n'
            f'stdout:\n{stdout}\n'
            f'stderr:\n{stderr}'
        ) from exc


def make_workflow_env() -> dict[str, str]:
    env = os.environ.copy()

    pythonpath_entries = [str(repo_root())]
    pythonpath = env.get('PYTHONPATH')
    if pythonpath:
        pythonpath_entries.append(pythonpath)
    env['PYTHONPATH'] = os.pathsep.join(pythonpath_entries)

    env['MACHE_BOOTSTRAP_URL'] = (
        (repo_root() / 'mache' / 'deploy' / 'bootstrap.py').resolve().as_uri()
    )
    env['MACHE_LOCAL_SOURCE_PATH'] = str(repo_root())

    # Isolate nested pixi operations used by workflow tests from whatever
    # cache/home settings the outer shell or CI job happens to export.
    pixi_root = Path(tempfile.mkdtemp(prefix='mache-workflow-pixi-'))
    env['PIXI_HOME'] = str(pixi_root / 'home')
    env['RATTLER_CACHE_DIR'] = str(pixi_root / 'rattler-cache')
    env['PIXI_CACHE_DIR'] = str(pixi_root / 'pixi-cache')
    return env


def clone_jigsaw_python(*, dest: Path) -> None:
    result = subprocess.run(
        [
            'git',
            'clone',
            '--depth',
            '1',
            'https://github.com/dengwirda/jigsaw-python.git',
            str(dest),
        ],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            'Unable to clone jigsaw-python for workflow testing.\n'
            f'stdout:\n{result.stdout}\n'
            f'stderr:\n{result.stderr}'
        )


def init_and_update_repo(
    *,
    downstream: Path,
    software: str,
    env: dict[str, str],
) -> None:
    source_repo = repo_root()
    version = mache_version()

    run(
        [
            sys.executable,
            '-m',
            'mache',
            'deploy',
            'init',
            '--repo-root',
            str(downstream),
            '--software',
            software,
            '--mache-version',
            version,
        ],
        cwd=source_repo,
        env=env,
    )

    (downstream / 'deploy.py').write_text(
        '# stale deploy.py\n',
        encoding='utf-8',
    )
    (downstream / 'deploy' / 'cli_spec.json').write_text(
        '{"stale": true}\n',
        encoding='utf-8',
    )

    run(
        [
            sys.executable,
            '-m',
            'mache',
            'deploy',
            'update',
            '--repo-root',
            str(downstream),
            '--software',
            software,
            '--mache-version',
            version,
        ],
        cwd=source_repo,
        env=env,
    )
