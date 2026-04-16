from __future__ import annotations

import difflib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from lxml import etree

from mache.spack.list import list_machine_compiler_mpilib
from mache.spack.shared import (
    PATH_LIKE_ENV_VARS,
    classify_env_var_package_group,
    classify_module_command_package_group,
)

ISSUE_MARKER = '<!-- cime-machine-config-update-report -->'
PREFIX_ENV_SUFFIXES = ('_DIR', '_HOME', '_PATH', '_PREFIX', '_ROOT')


@dataclass
class BlockChange:
    selectors: dict[str, str]
    added: list[str]
    removed: list[str]


@dataclass
class MachineUpdate:
    machine: str
    diff_lines: list[str]
    module_changes: list[BlockChange]
    env_var_changes: list[BlockChange]
    package_groups: list[str]
    prefix_vars: list[str]
    spack_templates_to_review: list[str]

    @property
    def has_updates(self) -> bool:
        return bool(
            self.diff_lines
            or self.module_changes
            or self.env_var_changes
            or self.package_groups
            or self.prefix_vars
            or self.spack_templates_to_review
        )


@dataclass
class UpdateReport:
    generated_at: str
    upstream_url: str
    supported_machines: list[str]
    machines: list[MachineUpdate]

    @property
    def has_updates(self) -> bool:
        return any(machine.has_updates for machine in self.machines)

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data['has_updates'] = self.has_updates
        return data


def build_update_report(old_xml, new_xml, supported_machines, upstream_url):
    """Build a structured report for supported machine config changes."""

    old_root = etree.parse(old_xml).getroot()
    new_root = etree.parse(new_xml).getroot()
    template_map = _get_machine_template_map()

    machines: list[MachineUpdate] = []
    for machine in supported_machines:
        old_machine = old_root.find(f".//machine[@MACH='{machine}']")
        new_machine = new_root.find(f".//machine[@MACH='{machine}']")
        update = _build_machine_update(
            machine=machine,
            old_machine=old_machine,
            new_machine=new_machine,
            template_map=template_map,
        )
        if update.has_updates:
            machines.append(update)

    return UpdateReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        upstream_url=upstream_url,
        supported_machines=list(supported_machines),
        machines=machines,
    )


def render_update_issue(report, run_url=None):
    """Render the report as a GitHub issue body for Copilot work."""

    if not report.has_updates:
        lines = [
            ISSUE_MARKER,
            '',
            'No supported machine updates were detected in the latest check.',
        ]
        return '\n'.join(lines)

    lines = [
        ISSUE_MARKER,
        '',
        'The daily config_machines check found upstream changes for one or',
        'more supported machines.',
        '',
        f'- Generated: {report.generated_at}',
        f'- Upstream source: {report.upstream_url}',
    ]

    if run_url:
        lines.append(f'- Workflow run: {run_url}')

    lines.extend(
        [
            '',
            'Required work:',
            '',
            '- Update mache/cime_machine_config/config_machines.xml for the',
            '  affected supported machines.',
            '- If module or environment changes imply different',
            '  system-package',
            '  versions, update the corresponding mache Spack templates and',
            '  version strings for the affected toolchains.',
            '- If the only follow-up is module or version drift, keep the PR',
            '  focused on those updates.',
            '- If any prefix or path values changed and the correct',
            '  replacement',
            '  is not obvious, add a TODO comment in the PR for the reviewer',
            '  instead of guessing.',
            '',
            'Affected machines: '
            f'{", ".join(update.machine for update in report.machines)}',
        ]
    )

    for machine in report.machines:
        lines.extend(_render_machine_section(machine))

    return '\n'.join(lines)


def write_report_json(report, filename):
    """Write the report to a JSON file."""

    with open(filename, 'w', encoding='utf-8') as handle:
        json.dump(report.to_dict(), handle, indent=2)
        handle.write('\n')


def _build_machine_update(machine, old_machine, new_machine, template_map):
    diff_lines = _get_machine_diff(
        old_machine=old_machine,
        new_machine=new_machine,
    )
    module_changes = _compare_block_maps(
        old_blocks=_collect_module_blocks(old_machine),
        new_blocks=_collect_module_blocks(new_machine),
    )
    env_var_changes = _compare_block_maps(
        old_blocks=_collect_env_var_blocks(old_machine),
        new_blocks=_collect_env_var_blocks(new_machine),
    )

    package_groups = _get_package_groups(
        module_changes=module_changes,
        env_var_changes=env_var_changes,
    )
    prefix_vars = _get_prefix_vars(env_var_changes)

    spack_templates = []
    if package_groups or prefix_vars:
        spack_templates = template_map.get(machine, [])

    return MachineUpdate(
        machine=machine,
        diff_lines=diff_lines,
        module_changes=module_changes,
        env_var_changes=env_var_changes,
        package_groups=package_groups,
        prefix_vars=prefix_vars,
        spack_templates_to_review=spack_templates,
    )


