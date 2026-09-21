from pathlib import Path

import pytest
from yaml import safe_dump, safe_load

from mache.spack.pins import (
    checkout_command,
    checkout_ref,
    load_pins,
    merge_pins,
    release_pins_are_valid,
    render_repos_yaml,
    validate_pins,
)
from mache.version import __version__


def _base():
    return {
        'spack': {
            'git': 'https://github.com/spack/spack.git',
            'tag': 'v1.2.2',
        },
        'repos': {
            'e3sm': {
                'git': 'https://github.com/E3SM-Project/e3sm-spack-packages.git',
                'tag': 'v2026.06.0',
            },
            'builtin': {
                'git': 'https://github.com/spack/spack-packages.git',
                'tag': 'v2026.06.0',
            },
        },
    }


def test_packaged_pins_are_valid():
    pins = load_pins()
    validate_pins(pins)
    assert list(pins['repos']) == ['e3sm', 'builtin']
    assert release_pins_are_valid(pins, __version__)


def test_merge_branch_replaces_tag():
    merged = merge_pins(_base(), {'repos': {'e3sm': {'branch': 'main'}}})
    assert merged['repos']['e3sm'] == {
        'git': 'https://github.com/E3SM-Project/e3sm-spack-packages.git',
        'branch': 'main',
    }
    # other repositories and the base are untouched
    assert merged['repos']['builtin'] == _base()['repos']['builtin']
    assert 'tag' in _base()['repos']['e3sm']


def test_merge_can_change_git_and_spack():
    merged = merge_pins(
        _base(),
        {
            'spack': {'commit': 'abc123'},
            'repos': {
                'e3sm': {
                    'git': 'https://github.com/xylar/e3sm-spack-packages.git'
                }
            },
        },
    )
    assert merged['spack'] == {
        'git': 'https://github.com/spack/spack.git',
        'commit': 'abc123',
    }
    assert merged['repos']['e3sm'] == {
        'git': 'https://github.com/xylar/e3sm-spack-packages.git',
        'tag': 'v2026.06.0',
    }


def test_merge_cannot_add_repos():
    with pytest.raises(ValueError, match='cannot add'):
        merge_pins(_base(), {'repos': {'other': {'branch': 'main'}}})


def test_merge_rejects_unknown_keys():
    with pytest.raises(ValueError, match='Unknown top-level'):
        merge_pins(_base(), {'e3sm': {'branch': 'main'}})


def test_validate_requires_exactly_one_ref():
    pins = _base()
    pins['repos']['e3sm']['branch'] = 'main'
    with pytest.raises(ValueError, match='exactly one'):
        validate_pins(pins)

    pins = _base()
    del pins['repos']['e3sm']['tag']
    with pytest.raises(ValueError, match='exactly one'):
        validate_pins(pins)

    pins = _base()
    del pins['spack']['git']
    with pytest.raises(ValueError, match='missing "git"'):
        validate_pins(pins)


def test_load_pins_precedence(tmp_path: Path):
    override_file = tmp_path / 'pins.yaml'
    override_file.write_text(
        safe_dump({'repos': {'e3sm': {'commit': 'fromfile'}}})
    )
    pins = load_pins(
        [
            {'repos': {'e3sm': {'branch': 'fromconfig'}}},
            {'repos': {'builtin': {'branch': 'fromruntime'}}},
            str(override_file),
        ]
    )
    assert pins['repos']['e3sm'] == {
        'git': 'https://github.com/E3SM-Project/e3sm-spack-packages.git',
        'commit': 'fromfile',
    }
    assert pins['repos']['builtin']['branch'] == 'fromruntime'
    assert 'tag' not in pins['repos']['builtin']


def test_load_pins_single_override_forms(tmp_path: Path):
    override_file = tmp_path / 'pins.yaml'
    override_file.write_text(safe_dump({'spack': {'branch': 'develop'}}))
    assert load_pins(str(override_file))['spack']['branch'] == 'develop'
    assert load_pins({'spack': {'branch': 'develop'}})['spack'] == {
        'git': 'https://github.com/spack/spack.git',
        'branch': 'develop',
    }
    assert load_pins(None) == load_pins()


def test_render_repos_yaml_keeps_search_order():
    text = render_repos_yaml('/opt/spack', _base())
    data = safe_load(text)
    assert list(data['repos']) == ['e3sm', 'builtin']
    assert (
        data['repos']['e3sm']
        == '/opt/spack/var/spack/package_repos/e3sm/repos/spack_repo/e3sm'
    )
    assert (
        data['repos']['builtin']
        == '/opt/spack/var/spack/package_repos/builtin/repos/spack_repo/'
        'builtin'
    )
    # keys come out in pins order, not sorted
    assert text.index('e3sm:') < text.index('builtin:')


def test_checkout_ref_and_command():
    assert checkout_ref({'git': 'g', 'tag': 'v1'}) == 'refs/tags/v1'
    assert checkout_ref({'git': 'g', 'commit': 'abc'}) == 'abc'
    assert checkout_ref({'git': 'g', 'branch': 'main'}) == 'origin/main'

    commands = checkout_command(
        {'git': 'https://example.com/r.git', 'branch': 'main'}, '/opt/r'
    )
    assert 'git clone https://example.com/r.git /opt/r' in commands
    assert 'git -C /opt/r fetch --tags origin' in commands
    assert 'git -C /opt/r checkout --detach' in commands
    assert 'git -C /opt/r reset --hard origin/main' in commands


def test_release_guard():
    pins = _base()
    assert release_pins_are_valid(pins, '5.0.0')
    assert release_pins_are_valid(pins, '5.0.0rc1')

    commit_pins = merge_pins(pins, {'repos': {'e3sm': {'commit': 'abc'}}})
    assert not release_pins_are_valid(commit_pins, '5.0.0')
    assert release_pins_are_valid(commit_pins, '5.0.0rc1')

    fork_pins = merge_pins(
        pins,
        {'repos': {'e3sm': {'git': 'https://github.com/xylar/x.git'}}},
    )
    assert not release_pins_are_valid(fork_pins, '5.0.0')
    assert release_pins_are_valid(fork_pins, '5.0.0.dev1')
