import logging
import os
import subprocess
from pathlib import Path

import pytest

from mache.spack.activation import (
    activation_file_path,
    activation_source_line,
    parse_env_before,
    parse_raw_activation,
    render_activation,
    rewrite_modifications,
    write_activation_files,
)
from mache.spack.script import get_spack_script

FIXTURES = Path(__file__).parent / 'spack_activation'
SPACK_PATH = '/home/xylar/scratch/spack-v1/instance'
VIEW = '/home/xylar/scratch/spack-v1/v1/.spack-env/view'


@pytest.fixture
def fixture_modifications():
    raw = parse_raw_activation((FIXTURES / 'raw_activate.sh').read_text())
    env_before = parse_env_before((FIXTURES / 'env_before').read_bytes())
    return raw, env_before, rewrite_modifications(raw, env_before)


def test_parse_env_before():
    env = parse_env_before(b'A=1\0PATH=/a:/b\0MULTI=x\ny\0\0')
    assert env == {'A': '1', 'PATH': '/a:/b', 'MULTI': 'x\ny'}


def test_parse_raw_activation_fixture(fixture_modifications):
    raw, _, _ = fixture_modifications
    names = [entry[1] for entry in raw]
    assert names == [
        'SPACK_ENV',
        'SPACK_ENV_VIEW',
        'ACLOCAL_PATH',
        'CMAKE_PREFIX_PATH',
        'MANPATH',
        'PATH',
        'PKG_CONFIG_PATH',
    ]
    assert all(entry[0] == 'export' for entry in raw)


def test_parse_raw_activation_forms():
    raw = parse_raw_activation(
        "export A='x y';\n"
        "alias despacktivate='spack env deactivate';\n"
        'unset B;\n'
        '\n'
        'export C=plain;\n'
    )
    assert raw == [
        ('export', 'A', 'x y'),
        ('unset', 'B'),
        ('export', 'C', 'plain'),
    ]

    with pytest.raises(ValueError, match='Unexpected line'):
        parse_raw_activation('echo hi;\n')


def test_rewrite_fixture(fixture_modifications):
    _, _, modifications = fixture_modifications
    by_name = {m[1]: m for m in modifications}

    # PATH carried the capturing shell's full value; only the view is new
    assert by_name['PATH'] == ('prepend', 'PATH', [f'{VIEW}/bin'])
    # MANPATH was unset before: all elements are new, trailing colon dropped
    assert by_name['MANPATH'] == (
        'prepend',
        'MANPATH',
        ['/usr/share/man', f'{VIEW}/share/man', f'{VIEW}/man'],
    )
    # elements from /usr externals are kept in spack's order
    assert by_name['PKG_CONFIG_PATH'][2] == [
        f'{VIEW}/lib/pkgconfig',
        '/usr/share/pkgconfig',
        '/usr/lib/pkgconfig',
        f'{VIEW}/share/pkgconfig',
        f'{VIEW}/lib64/pkgconfig',
    ]
    # literal variables
    assert by_name['SPACK_ENV'] == (
        'set',
        'SPACK_ENV',
        '/home/xylar/scratch/spack-v1/v1',
    )
    assert by_name['SPACK_ENV_VIEW'] == ('set', 'SPACK_ENV_VIEW', 'default')
    # the alias is gone
    assert not any('despacktivate' in str(m) for m in modifications)


def test_rewrite_unset_and_lost_elements(caplog):
    raw = [
        ('export', 'PATH', '/view/bin:/usr/bin'),
        ('unset', 'OLD'),
        ('export', 'ESMFMKFILE', '/view/lib/esmf.mk'),
        ('export', 'LD_LIBRARY_PATH', '/old/lib'),
    ]
    env_before = {
        'PATH': '/usr/bin:/removed/bin',
        'LD_LIBRARY_PATH': '/old/lib',
    }
    with caplog.at_level(logging.WARNING, logger='mache.spack.activation'):
        modifications = rewrite_modifications(raw, env_before)
    assert modifications == [
        ('prepend', 'PATH', ['/view/bin']),
        ('unset', 'OLD'),
        ('set', 'ESMFMKFILE', '/view/lib/esmf.mk'),
    ]
    assert '/removed/bin' in caplog.text
    assert 'PATH' in caplog.text


def test_render_sh(fixture_modifications):
    _, _, modifications = fixture_modifications
    text = render_activation(modifications, 'sh', SPACK_PATH)
    lines = text.splitlines()
    assert f'export SPACK_ROOT="{SPACK_PATH}"' in lines
    assert f'export PATH="{SPACK_PATH}/bin${{PATH:+:$PATH}}"' in lines
    assert f'export PATH="{VIEW}/bin${{PATH:+:$PATH}}"' in lines
    assert (
        f'export MANPATH="/usr/share/man:{VIEW}/share/man:{VIEW}/man:'
        '${MANPATH:-}"'
    ) in lines
    assert 'export SPACK_ENV_VIEW="default"' in lines
    # SPACK_ROOT/bin comes first so it ends up after the view on PATH
    assert lines.index(f'export PATH="{SPACK_PATH}/bin${{PATH:+:$PATH}}"') < (
        lines.index(f'export PATH="{VIEW}/bin${{PATH:+:$PATH}}"')
    )


