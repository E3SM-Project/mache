import textwrap

from mache.discover import discover_machine


def test_discover_machine_builtin_rules(monkeypatch):
    monkeypatch.setattr('socket.gethostname', lambda: 'andes001')
    assert discover_machine(quiet=True) == 'andes'


def test_discover_machine_path_overrides_package(monkeypatch, tmp_path):
    # Both package and path match, path wins.
    pkg_dir = tmp_path / 'extmachines'
    pkg_dir.mkdir()
    (pkg_dir / '__init__.py').write_text('')
    (pkg_dir / 'pkgmach.cfg').write_text(
        textwrap.dedent(
            """
            [discovery]
            hostname_re = ^testhost$
            """
        ).lstrip()
    )

    machines_dir = tmp_path / 'machines'
    machines_dir.mkdir()
    (machines_dir / 'pathmach.cfg').write_text(
        textwrap.dedent(
            """
            [discovery]
            hostname_re = ^testhost$
            """
        ).lstrip()
    )

    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr('socket.gethostname', lambda: 'testhost')

    assert (
        discover_machine(
            quiet=True,
            package='extmachines',
            path=str(machines_dir),
        )
        == 'pathmach'
    )


def test_discover_machine_package_rules(monkeypatch, tmp_path):
    pkg_dir = tmp_path / 'extmachines2'
    pkg_dir.mkdir()
    (pkg_dir / '__init__.py').write_text('')
    (pkg_dir / 'mymachine.cfg').write_text(
        textwrap.dedent(
            """
            [discovery]
            hostname_re = ^pkg-host\\d+$
            """
        ).lstrip()
    )

    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr('socket.gethostname', lambda: 'pkg-host123')

    assert discover_machine(quiet=True, package='extmachines2') == 'mymachine'
