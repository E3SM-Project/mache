import os
import subprocess
from jinja2 import Template
from importlib import resources

from mache.machine_info import discover_machine


def make_spack_env(spack_path, env_name, spack_specs, compiler, mpi,
                   machine=None):

    if machine is None:
        machine = discover_machine()
        if machine is None:
            raise ValueError('Unable to discover machine form host name')

    if not os.path.exists(spack_path):
        # we need to clone the spack repo
        clone = f'git clone -b spack_for_mache ' \
                f'git@github.com:E3SM-Project/spack.git {spack_path}'
    else:
        clone = ''

    # add the package specs to the appropriate template
    specs = ''.join([f'  - {spec}\n' for spec in spack_specs])

    template_filename = f'{machine}_{compiler}_{mpi}.yaml'
    try:
        template = Template(
            resources.read_text('mache.spack', template_filename))
    except FileNotFoundError:
        raise ValueError(f'Spack template not available for {compiler} and '
                         f'{mpi} on {machine}.')
    yaml_file = template.render(specs=specs)
    yaml_filename = os.path.abspath(f'{env_name}.yaml')
    with open(yaml_filename, 'w') as handle:
        handle.write(yaml_file)

    template = Template(
        resources.read_text('mache.spack', 'build_spack_env.template'))
    build_file = template.render(clone=clone, spack_path=spack_path,
                                 env_name=env_name, yaml_filename=yaml_filename)
    build_filename = f'build_{env_name}.bash'
    with open(build_filename, 'w') as handle:
        handle.write(build_file)

    # clear environment variables and start fresh with those from login
    # so spack doesn't get confused by conda
    subprocess.check_call(f'env -i bash -l {build_filename}', shell=True)