def test_render_csh(fixture_modifications):
    _, _, modifications = fixture_modifications
    text = render_activation(modifications, 'csh', SPACK_PATH)
    assert f'setenv SPACK_ROOT "{SPACK_PATH}"' in text
    assert (
        'if ($?PATH) then\n'
        f'  setenv PATH "{VIEW}/bin:$PATH"\n'
        'else\n'
        f'  setenv PATH "{VIEW}/bin"\n'
        'endif\n'
    ) in text
    assert (
        f'  setenv MANPATH "/usr/share/man:{VIEW}/share/man:{VIEW}/man:"\n'
    ) in text
    assert 'setenv SPACK_ENV_VIEW "default"' in text


def test_render_unset_and_quoting():
    modifications = [
        ('unset', 'OLD'),
        ('set', 'MSG', 'a "b" $c'),
        ('prepend', 'PATH', ['/dir with space/bin']),
    ]
    sh = render_activation(modifications, 'sh', '/opt/spack')
    assert 'unset OLD' in sh
    assert 'export MSG="a \\"b\\" \\$c"' in sh
    assert 'export PATH="/dir with space/bin${PATH:+:$PATH}"' in sh
    csh = render_activation(modifications, 'csh', '/opt/spack')
    assert 'unsetenv OLD' in csh
    assert 'setenv MSG "a \\"b\\" \\$c"' in csh


def test_sourcing_sh_prepends(tmp_path: Path):
    """Source the rendered sh snippet in bash and check the resulting
    environment against the design's rules."""
    modifications = [
        ('set', 'SPACK_ENV', '/env'),
        ('prepend', 'PATH', ['/view/bin']),
        ('prepend', 'MANPATH', ['/view/man']),
        ('prepend', 'CMAKE_PREFIX_PATH', ['/view']),
    ]
    snippet = tmp_path / 'activate.sh'
    snippet.write_text(render_activation(modifications, 'sh', '/opt/spack'))
    result = subprocess.run(
        ['bash', '-c', f'source {snippet}; env'],
        capture_output=True,
        text=True,
        env={'PATH': '/usr/bin:/bin', 'CMAKE_PREFIX_PATH': '/old'},
        check=True,
    )
    env = dict(line.split('=', 1) for line in result.stdout.splitlines())
    assert env['PATH'] == '/view/bin:/opt/spack/bin:/usr/bin:/bin'
    assert env['MANPATH'] == '/view/man:'
    assert env['CMAKE_PREFIX_PATH'] == '/view:/old'
    assert env['SPACK_ENV'] == '/env'
    assert env['SPACK_ROOT'] == '/opt/spack'


def test_write_activation_files(tmp_path: Path):
    env_dir = tmp_path / 'var' / 'spack' / 'environments' / 'dev'
    env_dir.mkdir(parents=True)
    paths = write_activation_files(
        spack_path=str(tmp_path),
        env_name='dev',
        modifications=[('set', 'A', '1')],
    )
    assert paths == (
        activation_file_path(str(tmp_path), 'dev', 'sh'),
        activation_file_path(str(tmp_path), 'dev', 'csh'),
    )
    assert os.path.dirname(paths[0]) == str(env_dir)
    assert 'export A="1"' in Path(paths[0]).read_text()
    assert 'setenv A "1"' in Path(paths[1]).read_text()


def test_activation_source_line():
    assert (
        activation_source_line('/opt/spack', 'dev', 'sh')
        == 'source /opt/spack/var/spack/environments/dev/activate.sh'
    )
    assert activation_source_line('/opt/spack', 'dev', 'csh').endswith(
        'activate.csh'
    )


@pytest.mark.parametrize('shell', ['sh', 'csh'])
def test_get_spack_script_activation_modes(shell):
    captured = get_spack_script(
        spack_path='/opt/spack',
        env_name='dev',
        compiler='gnu',
        mpi='openmpi',
        shell=shell,
        machine='chrysalis',
        load_spack_env=True,
    )
    assert captured.startswith(
        f'source /opt/spack/var/spack/environments/dev/activate.{shell}\n'
    )
    assert 'spack env activate' not in captured

    dynamic = get_spack_script(
        spack_path='/opt/spack',
        env_name='dev',
        compiler='gnu',
        mpi='openmpi',
        shell=shell,
        machine='chrysalis',
        load_spack_env=True,
        activation='dynamic',
    )
    assert dynamic.startswith(
        f'source /opt/spack/share/spack/setup-env.{shell}\n'
        'spack env activate dev\n'
    )
    # the rest (config_machines.xml modules) is the same in both
    assert captured.split('\n', 1)[1] == dynamic.split('\n', 2)[2]

    with pytest.raises(ValueError, match='activation'):
        get_spack_script(
            spack_path='/opt/spack',
            env_name='dev',
            compiler='gnu',
            mpi='openmpi',
            shell=shell,
            machine='chrysalis',
            activation='eager',
        )
