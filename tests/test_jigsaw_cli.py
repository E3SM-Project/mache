import argparse

from mache.jigsaw.cli import _dispatch_jigsaw, add_jigsaw_subparser


def test_dispatch_jigsaw_install_calls_deploy(monkeypatch):
    """Verify ``mache jigsaw install`` dispatches to ``deploy_jigsawpy``."""
    called = {}

    def _fake_deploy_jigsawpy(**kwargs):
        called.update(kwargs)

    monkeypatch.setattr(
        'mache.jigsaw.cli.deploy_jigsawpy',
        _fake_deploy_jigsawpy,
    )

    args = argparse.Namespace(
        jigsaw_cmd='install',
        jigsaw_python_path='jigsaw-python',
        repo_root='.',
        quiet=True,
        pixi_feature=None,
        pixi_manifest=None,
        pixi_local=False,
    )

    _dispatch_jigsaw(args)

    assert called['jigsaw_python_path'] == 'jigsaw-python'
    assert called['repo_root'] == '.'
    assert called['log_filename'] is None
    assert called['quiet'] is True
    assert called['pixi_local'] is False


def test_add_jigsaw_subparser_parses_install_args():
    """Verify parser wiring for ``mache jigsaw install`` arguments."""
    parser = argparse.ArgumentParser(prog='mache')
    subparsers = parser.add_subparsers(dest='command', required=True)
    add_jigsaw_subparser(subparsers)

    args = parser.parse_args(
        [
            'jigsaw',
            'install',
        ]
    )

    assert args.command == 'jigsaw'
    assert args.jigsaw_cmd == 'install'
    assert args.jigsaw_python_path == 'jigsaw-python'
    assert args.pixi_local is False


def test_add_jigsaw_subparser_allows_conda_without_pixi():
    """Verify parser accepts minimal args and uses defaults."""
    parser = argparse.ArgumentParser(prog='mache')
    subparsers = parser.add_subparsers(dest='command', required=True)
    add_jigsaw_subparser(subparsers)

    args = parser.parse_args(
        [
            'jigsaw',
            'install',
        ]
    )

    assert args.command == 'jigsaw'
    assert args.jigsaw_cmd == 'install'
    assert args.jigsaw_python_path == 'jigsaw-python'
    assert args.pixi_local is False
