import grp
import os
import stat
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tqdm import tqdm


def update_permissions(  # noqa: C901
    base_paths,
    group,
    show_progress=True,
    group_writable=False,
    other_readable=True,
    workers=4,
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

    workers : int, optional
        Number of threads to parallelize across
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

        files = Path(directory).rglob('*')
        paths_iter = (p for p in files)
        n_files = sum(1 for _ in files)

        print(f'Updating file permissions for: {directory}')

        with (
            ThreadPoolExecutor(max_workers=workers) as pool,
            tqdm(
                total=n_files,
                unit='item',
                dynamic_ncols=True,
                disable=(not show_progress),
            ) as bar,
        ):
            futures = [
                pool.submit(
                    _update,
                    p,
                    uid=new_uid,
                    gid=new_gid,
                    read_write_perm=read_write_perm,
                    exec_perm=exec_perm,
                    mask=mask,
                )
                for p in paths_iter
            ]

            for fut in as_completed(futures):
                bar.update(1)
                fut.result()


def _update(
    path: Path,
    uid: int,
    gid: int,
    read_write_perm: int,
    exec_perm: int,
    mask: int,
) -> None:
    """
    Update file permissions for a single path
    """
    try:
        _stat = os.stat(path)
        _perm = _stat.st_mode & mask

        if path.is_file():
            if _perm & stat.S_IXUSR:
                new_perm = exec_perm
            else:
                new_perm = read_write_perm
        elif path.is_dir():
            new_perm = exec_perm

        if _perm == new_perm and _stat.st_uid == uid and _stat.st_gid == gid:
            return

        os.chown(path, uid, gid)
        os.chmod(path, new_perm)
    except OSError as e:
        print(f'{e} – skipping {path}')
