from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_update_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / 'utils'
        / 'update_cime_machine_config.py'
    )
    spec = spec_from_file_location('update_cime_machine_config', module_path)
    assert spec is not None
    assert spec.loader is not None

    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_github_raw_url_supports_default_e3sm_url():
    update_module = _load_update_module()

    source = update_module._parse_github_raw_url(
        'https://raw.githubusercontent.com/E3SM-Project/E3SM/'
        'refs/heads/master/cime_config/machines/config_machines.xml'
    )

    assert source == (
        'E3SM-Project',
        'E3SM',
        'master',
        'cime_config/machines/config_machines.xml',
    )


def test_get_latest_commit_sha_uses_github_commits_api(monkeypatch):
    update_module = _load_update_module()
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [{'sha': 'abc123'}]

    def fake_get(url, *, params, timeout):
        captured['url'] = url
        captured['params'] = params
        captured['timeout'] = timeout
        return FakeResponse()

    monkeypatch.setattr(update_module.requests, 'get', fake_get)

    sha = update_module._get_latest_commit_sha(
        owner='E3SM-Project',
        repo='E3SM',
        ref='master',
        path='cime_config/machines/config_machines.xml',
    )

    assert sha == 'abc123'
    assert captured['url'].endswith('/repos/E3SM-Project/E3SM/commits')
    assert captured['params'] == {
        'sha': 'master',
        'path': 'cime_config/machines/config_machines.xml',
        'per_page': 1,
    }
    assert captured['timeout'] == 60
