from pathlib import Path

import pytest

from mache.deploy.cli_spec import filter_args_by_route, load_repo_cli_spec_file


def test_load_repo_cli_spec_file_merges_custom_flags(tmp_path: Path):
    deploy_dir = tmp_path / 'deploy'
    deploy_dir.mkdir()
    (deploy_dir / 'custom_cli_spec.json').write_text(
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
        '}\n',
        encoding='utf-8',
    )

    spec = load_repo_cli_spec_file(str(tmp_path))
    run_args = filter_args_by_route(spec, 'run')

    assert any(arg.dest == 'with_albany' for arg in run_args)


def test_load_repo_cli_spec_file_rejects_duplicate_custom_flags(
    tmp_path: Path,
):
    deploy_dir = tmp_path / 'deploy'
    deploy_dir.mkdir()
    (deploy_dir / 'custom_cli_spec.json').write_text(
        '{\n'
        '  "arguments": [\n'
        '    {\n'
        '      "flags": ["--machine"],\n'
        '      "dest": "with_albany",\n'
        '      "route": ["deploy", "run"]\n'
        '    }\n'
        '  ]\n'
        '}\n',
        encoding='utf-8',
    )

    with pytest.raises(
        ValueError, match='custom_cli_spec flags duplicate generated cli_spec'
    ):
        load_repo_cli_spec_file(str(tmp_path))
