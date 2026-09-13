#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json

import requests

CLAUDE_LABEL = 'claude'
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
):
    """Create or update the automation issue and hand it to Claude."""

    payload = build_issue_payload(
        issue_title=issue_title,
        body=body,
        primary_assignee=primary_assignee,
    )

    if issue is None:
        created = _post_issue(
            session=session,
            owner=owner,
            repo=repo,
            payload=payload,
        )
        number = created['number']
        print(f'Created automation issue #{number} labeled {CLAUDE_LABEL}.')
        return

    updated = _patch_issue(
        session=session,
        owner=owner,
        repo=repo,
        issue_number=issue['number'],
        payload=payload,
    )
    number = updated['number']
    if CLAUDE_LABEL in {label['name'] for label in issue.get('labels', [])}:
        print(
            f'Updated automation issue #{number}; it already carries the '
            f'{CLAUDE_LABEL} label, so Claude was not triggered again.'
        )
    else:
        print(f'Updated automation issue #{number} labeled {CLAUDE_LABEL}.')


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


def build_issue_payload(*, issue_title, body, primary_assignee):
    """Build the REST payload for creating or updating the issue."""

    assignees = []
    if primary_assignee != '':
        assignees.append(primary_assignee)

    return {
        'title': issue_title,
        'body': body,
        'assignees': assignees,
        'labels': [CLAUDE_LABEL],
    }


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
