import os
import shutil
import subprocess
import sys
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
    deploy_dir = repo_root / 'deploy'
    overrides_dir = fixtures_dir() / overrides_name
    relpaths = ('config.yaml.j2', 'pixi.toml.j2', 'load.sh')
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
    return subprocess.run(
        args,
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )


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
