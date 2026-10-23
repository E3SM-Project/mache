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
    recursive=True,
    owner_writable=True,
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

    recursive : bool, optional
        Whether to traverse the path(s) provided recursively

    owner_writable : bool, optional
        Whether the owner keeps write permission.  Use
        :py:func:`restore_owner_write` to give it back before modifying
        paths updated with ``owner_writable=False``.
    """

    if isinstance(base_paths, str):
        paths = [Path(base_paths)]
    else:
        paths = [Path(path) for path in base_paths]

    new_uid = os.getuid()
    new_gid = grp.getgrnam(group).gr_gid

    read_write_perm = stat.S_IRUSR | stat.S_IRGRP
    exec_perm = stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP

    if owner_writable:
        read_write_perm = read_write_perm | stat.S_IWUSR
        exec_perm = exec_perm | stat.S_IWUSR
    if group_writable:
        read_write_perm = read_write_perm | stat.S_IWGRP
        exec_perm = exec_perm | stat.S_IWGRP
    if other_readable:
        read_write_perm = read_write_perm | stat.S_IROTH
        exec_perm = exec_perm | stat.S_IROTH | stat.S_IXOTH

    mask = stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO

    for path in paths:
        if recursive and not path.is_file():
            print(f'Updating file permissions (recursively) for: {path}')
        else:
            print(f'Updating file permissions for: {path}')

        # start by updating the top level path (file or directory)
        _update(
            path,
            uid=new_uid,
            gid=new_gid,
            read_write_perm=read_write_perm,
            exec_perm=exec_perm,
            mask=mask,
        )

        # iterate over the path recursively, only if it's a direcotry
        if path.is_file():
            continue
        # only iterate directories recursively if requested
        elif not recursive:
            continue

        paths_iter = (p for p in Path(path).rglob('*'))
        n_files = sum(1 for _ in Path(path).rglob('*'))

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


def restore_owner_write(base_paths, show_progress=True):
    """
    Give the owner back write permission on path(s), recursively, so that a
    deployment made read-only with
    ``update_permissions(..., owner_writable=False)`` can be modified

    Only paths owned by the current user are changed, and symlinks are
    skipped.  A directory that is already owner-writable is assumed not to
    have been made read-only and is skipped without traversing it, which
    keeps this cheap for deployments that were never made read-only.

    Parameters
    ----------
    base_paths : str or list
        The base path(s) to restore owner write permission on.  Paths that
        do not exist are ignored.

    show_progress : bool, optional
        Whether to show a progress bar
    """

    if isinstance(base_paths, str):
        paths = [Path(base_paths)]
    else:
        paths = [Path(path) for path in base_paths]

    uid = os.getuid()

    for path in paths:
        try:
            path_stat = os.lstat(path)
        except OSError:
            continue
        if stat.S_ISLNK(path_stat.st_mode):
            continue
        if stat.S_ISDIR(path_stat.st_mode):
            if path_stat.st_mode & stat.S_IWUSR:
                continue
            print(
                f'Restoring owner write permission (recursively) for: {path}'
            )
            with tqdm(
                unit='item',
                dynamic_ncols=True,
                disable=(not show_progress),
            ) as bar:
                # children before their directory, so an interrupted run
                # leaves the top directory read-only and is redone next time
                for root, dirs, files in os.walk(path, topdown=False):
                    for name in files + dirs:
                        _add_owner_write(Path(root) / name, uid)
                        bar.update(1)
        _add_owner_write(path, uid)


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
    except OSError:
        pass


def _add_owner_write(path: Path, uid: int) -> None:
    """
    Add owner write permission to a single path the current user owns
    """
    try:
        path_stat = os.lstat(path)
        if stat.S_ISLNK(path_stat.st_mode) or path_stat.st_uid != uid:
            return
        if not path_stat.st_mode & stat.S_IWUSR:
            os.chmod(path, stat.S_IMODE(path_stat.st_mode) | stat.S_IWUSR)
    except OSError:
        pass
