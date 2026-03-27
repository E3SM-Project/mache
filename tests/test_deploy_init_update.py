from pathlib import Path

from mache.deploy.init_update import init_or_update_repo


def test_init_creates_custom_cli_spec_file(tmp_path: Path):
    init_or_update_repo(
        repo_root=str(tmp_path),
        software='polaris',
        mache_version='1.2.3',
        update=False,
        overwrite=False,
    )

    custom_cli_spec = tmp_path / 'deploy' / 'custom_cli_spec.json'
    assert custom_cli_spec.read_text(encoding='utf-8') == (
        '{\n  "arguments": []\n}\n'
    )


def test_update_preserves_custom_cli_spec_file(tmp_path: Path):
    init_or_update_repo(
        repo_root=str(tmp_path),
        software='polaris',
        mache_version='1.2.3',
        update=False,
        overwrite=False,
    )

    custom_cli_spec = tmp_path / 'deploy' / 'custom_cli_spec.json'
    expected = (
        '{\n'
        '  "arguments": [\n'
        '    {\n'
        '      "flags": ["--with-albany"],\n'
        '      "dest": "with_albany",\n'
        '      "action": "store_true",\n'
        '      "help": "Install optional Albany support.",\n'
        '      "route": ["deploy", "run"]\n'
        '    }\n'
        '  ]\n'
        '}\n'
    )
    custom_cli_spec.write_text(expected, encoding='utf-8')

    init_or_update_repo(
        repo_root=str(tmp_path),
        software='polaris',
        mache_version='1.2.4',
        update=True,
        overwrite=True,
    )

    assert custom_cli_spec.read_text(encoding='utf-8') == expected


def test_generated_deploy_py_runs_mache_without_nested_login_shell(
    tmp_path: Path,
):
    init_or_update_repo(
        repo_root=str(tmp_path),
        software='polaris',
        mache_version='1.2.3',
        update=False,
        overwrite=False,
    )

    deploy_py = (tmp_path / 'deploy.py').read_text(encoding='utf-8')

    assert 'bash -lc' not in deploy_py
    assert 'subprocess.run(cmd, cwd=repo_root, env=env, check=True)' in (
        deploy_py
    )
    assert "'mache'," in deploy_py
    assert "'deploy'," in deploy_py
    assert "'run'," in deploy_py