def _collect_module_blocks(machine):
    blocks: dict[tuple[tuple[str, str], ...], set[str]] = {}
    if machine is None:
        return blocks

    for module_system in machine.findall('module_system'):
        for modules in module_system.findall('modules'):
            key = _selector_key(modules)
            values = blocks.setdefault(key, set())
            for command in modules.findall('command'):
                name = command.get('name', '').strip()
                value = (command.text or '').strip()
                entry = name if value == '' else f'{name} {value}'
                values.add(entry)

    return blocks


def _collect_env_var_blocks(machine):
    blocks: dict[tuple[tuple[str, str], ...], set[str]] = {}
    if machine is None:
        return blocks

    for env_vars in machine.findall('environment_variables'):
        key = _selector_key(env_vars)
        values = blocks.setdefault(key, set())
        for env_var in env_vars.findall('env'):
            name = env_var.get('name', '').strip()
            value = (env_var.text or '').strip()
            values.add(f'{name}={value}')

    return blocks


def _compare_block_maps(old_blocks, new_blocks):
    changes: list[BlockChange] = []
    keys = sorted(set(old_blocks) | set(new_blocks))
    for key in keys:
        old_values = old_blocks.get(key, set())
        new_values = new_blocks.get(key, set())
        added = sorted(new_values - old_values)
        removed = sorted(old_values - new_values)
        if added or removed:
            changes.append(
                BlockChange(
                    selectors=dict(key),
                    added=added,
                    removed=removed,
                )
            )

    return changes


def _get_machine_diff(old_machine, new_machine):
    old_text = _machine_to_text(old_machine)
    new_text = _machine_to_text(new_machine)
    return list(
        difflib.unified_diff(
            old_text.splitlines(),
            new_text.splitlines(),
            fromfile='old',
            tofile='new',
            lineterm='',
        )
    )


def _machine_to_text(machine):
    if machine is None:
        return ''

    return etree.tostring(machine, pretty_print=True).decode('utf-8')


def _get_package_groups(*, module_changes, env_var_changes):
    groups: set[str] = set()

    for change in module_changes:
        for entry in change.added + change.removed:
            _name, _sep, value = entry.partition(' ')
            if value == '':
                continue
            group = classify_module_command_package_group(value)
            if group is not None:
                groups.add(group)

    for change in env_var_changes:
        for entry in change.added + change.removed:
            name, _sep, value = entry.partition('=')
            group = classify_env_var_package_group(name, value)
            if group is not None:
                groups.add(group)

    return sorted(groups)


def _get_prefix_vars(env_var_changes):
    prefix_vars: set[str] = set()

    for change in env_var_changes:
        for entry in change.added + change.removed:
            name, _sep, value = entry.partition('=')
            if _is_prefix_var(name=name, value=value):
                prefix_vars.add(name)

    return sorted(prefix_vars)


def _is_prefix_var(*, name, value):
    if name in PATH_LIKE_ENV_VARS:
        return True

    if name.endswith(PREFIX_ENV_SUFFIXES):
        return True

    return '/' in value or '${' in value or '$ENV{' in value


def _selector_key(element):
    return tuple(sorted((key, value) for key, value in element.attrib.items()))


def _get_machine_template_map():
    template_map: dict[str, list[str]] = {}
    for machine, compiler, mpilib in list_machine_compiler_mpilib():
        filename = f'{machine}_{compiler}_{mpilib}.yaml'
        template_map.setdefault(machine, []).append(filename)

    for _machine, filenames in template_map.items():
        filenames.sort()

    return template_map


def _render_machine_section(machine):
    lines = [
        '',
        f'## {machine.machine}',
        '',
    ]

    if machine.package_groups:
        lines.append(
            f'- Package groups to review: {", ".join(machine.package_groups)}'
        )
    else:
        lines.append('- Package groups to review: none detected')

    if machine.prefix_vars:
        lines.append(
            '- Prefix/path variables changed: '
            f'{", ".join(machine.prefix_vars)}'
        )
    else:
        lines.append('- Prefix/path variables changed: none detected')

    if machine.spack_templates_to_review:
        lines.append(
            '- Spack templates to review: '
            f'{", ".join(machine.spack_templates_to_review)}'
        )
    else:
        lines.append('- Spack templates to review: none matched')

    if machine.module_changes:
        lines.extend(
            _render_change_details(
                'Module changes',
                machine.module_changes,
            )
        )

    if machine.env_var_changes:
        lines.extend(
            _render_change_details(
                'Environment variable changes',
                machine.env_var_changes,
            )
        )

    if machine.diff_lines:
        lines.extend(
            [
                '',
                '<details>',
                '<summary>XML diff</summary>',
                '',
                '```diff',
                *machine.diff_lines,
                '```',
                '</details>',
            ]
        )

    return lines


def _render_change_details(title, changes):
    lines = [
        '',
        '<details>',
        f'<summary>{title}</summary>',
        '',
    ]

    for change in changes:
        selector_text = _format_selectors(change.selectors)
        lines.append(f'- Selector: {selector_text}')
        for entry in change.added:
            lines.append(f'  - Added: {entry}')
        for entry in change.removed:
            lines.append(f'  - Removed: {entry}')

    lines.append('</details>')
    return lines


def _format_selectors(selectors):
    if len(selectors) == 0:
        return 'all matching toolchains'

    return ', '.join(f'{key}={value}' for key, value in selectors.items())
