import subprocess
from pathlib import Path

import pytest

from mache.spack.install import (
    prologue_path,
    render_install_script,
    write_prologue,
)
from mache.spack.pins import load_pins


def _render(pins, **kwargs):
    args = dict(
        spack_path='/opt/spack',
        env_name='dev_gnu_openmpi',
        yaml_path='/work/dev_gnu_openmpi.yaml',
        prologue='module load gcc\nexport TMPDIR=/tmp/build',
        pins=pins,
        work_dir='/work',
    )
    args.update(kwargs)
    return render_install_script(**args)


def test_render_with_tags():
    script = _render(load_pins())
    assert script.startswith('#!/bin/bash')
    assert 'module load gcc\nexport TMPDIR=/tmp/build' in script
    assert 'git clone https://github.com/spack/spack.git /opt/spack' in script
    assert 'git -C /opt/spack reset --hard refs/tags/v1.2.2' in script
    assert (
        'git -C /opt/spack/var/spack/package_repos/builtin reset --hard '
        'refs/tags/v2026.06.0'
    ) in script
    assert 'spack isolate --self' in script
    assert 'spack repo list' in script
    assert 'spack env create "$env_name" /work/dev_gnu_openmpi.yaml' in script
    assert 'spack install\n' in script
    assert (
        'cp "$env_dir/spack.lock" /work/dev_gnu_openmpi.spack.lock' in script
    )
    assert '/work/dev_gnu_openmpi.provenance.yaml' in script
    # search order: e3sm before builtin in repos.yaml and in the checkouts
    assert script.index('e3sm:') < script.index('builtin:')
    assert script.index('package_repos/e3sm') < script.index(
        'package_repos/builtin'
    )


def test_render_with_commit_and_branch():
    pins = load_pins(
        {
            'spack': {'commit': '0123abcd'},
            'repos': {'e3sm': {'branch': 'my-fix'}},
        }
    )
    script = _render(pins)
    assert 'git -C /opt/spack reset --hard 0123abcd' in script
    assert (
        'git -C /opt/spack/var/spack/package_repos/e3sm reset --hard '
        'origin/my-fix'
    ) in script


def test_render_options():
    script = _render(
        load_pins(),
        mirror='/mirrors/spack',
        custom_spack='spack find\n',
        build_jobs=8,
    )
    assert 'spack mirror add spack_mirror file:///mirrors/spack' in script
    assert 'spack install -j 8' in script
    assert script.rstrip().endswith('spack find')


def test_legacy_check_present_and_old_names_gone():
    script = _render(load_pins())
    assert 'lib/spack/spack/__init__.py' in script
    assert 'Choose a new spack_path' in script
    assert 'spack_for_mache' not in script
    assert 'SPACK_PYTHON' not in script
    assert 'E3SM-Project/spack.git' not in script


@pytest.mark.parametrize(
    'version, refused',
    [('0.23.1', True), ('0.9', True), ('1.2.2', False), ('2.0.0', False)],
)
def test_legacy_check_runs(tmp_path: Path, version, refused):
    """The refusal runs before any git command, so it can be exercised by
    running the script with a fake checkout and no network."""
    spack_path = tmp_path / 'spack'
    init = spack_path / 'lib' / 'spack' / 'spack'
    init.mkdir(parents=True)
    (init / '__init__.py').write_text(f'__version__ = "{version}"\n')
    script = _render(
        load_pins(), spack_path=str(spack_path), prologue='', work_dir=''
    )
    # stop right after the check
    script = script.split('# Spack itself')[0] + 'echo PASSED_CHECK\n'
    result = subprocess.run(
        ['bash', '-c', script], capture_output=True, text=True
    )
    if refused:
        assert result.returncode == 1
        assert 'Choose a new spack_path' in result.stderr
    else:
        assert result.returncode == 0, result.stderr
        assert 'PASSED_CHECK' in result.stdout


def test_write_prologue(tmp_path: Path):
    path = write_prologue(str(tmp_path), 'env', '\nmodule load x\n')
    assert path == prologue_path(str(tmp_path), 'env')
    assert Path(path).name == 'env.prologue.sh'
    assert Path(path).read_text() == 'module load x\n'
