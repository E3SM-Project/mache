from pathlib import Path

import pytest
from yaml import safe_load

from mache.spack.list import list_machine_compiler_mpilib
from mache.spack.shared import (
    E3SM_HDF5_NETCDF_PACKAGES,
    _get_yaml_data,
    validate_spack_env_yaml,
)

COMPILER_PACKAGES = {'gcc', 'nvhpc', 'cce', 'intel-oneapi-compilers'}


def _render(machine, compiler, mpi, **kwargs):
    args = dict(
        include_e3sm_lapack=False,
        e3sm_hdf5_netcdf=True,
        specs=['zlib-ng', 'cmake@3.27:'],
        yaml_template=None,
        exclude_packages=None,
    )
    args.update(kwargs)
    return _get_yaml_data(machine, compiler, mpi, **args)


def test_intel_classic_templates_are_retired():
    combos = set(list_machine_compiler_mpilib())
    assert ('compy', 'intel', 'impi') not in combos
    assert ('chrysalis', 'intel-classic', 'openmpi') not in combos
    assert ('chrysalis', 'intel-classic', 'impi') not in combos
    assert ('chrysalis', 'gnu', 'openmpi') in combos


@pytest.mark.parametrize(
    'machine, compiler, mpi', list_machine_compiler_mpilib()
)
@pytest.mark.parametrize('e3sm_lapack', [False, True])
def test_template_uses_spack_1x_compiler_model(
    machine, compiler, mpi, e3sm_lapack
):
    text = _render(machine, compiler, mpi, include_e3sm_lapack=e3sm_lapack)
    data = safe_load(text)['spack']

    assert 'compilers' not in data
    assert 'compiler' not in data['packages']['all']

    toolchain = data['toolchains']['mache']
    assert [entry['when'] for entry in toolchain] == ['%c', '%cxx', '%fortran']
    compiler_spec = toolchain[0]['spec'].split('=', 1)[1]
    assert all(
        entry['spec'].endswith(f'={compiler_spec}') for entry in toolchain
    )
    assert data['packages']['all']['require'] == ['%mache']

    for spec in data['specs']:
        assert '%' not in spec, spec
        assert spec.split('@')[0] not in COMPILER_PACKAGES, spec
    assert 'zlib-ng' in data['specs']
    assert 'cmake@3.27:' in data['specs']

    for name, package in data['packages'].items():
        for external in package.get('externals', []):
            assert '%' not in external['spec'], (name, external['spec'])

    compiler_name = compiler_spec.split('@')[0]
    assert compiler_name in COMPILER_PACKAGES
    externals = data['packages'][compiler_name]['externals']
    external = next(e for e in externals if e['spec'] == compiler_spec)
    assert set(external['extra_attributes']['compilers']) == {
        'c',
        'cxx',
        'fortran',
    }
    assert 'prefix' in external or external.get('modules')


@pytest.mark.parametrize(
    'machine, compiler, mpi', list_machine_compiler_mpilib()
)
def test_template_exclude_hdf5_netcdf(machine, compiler, mpi):
    text = _render(
        machine,
        compiler,
        mpi,
        e3sm_hdf5_netcdf=False,
        exclude_packages=['hdf5_netcdf'],
    )
    data = safe_load(text)['spack']
    for package in E3SM_HDF5_NETCDF_PACKAGES:
        assert package not in data['packages']
        assert package not in data['specs']


def test_validate_rejects_legacy_compiler_model(tmp_path: Path):
    legacy = tmp_path / 'katara_gnu_openmpi.yaml'
    legacy.write_text(
        'spack:\n'
        '  specs: [zlib-ng]\n'
        '  packages:\n'
        '    all:\n'
        '      compiler: [gcc@13.3.0]\n'
        '  compilers:\n'
        '  - compiler:\n'
        '      spec: gcc@13.3.0\n'
    )
    with pytest.raises(ValueError, match='katara_gnu_openmpi.yaml'):
        _render('katara', 'gnu', 'openmpi', yaml_template=str(legacy))

    with pytest.raises(ValueError, match='packages:all:compiler'):
        validate_spack_env_yaml(
            'spack:\n  packages:\n    all:\n      compiler: [gcc]\n', 'x'
        )
    validate_spack_env_yaml('spack:\n  specs: [zlib-ng]\n', 'x')
