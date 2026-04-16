#!/usr/bin/env python3

import argparse
import os
import tempfile

import mache.version
from mache.cime_machine_config.report import (
    build_update_report,
    render_update_issue,
    write_report_json,
)
from mache.io import download_file
from mache.machines import get_supported_machines


def main():
    """
    Main function to download the XML file, get supported machines, and extract
    them, then compare the machine configurations between the old and new XML.
    """
    parser = argparse.ArgumentParser(
        description='Compare supported machine config_machines entries '
        'against the latest upstream CIME source.',
    )

    parser.add_argument(
        '-v',
        '--version',
        action='version',
        version=mache.version.__version__,
        help='Show version number and exit',
    )
    parser.add_argument(
        '--upstream-url',
        default=(
            'https://raw.githubusercontent.com/E3SM-Project/E3SM/'
            'refs/heads/master/cime_config/machines/config_machines.xml'
        ),
        help='The upstream config_machines.xml URL to compare against.',
    )
    parser.add_argument(
        '--json-output',
        help='Optional JSON file to write the structured update report to.',
    )
    parser.add_argument(
        '--markdown-output',
        help='Optional Markdown file to write the issue body to.',
    )
    parser.add_argument(
        '--run-url',
        help='Optional workflow run URL to include in the rendered report.',
    )
    parser.add_argument(
        '--work-dir',
        help='Optional directory for temporary XML comparison files.',
    )

    args = parser.parse_args()

    report = build_report(
        upstream_url=args.upstream_url,
        work_dir=args.work_dir,
    )
    print_console_report(report)

    if args.json_output:
        write_report_json(report, args.json_output)

    if args.markdown_output:
        markdown = render_update_issue(report, run_url=args.run_url)
        with open(args.markdown_output, 'w', encoding='utf-8') as handle:
            handle.write(markdown)
            handle.write('\n')


def build_report(*, upstream_url, work_dir=None):
    """Download upstream config and return a structured drift report."""

    if work_dir is not None:
        return _build_report_in_dir(
            upstream_url=upstream_url,
            work_dir=work_dir,
        )

    with tempfile.TemporaryDirectory() as temp_dir:
        return _build_report_in_dir(
            upstream_url=upstream_url,
            work_dir=temp_dir,
        )


def print_console_report(report):
    """Print a concise human-readable summary to stdout."""

    if not report.has_updates:
        print('No supported machine updates detected.')
        return

    print('Supported machine updates detected:')
    for machine in report.machines:
        print(f'- {machine.machine}')
        if machine.package_groups:
            package_groups = ', '.join(machine.package_groups)
            print(f'  package groups: {package_groups}')
        if machine.prefix_vars:
            prefix_vars = ', '.join(machine.prefix_vars)
            print(f'  prefix/path vars: {prefix_vars}')
        if machine.spack_templates_to_review:
            templates = ', '.join(machine.spack_templates_to_review)
            print(f'  spack templates: {templates}')


def _build_report_in_dir(*, upstream_url, work_dir):
    machines = get_supported_machines()
    upstream_filename = os.path.join(work_dir, 'upstream_config_machines.xml')
    old_filename = 'mache/cime_machine_config/config_machines.xml'

    download_file(upstream_url, upstream_filename)
    return build_update_report(
        old_xml=old_filename,
        new_xml=upstream_filename,
        supported_machines=machines,
        upstream_url=upstream_url,
    )


if __name__ == '__main__':
    main()
