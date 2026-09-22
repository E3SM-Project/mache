import re

# must match the git tag exactly, including any rc suffix, since this is
# the version published to PyPI
__version__ = '4.0.1rc1'

# the numeric part of the version, e.g. (4, 0, 1) for '4.0.1rc1'
__version_info__ = tuple(
    int(part)
    for part in re.split(r'[^\d.]', __version__, maxsplit=1)[0].split('.')
)
