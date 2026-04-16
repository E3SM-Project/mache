#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json

import requests

COPILOT_LOGIN = 'copilot-swe-agent[bot]'
DEFAULT_API_VERSION = '2022-11-28'


def main():
    """Create, update, or close the automation issue for config drift."""

    parser = argparse.ArgumentParser(
        description='Synchronize the config_machines automation issue.',
    )
    parser.add_argument('--report-json', required=True)
    parser.add_argument('--report-markdown', required=True)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--token', required=True)
    parser.add_argument('--issue-title', required=True)
    parser.add_argument('--base-branch', required=True)
    parser.add_argument('--primary-assignee', default='')
    args = parser.parse_args()

    with open(args.report_json, encoding='utf-8') as handle:
        report = json.load(handle)

    with open(args.report_markdown, encoding='utf-8') as handle:
        body = handle.read()

    session = _make_session(args.token)
    owner, repo = _split_repository(args.repository)
    issue = _find_existing_issue(
        session=session,
        owner=owner,
        repo=repo,
        issue_title=args.issue_title,
    )

    if report['has_updates']:
        create_or_update_issue(
            session=session,
            owner=owner,
            repo=repo,
            issue=issue,
            issue_title=args.issue_title,
            body=body,
            primary_assignee=args.primary_assignee,
            base_branch=args.base_branch,
        )
        return

    if issue is not None:
        close_issue(
            session=session,
            owner=owner,
            repo=repo,
            issue_number=issue['number'],
        )
        print(f'Closed issue #{issue["number"]} because no updates remain.')
        return

    print('No updates detected and no open automation issue found.')


def create_or_update_issue(
    *,
    session,
    owner,
    repo,
    issue,
    issue_title,
    body,
    primary_assignee,
    base_branch,
):
    """Create or update the automation issue, with Copilot fallback."""

    payload = build_issue_payload(
        issue_title=issue_title,
        body=body,
        primary_assignee=primary_assignee,
        owner=owner,
        repo=repo,
        base_branch=base_branch,
        assign_copilot=True,
    )

    try:
        if issue is None:
            created = _post_issue(
                session=session,
                owner=owner,
                repo=repo,
                payload=payload,
            )
            print(
                'Created automation issue '
                f'#{created["number"]} with Copilot assignment.'
            )
        else:
            updated = _patch_issue(
                session=session,
                owner=owner,
                repo=repo,
                issue_number=issue['number'],
                payload=payload,
            )
            print(
                'Updated automation issue '
                f'#{updated["number"]} with Copilot assignment.'
            )
        return
    except requests.HTTPError as error:
        warning = (
            'Automation note: Copilot assignment failed. Check that Copilot '
            'cloud agent is enabled for this repository and that the token '
            'used by this workflow is a user token with write access to '
            'actions, contents, issues, and pull requests.\n\n'
        )
        fallback_payload = build_issue_payload(
            issue_title=issue_title,
            body=warning + body,
            primary_assignee=primary_assignee,
            owner=owner,
            repo=repo,
            base_branch=base_branch,
            assign_copilot=False,
        )
        if issue is None:
            created = _post_issue(
                session=session,
                owner=owner,
                repo=repo,
                payload=fallback_payload,
            )
            print(
                'Created automation issue '
                f'#{created["number"]} without Copilot assignment: {error}'
            )
        else:
            updated = _patch_issue(
                session=session,
                owner=owner,
                repo=repo,
                issue_number=issue['number'],
                payload=fallback_payload,
            )
            print(
                'Updated automation issue '
                f'#{updated["number"]} without Copilot assignment: {error}'
            )


def close_issue(*, session, owner, repo, issue_number):
    """Close the automation issue once drift has been resolved."""

    payload = {'state': 'closed', 'state_reason': 'completed'}
    _patch_issue(
        session=session,
        owner=owner,
        repo=repo,
        issue_number=issue_number,
        payload=payload,
    )


def build_issue_payload(
    *,
    issue_title,
    body,
    primary_assignee,
    owner,
    repo,
    base_branch,
    assign_copilot,
):
    """Build the REST payload for creating or updating the issue."""

    assignees = []
    if primary_assignee != '':
        assignees.append(primary_assignee)
    if assign_copilot:
        assignees.append(COPILOT_LOGIN)

    payload = {
        'title': issue_title,
        'body': body,
        'assignees': assignees,
    }
    if assign_copilot:
        payload['agent_assignment'] = {
            'target_repo': f'{owner}/{repo}',
            'base_branch': base_branch,
            'custom_instructions': (
                'Use the issue body as the task definition. Run `pixi run '
                '-e py314 python utils/update_cime_machine_config.py '
                '--work-dir .`, replace '
                'mache/cime_machine_config/config_machines.xml with '
                'upstream_config_machines.xml, remove '
                'upstream_config_machines.xml before committing, and state '
                'the upstream E3SM commit hash in the PR summary. Then '
                'update the related Spack templates and version strings in '
                'mache/spack/templates/<machine>*.yaml, '
                'mache/spack/templates/<machine>*.sh, and '
                'mache/spack/templates/<machine>*.csh. '
                'Add TODO comments in the PR when prefix or path changes '
                'need reviewer confirmation.'
            ),
            'custom_agent': '',
            'model': '',
        }

    return payload


def _make_session(token):
    session = requests.Session()
    session.headers.update(
        {
            'Accept': 'application/vnd.github+json',
            'Authorization': f'Bearer {token}',
            'X-GitHub-Api-Version': DEFAULT_API_VERSION,
        }
    )
    return session


def _find_existing_issue(*, session, owner, repo, issue_title):
    issues = _request_json(
        session=session,
        method='GET',
        url=f'https://api.github.com/repos/{owner}/{repo}/issues',
        params={'state': 'open', 'per_page': 100},
    )
    for issue in issues:
        if 'pull_request' in issue:
            continue
        if issue.get('title') == issue_title:
            return issue
    return None


def _post_issue(*, session, owner, repo, payload):
    return _request_json(
        session=session,
        method='POST',
        url=f'https://api.github.com/repos/{owner}/{repo}/issues',
        json_payload=payload,
    )


def _patch_issue(*, session, owner, repo, issue_number, payload):
    return _request_json(
        session=session,
        method='PATCH',
        url=f'https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}',
        json_payload=payload,
    )


def _request_json(*, session, method, url, params=None, json_payload=None):
    response = session.request(
        method,
        url,
        params=params,
        json=json_payload,
        timeout=60,
    )
    response.raise_for_status()
    if response.status_code == 204 or response.text == '':
        return None
    return response.json()


def _split_repository(repository):
    owner, repo = repository.split('/', maxsplit=1)
    return owner, repo


if __name__ == '__main__':
    main()
