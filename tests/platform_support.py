"""Test-only helpers for platform-specific link creation and private-file assertions."""

import os

import pytest

from apixly_jev_harness import _secure_fs

WINDOWS = os.name == "nt"


def make_symlink(link, target, *, directory=False):
    """Create a symlink, or skip when Windows withholds the symlink privilege.

    Unprivileged Windows reparse-point rejection is covered by junction tests.
    """
    try:
        link.symlink_to(target, target_is_directory=directory)
    except OSError as error:
        if WINDOWS and getattr(error, "winerror", None) == 1314:
            pytest.skip("Windows symlink creation requires SeCreateSymbolicLinkPrivilege")
        raise


def make_junction(link, target):
    """Create an unprivileged Windows directory junction (a name-surrogate reparse point)."""
    import _winapi

    _winapi.CreateJunction(str(target), str(link))


def owner_only(path, *, directory=False):
    """Windows: protected DACL granting only the current user; POSIX: caller's mode check."""
    return _secure_fs.path_owner_only(path, directory=directory)


requires_fifo = pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no filesystem FIFOs")
windows_only = pytest.mark.skipif(not WINDOWS, reason="Windows reparse-point regression")
posix_only = pytest.mark.skipif(WINDOWS, reason="POSIX descriptor capability regression")


def broaden_access(path):
    """Grant another principal access: POSIX 0644, Windows an Everyone read ACE."""
    if WINDOWS:
        import subprocess

        subprocess.run(
            ["icacls", str(path), "/grant", "*S-1-1-0:R"], check=True, capture_output=True
        )
    else:
        path.chmod(0o644)


def restore_owner_only(path):
    if WINDOWS:
        import subprocess

        subprocess.run(
            ["icacls", str(path), "/remove:g", "*S-1-1-0"], check=True, capture_output=True
        )
    else:
        path.chmod(0o600)
