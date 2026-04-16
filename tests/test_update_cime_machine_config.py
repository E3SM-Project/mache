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

    def fake_get(url, *, params, headers, timeout):
        captured['url'] = url
        captured['params'] = params
        captured['headers'] = headers
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
    assert captured['headers'] == {
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'mache/update_cime_machine_config',
    }
    assert captured['timeout'] == 60


def test_get_latest_commit_sha_uses_github_token_when_available(monkeypatch):
    update_module = _load_update_module()
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [{'sha': 'abc123'}]

    def fake_get(url, *, params, headers, timeout):
        captured['headers'] = headers
        return FakeResponse()

    monkeypatch.setenv('GITHUB_TOKEN', 'secret-token')
    monkeypatch.setattr(update_module.requests, 'get', fake_get)

    sha = update_module._get_latest_commit_sha(
        owner='E3SM-Project',
        repo='E3SM',
        ref='master',
        path='cime_config/machines/config_machines.xml',
    )

    assert sha == 'abc123'
    assert captured['headers'] == {
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'mache/update_cime_machine_config',
        'Authorization': 'Bearer secret-token',
    }


def test_build_report_uses_manual_upstream_revision(monkeypatch):
    update_module = _load_update_module()

    monkeypatch.setattr(
        update_module,
        '_build_report_in_dir',
        lambda **kwargs: kwargs['upstream_revision'],
    )

    report = update_module.build_report(
        upstream_url='https://example.com/config_machines.xml',
        upstream_revision='deadbeef1234',
        work_dir='.',
    )

    assert report == 'deadbeef1234'


def test_resolve_upstream_revision_ignores_github_api_errors(monkeypatch):
    update_module = _load_update_module()

    class FakeResponse:
        status_code = 403

    def fake_get_latest_commit_sha(**kwargs):
        raise update_module.requests.HTTPError(response=FakeResponse())

    monkeypatch.setattr(
        update_module,
        '_get_latest_commit_sha',
        fake_get_latest_commit_sha,
    )

    revision = update_module._resolve_upstream_revision(
        'https://raw.githubusercontent.com/E3SM-Project/E3SM/'
        'refs/heads/master/cime_config/machines/config_machines.xml'
    )

    assert revision is None
