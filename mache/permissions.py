import grp
import os
import stat

import progressbar


def update_permissions(  # noqa: C901
    base_paths,
    group,
    show_progress=True,
    group_writable=False,
    other_readable=True,
):
    """
    Update the group that a directory belongs to along with the "group" and
    "other" permissions for the directory

    Parameters
    ----------
    base_paths : str or list
        The base path(s) to recursively update permissions on

    group : str
        The name of the group the contents of ``base_paths`` should belong to

    show_progress : bool, optional
        Whether to show a progress bar

    group_writable : bool, optional
        Whether to allow group write permissions

    other_readable : bool, optional
        Whether to allow world read (and, where appropriate, execute)
        permissions
    """

    if isinstance(base_paths, str):
        directories = [base_paths]
    else:
        directories = base_paths

    new_uid = os.getuid()
    new_gid = grp.getgrnam(group).gr_gid

    read_write_perm = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP
    exec_perm = (
        stat.S_IRUSR
        | stat.S_IWUSR
        | stat.S_IXUSR
        | stat.S_IRGRP
        | stat.S_IXGRP
    )

    if group_writable:
        read_write_perm = read_write_perm | stat.S_IWGRP
        exec_perm = exec_perm | stat.S_IWGRP
    if other_readable:
        read_write_perm = read_write_perm | stat.S_IROTH
        exec_perm = exec_perm | stat.S_IROTH | stat.S_IXOTH

    mask = stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO

    # first the base directories that don't seem to be included in
    # os.walk()
    for directory in directories:
        try:
            dir_stat = os.stat(directory)
        except OSError:
            continue

        perm = dir_stat.st_mode & mask

        if (
            perm == exec_perm
            and dir_stat.st_uid == new_uid
            and dir_stat.st_gid == new_gid
        ):
            continue

        try:
            os.chown(directory, new_uid, new_gid)
            os.chmod(directory, exec_perm)
        except OSError:
            continue

    files_and_dirs = []
    for base in directories:
        for _, dirs, files in os.walk(base):
            files_and_dirs.extend(dirs)
            files_and_dirs.extend(files)

    if show_progress:
        widgets = [
            progressbar.Percentage(),
            ' ',
            progressbar.Bar(),
            ' ',
            progressbar.ETA(),
        ]
        bar = progressbar.ProgressBar(
            widgets=widgets, maxval=len(files_and_dirs), maxerror=False
        ).start()
    else:
        bar = None
    progress = 0
    for base in directories:
        for root, dirs, files in os.walk(base):
            for directory in dirs:
                progress += 1
                if show_progress:
                    bar.update(progress)

                directory = os.path.join(root, directory)

                try:
                    dir_stat = os.stat(directory)
                except OSError:
                    continue

                perm = dir_stat.st_mode & mask

                if (
                    perm == exec_perm
                    and dir_stat.st_uid == new_uid
                    and dir_stat.st_gid == new_gid
                ):
                    continue

                try:
                    os.chown(directory, new_uid, new_gid)
                    os.chmod(directory, exec_perm)
                except OSError:
                    continue

            for file_name in files:
                progress += 1
                bar.update(progress)
                file_name = os.path.join(root, file_name)
                try:
                    file_stat = os.stat(file_name)
                except OSError:
                    continue

                perm = file_stat.st_mode & mask

                if perm & stat.S_IXUSR:
                    # executable, so make sure others can execute it
                    new_perm = exec_perm
                else:
                    new_perm = read_write_perm

                if (
                    perm == new_perm
                    and file_stat.st_uid == new_uid
                    and file_stat.st_gid == new_gid
                ):
                    continue

                try:
                    os.chown(file_name, new_uid, new_gid)
                    os.chmod(file_name, new_perm)
                except OSError:
                    continue

    if show_progress:
        bar.finish()
