from pathlib import Path

from mache.spack.config_machines import (
    config_to_shell_script,
    extract_machine_config,
)


def test_extract_machine_config_requires_full_compiler_match(tmp_path: Path):
    xml_file = tmp_path / 'config_machines.xml'
    xml_file.write_text(
        '<config_machines>\n'
        '  <machine MACH="test-machine">\n'
        '    <module_system type="module">\n'
        '      <modules compiler="oneapi-ifx">\n'
        '        <command name="load">cpu-module</command>\n'
        '      </modules>\n'
        '      <modules compiler="oneapi-ifxgpu">\n'
        '        <command name="load">gpu-module</command>\n'
        '      </modules>\n'
        '    </module_system>\n'
        '    <environment_variables compiler="oneapi-ifx">\n'
        '      <env name="CPU_ONLY">1</env>\n'
        '    </environment_variables>\n'
        '    <environment_variables compiler="oneapi-ifxgpu">\n'
        '      <env name="GPU_ONLY">1</env>\n'
        '    </environment_variables>\n'
        '  </machine>\n'
        '</config_machines>\n',
        encoding='utf-8',
    )

    gpu_config = extract_machine_config(
        xml_file=xml_file,
        machine='test-machine',
        compiler='oneapi-ifxgpu',
        mpilib='mpich',
    )
    gpu_script = config_to_shell_script(gpu_config, 'sh')

    assert 'gpu-module' in gpu_script
    assert 'cpu-module' not in gpu_script
    assert "{{ render_env_var('GPU_ONLY', '1', 'sh') }}" in gpu_script
    assert "{{ render_env_var('CPU_ONLY', '1', 'sh') }}" not in gpu_script

    cpu_config = extract_machine_config(
        xml_file=xml_file,
        machine='test-machine',
        compiler='oneapi-ifx',
        mpilib='mpich',
    )
    cpu_script = config_to_shell_script(cpu_config, 'sh')

    assert 'cpu-module' in cpu_script
    assert 'gpu-module' not in cpu_script
    assert "{{ render_env_var('CPU_ONLY', '1', 'sh') }}" in cpu_script
    assert "{{ render_env_var('GPU_ONLY', '1', 'sh') }}" not in cpu_script
