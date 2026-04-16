from mache.cime_machine_config.report import (
    build_update_report,
    render_update_issue,
)


def test_build_update_report_detects_spack_related_drift(
    monkeypatch, tmp_path
):
    old_xml = tmp_path / 'old.xml'
    new_xml = tmp_path / 'new.xml'
    old_xml.write_text(
        '<config_machines>\n'
        '  <machine MACH="test-machine">\n'
        '    <module_system type="module">\n'
        '      <modules compiler="gnu" mpilib="mpich">\n'
        '        <command name="load">netcdf/4.9.2</command>\n'
        '      </modules>\n'
        '    </module_system>\n'
        '    <environment_variables compiler="gnu" mpilib="mpich">\n'
        '      <env name="NETCDF_PATH">/old/netcdf</env>\n'
        '    </environment_variables>\n'
        '  </machine>\n'
        '</config_machines>\n',
        encoding='utf-8',
    )
    new_xml.write_text(
        '<config_machines>\n'
        '  <machine MACH="test-machine">\n'
        '    <module_system type="module">\n'
        '      <modules compiler="gnu" mpilib="mpich">\n'
        '        <command name="load">netcdf/4.9.3</command>\n'
        '      </modules>\n'
        '    </module_system>\n'
        '    <environment_variables compiler="gnu" mpilib="mpich">\n'
        '      <env name="NETCDF_PATH">/new/netcdf</env>\n'
        '    </environment_variables>\n'
        '  </machine>\n'
        '</config_machines>\n',
        encoding='utf-8',
    )

    monkeypatch.setattr(
        'mache.cime_machine_config.report.list_machine_compiler_mpilib',
        lambda: [('test-machine', 'gnu', 'mpich')],
    )

    report = build_update_report(
        old_xml=old_xml,
        new_xml=new_xml,
        supported_machines=['test-machine'],
        upstream_url='https://example.invalid/config_machines.xml',
    )

    assert report.has_updates is True
    assert len(report.machines) == 1

    machine = report.machines[0]
    assert machine.machine == 'test-machine'
    assert machine.package_groups == ['netcdf']
    assert machine.prefix_vars == ['NETCDF_PATH']
    assert machine.spack_templates_to_review == ['test-machine_gnu_mpich.yaml']
    assert machine.module_changes[0].selectors == {
        'compiler': 'gnu',
        'mpilib': 'mpich',
    }
    assert machine.module_changes[0].added == ['load netcdf/4.9.3']
    assert machine.module_changes[0].removed == ['load netcdf/4.9.2']


def test_render_update_issue_includes_required_instructions(
    monkeypatch, tmp_path
):
    old_xml = tmp_path / 'old.xml'
    new_xml = tmp_path / 'new.xml'
    xml_text = (
        '<config_machines>\n'
        '  <machine MACH="test-machine">\n'
        '    <module_system type="module">\n'
        '      <modules>\n'
        '        <command name="load">cmake/3.20.0</command>\n'
        '      </modules>\n'
        '    </module_system>\n'
        '  </machine>\n'
        '</config_machines>\n'
    )
    old_xml.write_text(xml_text, encoding='utf-8')
    new_xml.write_text(xml_text.replace('3.20.0', '3.30.0'), encoding='utf-8')

    monkeypatch.setattr(
        'mache.cime_machine_config.report.list_machine_compiler_mpilib',
        lambda: [('test-machine', 'gnu', 'mpich')],
    )

    report = build_update_report(
        old_xml=old_xml,
        new_xml=new_xml,
        supported_machines=['test-machine'],
        upstream_url='https://example.invalid/config_machines.xml',
    )
    markdown = render_update_issue(
        report,
        run_url='https://github.example/actions/runs/1',
    )

    assert 'Update mache/cime_machine_config/config_machines.xml' in markdown
    assert 'TODO comment in the PR for the reviewer' in markdown
    assert 'test-machine_gnu_mpich.yaml' in markdown
    assert 'https://github.example/actions/runs/1' in markdown
