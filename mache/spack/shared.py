from importlib import resources as importlib_resources

import yaml
from jinja2 import Template


def _get_yaml_data(
    machine,
    compiler,
    mpi,
    include_e3sm_lapack,
    include_e3sm_hdf5_netcdf,
    specs,
    yaml_template,
):
    """Get the data from the jinja-templated yaml file based on settings"""
    if yaml_template is None:
        template_filename = f'{machine}_{compiler}_{mpi}.yaml'
        path = (
            importlib_resources.files('mache.spack.templates')
            / template_filename
        )
        try:
            with open(str(path)) as fp:
                template = Template(fp.read())
        except FileNotFoundError as err:
            raise ValueError(
                f'Spack template not available for {compiler} '
                f'and {mpi} on {machine}.'
            ) from err
    else:
        with open(yaml_template) as f:
            template = Template(f.read())

    yaml_data = template.render(
        specs=specs,
        e3sm_lapack=include_e3sm_lapack,
        e3sm_hdf5_netcdf=include_e3sm_hdf5_netcdf,
    )
    return yaml_data


def _get_modules(yaml_string):
    """Get a list of modules from a yaml file"""
    yaml_data = yaml.safe_load(yaml_string)
    mods = []
    if 'spack' in yaml_data and 'packages' in yaml_data['spack']:
        package_data = yaml_data['spack']['packages']
        for package in package_data.values():
            if 'externals' in package:
                for item in package['externals']:
                    if 'modules' in item:
                        for mod in item['modules']:
                            mods.append(f'module load {mod}')

    mods_str = '\n'.join(mods)

    return mods_str
