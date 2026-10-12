"""Owner-only files and descriptor-relative, no-follow directory access.

POSIX uses ``dir_fd``/``O_NOFOLLOW`` opens and 0600/0700 modes. Windows uses
handle-relative ``NtCreateFile`` opens with ``FILE_OPEN_REPARSE_POINT``, rejects every
reparse point (symlinks, junctions and WSL/LX links that Python reports as regular
files), enumerates directories from the open handle and applies protected owner-only
DACLs. Platforms offering neither fail closed; there is no path-string fallback.
"""

import os
import stat
import sys

WINDOWS = sys.platform == "win32"


def _posix_available():
    return (
        os.open in os.supports_dir_fd
        and os.scandir in os.supports_fd
        and hasattr(os, "O_NOFOLLOW")
        and hasattr(os, "O_DIRECTORY")
    )


def available():
    """True when a no-follow, descriptor-relative backend exists on this platform."""
    return _windows_ready() if WINDOWS else _posix_available()


def _check_name(name):
    if (
        type(name) is not str
        or not name
        or name in (".", "..")
        or any(c in name for c in "/\\\x00")
        or (WINDOWS and ":" in name)
    ):
        raise OSError(22, "secure_fs_name_not_allowed")


class _PosixDirectory:
    _FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)

    def __init__(self, fd):
        self.fd = fd

    @classmethod
    def open(cls, path):
        if not _posix_available():
            raise OSError(95, "secure_fs_unavailable")
        return cls(os.open(path, cls._FLAGS))

    def child(self, name):
        _check_name(name)
        return _PosixDirectory(os.open(name, self._FLAGS, dir_fd=self.fd))

    def duplicate(self):
        return _PosixDirectory(os.dup(self.fd))

    def entries(self, limit):
        rows = []
        with os.scandir(self.fd) as listing:
            for entry in listing:
                if len(rows) > limit:
                    break
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError:
                    rows.append((entry.name, "unreadable", 0))
                    continue
                if stat.S_ISLNK(info.st_mode):
                    kind = "link"
                elif stat.S_ISDIR(info.st_mode):
                    kind = "directory"
                elif stat.S_ISREG(info.st_mode):
                    kind = "file"
                else:
                    kind = "other"
                rows.append((entry.name, kind, info.st_size))
        return rows

    def names(self):
        return os.listdir(self.fd)

    def open_file(self, name):
        _check_name(name)
        fd = os.open(
            name, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0), dir_fd=self.fd
        )
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            raise OSError(22, "secure_fs_regular_file_required")
        return fd

    def create_private(self, name):
        _check_name(name)
        return os.open(
            name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd
        )

    def unlink(self, name):
        _check_name(name)
        os.unlink(name, dir_fd=self.fd)

    def rename(self, source, destination):
        _check_name(source)
        _check_name(destination)
        os.rename(source, destination, src_dir_fd=self.fd, dst_dir_fd=self.fd)

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


def open_directory(path):
    """Open a directory without following its final component."""
    if WINDOWS:
        return _WindowsDirectory.open(path)
    return _PosixDirectory.open(path)


def open_private_file(path, mode):
    """Open a private regular file without following its final component.

    ``x`` creates write-only, ``x+`` creates read-write and ``r+`` reopens an existing
    file read-write. ``a`` appends, creating the file privately when absent. Existing
    files must already be owner-only regular files. Returns an OS file descriptor.
    """
    if mode not in ("x", "x+", "r+", "a"):
        raise ValueError("invalid_private_file_mode")
    if WINDOWS:
        return _windows_private_file(path, mode)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if mode == "a":
        try:
            return os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_APPEND, 0o600)
        except FileExistsError:
            if not nofollow:
                raise OSError(95, "secure_fs_unavailable") from None
            fd = os.open(path, os.O_WRONLY | os.O_APPEND | nofollow)
            if not owner_only(fd):
                os.close(fd)
                raise OSError(1, "secure_fs_owner_changed") from None
            return fd
    if mode == "r+":
        if not nofollow:
            raise OSError(95, "secure_fs_unavailable")
        return os.open(path, os.O_RDWR | nofollow)
    flags = os.O_CREAT | os.O_EXCL | (os.O_RDWR if mode == "x+" else os.O_WRONLY)
    return os.open(path, flags | nofollow, 0o600)


def owner_only(fd, *, directory=False):
    """True when an open regular file/directory is accessible only by the current user."""
    if WINDOWS:
        return _windows_owner_only(msvcrt.get_osfhandle(fd), directory=directory)
    info = os.fstat(fd)
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    return (
        kind(info.st_mode)
        and stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600)
        and (not hasattr(os, "getuid") or info.st_uid == os.getuid())
    )


def path_owner_only(path, *, directory=False):
    """Check a path's own entry (never a reparse/symlink target) for owner-only access."""
    if WINDOWS:
        handle = _windows_path_handle(path, directory=directory, access=_READ_CONTROL)
        try:
            return _windows_owner_only(handle, directory=directory)
        finally:
            _kernel32.CloseHandle(handle)
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode):
        return False
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    return (
        kind(info.st_mode)
        and stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600)
        and (not hasattr(os, "getuid") or info.st_uid == os.getuid())
    )


def is_link(path):
    """True for symlinks and, on Windows, every reparse point including junctions/LX links."""
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    return bool(getattr(info, "st_file_attributes", 0) & 0x400)


def make_private_directory(path, *, parents=False, exist_ok=False):
    """Create a directory accessible only by the current user (0700 or protected DACL)."""
    path = os.fspath(path)
    if parents:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    try:
        if WINDOWS:
            _windows_mkdir(path)
        else:
            os.mkdir(path, 0o700)
    except FileExistsError:
        if not exist_ok or not os.path.isdir(path) or is_link(path):
            raise


# ---------------------------------------------------------------------------
# Windows backend
# ---------------------------------------------------------------------------

_READ_CONTROL = 0x00020000

if WINDOWS:  # pragma: no cover - exercised by the Windows test run
    import ctypes
    import msvcrt
    import struct
    from ctypes import wintypes

    _ntdll = ctypes.WinDLL("ntdll")
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

    _DELETE = 0x00010000
    _SYNCHRONIZE = 0x00100000
    _GENERIC_READ = 0x80000000
    _GENERIC_WRITE = 0x40000000
    _FILE_READ_DATA = 0x0001
    _FILE_LIST_DIRECTORY = 0x0001
    _FILE_WRITE_DATA = 0x0002
    _FILE_APPEND_DATA = 0x0004
    _FILE_TRAVERSE = 0x0020
    _FILE_READ_ATTRIBUTES = 0x0080
    _SHARE_ALL = 0x7
    _FILE_OPEN, _FILE_CREATE = 1, 2
    _FILE_DIRECTORY_FILE = 0x00000001
    _FILE_SYNCHRONOUS_IO_NONALERT = 0x00000020
    _FILE_NON_DIRECTORY_FILE = 0x00000040
    _FILE_DELETE_ON_CLOSE = 0x00001000
    _FILE_OPEN_REPARSE_POINT = 0x00200000
    _OBJ_CASE_INSENSITIVE = 0x40
    _ATTR_DIRECTORY, _ATTR_REPARSE = 0x10, 0x400
    _INVALID = ctypes.c_void_p(-1).value
    _OPEN_EXISTING, _CREATE_NEW, _OPEN_ALWAYS = 3, 1, 4
    _FLAG_BACKUP_SEMANTICS, _FLAG_OPEN_REPARSE = 0x02000000, 0x00200000
    _FILE_TYPE_DISK = 1

    class _UnicodeString(ctypes.Structure):
        _fields_ = [
            ("Length", wintypes.USHORT),
            ("MaximumLength", wintypes.USHORT),
            ("Buffer", ctypes.c_void_p),
        ]

    class _ObjectAttributes(ctypes.Structure):
        _fields_ = [
            ("Length", wintypes.ULONG),
            ("RootDirectory", wintypes.HANDLE),
            ("ObjectName", ctypes.POINTER(_UnicodeString)),
            ("Attributes", wintypes.ULONG),
            ("SecurityDescriptor", ctypes.c_void_p),
            ("SecurityQualityOfService", ctypes.c_void_p),
        ]

    class _IoStatusBlock(ctypes.Structure):
        _fields_ = [("Status", ctypes.c_void_p), ("Information", ctypes.c_size_t)]

    class _SecurityAttributes(ctypes.Structure):
        _fields_ = [
            ("nLength", wintypes.DWORD),
            ("lpSecurityDescriptor", ctypes.c_void_p),
            ("bInheritHandle", wintypes.BOOL),
        ]

    _ntdll.NtCreateFile.restype = ctypes.c_long
    _ntdll.NtCreateFile.argtypes = [
        ctypes.POINTER(wintypes.HANDLE),
        wintypes.DWORD,
        ctypes.POINTER(_ObjectAttributes),
        ctypes.POINTER(_IoStatusBlock),
        ctypes.c_void_p,
        wintypes.ULONG,
        wintypes.ULONG,
        wintypes.ULONG,
        wintypes.ULONG,
        ctypes.c_void_p,
        wintypes.ULONG,
    ]
    _ntdll.NtSetInformationFile.restype = ctypes.c_long
    _ntdll.NtSetInformationFile.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_IoStatusBlock),
        ctypes.c_void_p,
        wintypes.ULONG,
        ctypes.c_int,
    ]
    _ntdll.RtlNtStatusToDosError.restype = wintypes.ULONG
    _ntdll.RtlNtStatusToDosError.argtypes = [ctypes.c_long]
    _kernel32.CreateFileW.restype = wintypes.HANDLE
    _kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    _kernel32.CreateDirectoryW.restype = wintypes.BOOL
    _kernel32.CreateDirectoryW.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p]
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.GetFileType.restype = wintypes.DWORD
    _kernel32.GetFileType.argtypes = [wintypes.HANDLE]
    _kernel32.GetFileInformationByHandleEx.restype = wintypes.BOOL
    _kernel32.GetFileInformationByHandleEx.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    _kernel32.DuplicateHandle.restype = wintypes.BOOL
    _kernel32.DuplicateHandle.argtypes = [
        wintypes.HANDLE,
        wintypes.HANDLE,
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.HANDLE),
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    ]
    _kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _advapi32.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    _advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _advapi32.ConvertSidToStringSidW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    _advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
    ]
    _advapi32.GetSecurityInfo.restype = wintypes.DWORD
    _advapi32.GetSecurityInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    _advapi32.GetSecurityDescriptorControl.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.WORD),
        ctypes.POINTER(wintypes.DWORD),
    ]
    _advapi32.GetAce.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)]
    _advapi32.EqualSid.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    _advapi32.IsValidSid.argtypes = [ctypes.c_void_p]

    def _raise_status(status):
        error = _ntdll.RtlNtStatusToDosError(status)
        raise ctypes.WinError(error)

    def _raise_last():
        raise ctypes.WinError(ctypes.get_last_error())

    _TOKEN_BUFFER = None

    def _user_sid():
        """Pointer to the current process user's SID (kept alive for the process)."""
        global _TOKEN_BUFFER
        if _TOKEN_BUFFER is None:
            token = wintypes.HANDLE()
            if not _advapi32.OpenProcessToken(_kernel32.GetCurrentProcess(), 0x8, token):
                _raise_last()
            try:
                size = wintypes.DWORD()
                _advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
                buffer = ctypes.create_string_buffer(size.value)
                if not _advapi32.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)):
                    _raise_last()
            finally:
                _kernel32.CloseHandle(token)
            _TOKEN_BUFFER = buffer
        return ctypes.cast(_TOKEN_BUFFER, ctypes.POINTER(ctypes.c_void_p))[0]

    def _user_sid_string():
        text = ctypes.c_void_p()
        if not _advapi32.ConvertSidToStringSidW(_user_sid(), ctypes.byref(text)):
            _raise_last()
        try:
            return ctypes.wstring_at(text.value)
        finally:
            _kernel32.LocalFree(text)

    class _OwnerOnlyDescriptor:
        """Protected owner-only security descriptor; inheritable for directories."""

        def __init__(self, directory):
            sid = _user_sid_string()
            inherit = "OICI" if directory else ""
            self.pointer = ctypes.c_void_p()
            if not _advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
                f"O:{sid}D:P(A;{inherit};FA;;;{sid})", 1, ctypes.byref(self.pointer), None
            ):
                _raise_last()

        def attributes(self):
            value = _SecurityAttributes()
            value.nLength = ctypes.sizeof(value)
            value.lpSecurityDescriptor = self.pointer
            return value

        def close(self):
            if self.pointer:
                _kernel32.LocalFree(self.pointer)
                self.pointer = ctypes.c_void_p()

    def _attribute_tag(handle):
        info = (wintypes.DWORD * 2)()
        if not _kernel32.GetFileInformationByHandleEx(handle, 9, info, ctypes.sizeof(info)):
            _raise_last()
        return info[0], info[1]

    def _require_kind(handle, directory):
        attributes, _ = _attribute_tag(handle)
        if attributes & _ATTR_REPARSE:
            raise OSError(22, "secure_fs_reparse_point_rejected")
        if bool(attributes & _ATTR_DIRECTORY) != directory:
            raise OSError(22, "secure_fs_kind_mismatch")
        if not directory and _kernel32.GetFileType(handle) != _FILE_TYPE_DISK:
            raise OSError(22, "secure_fs_regular_file_required")

    def _extended(path):
        absolute = os.path.abspath(os.fspath(path))
        if absolute.startswith("\\\\?\\"):
            return absolute
        if absolute.startswith("\\\\"):
            return "\\\\?\\UNC\\" + absolute[2:]
        return "\\\\?\\" + absolute

    def _windows_path_handle(path, *, directory, access, disposition=None, security=None):
        flags = _FLAG_OPEN_REPARSE | (_FLAG_BACKUP_SEMANTICS if directory else 0)
        handle = _kernel32.CreateFileW(
            _extended(path),
            access | _FILE_READ_ATTRIBUTES | _READ_CONTROL,
            _SHARE_ALL if directory else 0x3,
            ctypes.byref(security) if security is not None else None,
            disposition or _OPEN_EXISTING,
            flags,
            None,
        )
        if handle in (None, _INVALID):
            _raise_last()
        try:
            _require_kind(handle, directory)
        except BaseException:
            _kernel32.CloseHandle(handle)
            raise
        return handle

    def _nt_open(root, name, *, access, options, disposition=_FILE_OPEN, descriptor=None):
        _check_name(name)
        buffer = ctypes.create_unicode_buffer(name)
        size = len(name.encode("utf-16-le", "surrogatepass"))
        if size > 0xFFF0:
            raise OSError(36, "secure_fs_name_too_long")
        text = _UnicodeString(size, size, ctypes.cast(buffer, ctypes.c_void_p))
        attributes = _ObjectAttributes(
            ctypes.sizeof(_ObjectAttributes),
            root,
            ctypes.pointer(text),
            _OBJ_CASE_INSENSITIVE,
            descriptor,
            None,
        )
        handle, status_block = wintypes.HANDLE(), _IoStatusBlock()
        status = _ntdll.NtCreateFile(
            ctypes.byref(handle),
            access | _SYNCHRONIZE,
            ctypes.byref(attributes),
            ctypes.byref(status_block),
            None,
            0,
            _SHARE_ALL,
            disposition,
            options | _FILE_SYNCHRONOUS_IO_NONALERT | _FILE_OPEN_REPARSE_POINT,
            None,
            0,
        )
        if status < 0:
            _raise_status(status)
        return handle.value

    def _windows_owner_only(handle, *, directory=False):
        attributes, _ = _attribute_tag(handle)
        if attributes & _ATTR_REPARSE or bool(attributes & _ATTR_DIRECTORY) != directory:
            return False
        owner, dacl, descriptor = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
        if _advapi32.GetSecurityInfo(
            handle,
            1,
            0x1 | 0x4,
            ctypes.byref(owner),
            None,
            ctypes.byref(dacl),
            None,
            ctypes.byref(descriptor),
        ):
            return False
        try:
            user = _user_sid()
            control, revision = wintypes.WORD(), wintypes.DWORD()
            if not _advapi32.GetSecurityDescriptorControl(
                descriptor, ctypes.byref(control), ctypes.byref(revision)
            ):
                return False
            if not owner or not _advapi32.EqualSid(owner, user):
                return False
            # A null DACL grants everyone; inheritance must not add other principals.
            if not dacl.value or not control.value & 0x1000:
                return False
            count = struct.unpack_from("<H", ctypes.string_at(dacl.value, 8), 4)[0]
            if count < 1:
                return False
            for index in range(count):
                ace = ctypes.c_void_p()
                if not _advapi32.GetAce(dacl, index, ctypes.byref(ace)):
                    return False
                kind = ctypes.string_at(ace.value, 1)[0]
                sid = ace.value + 8
                if kind != 0 or not _advapi32.IsValidSid(sid) or not _advapi32.EqualSid(sid, user):
                    return False
            return True
        finally:
            _kernel32.LocalFree(descriptor)

    def _windows_private_file(path, mode):
        access = {
            "x": _GENERIC_WRITE,
            "x+": _GENERIC_READ | _GENERIC_WRITE,
            "r+": _GENERIC_READ | _GENERIC_WRITE,
            "a": _FILE_APPEND_DATA | _READ_CONTROL | _FILE_READ_ATTRIBUTES,
        }[mode]
        descriptor = _OwnerOnlyDescriptor(directory=False)
        try:
            security = descriptor.attributes()
            disposition = {"x": _CREATE_NEW, "x+": _CREATE_NEW, "r+": _OPEN_EXISTING}.get(mode)
            if mode == "a":
                try:
                    handle = _windows_path_handle(
                        path,
                        directory=False,
                        access=access,
                        disposition=_CREATE_NEW,
                        security=security,
                    )
                except FileExistsError:
                    handle = _windows_path_handle(path, directory=False, access=access)
                    if not _windows_owner_only(handle):
                        _kernel32.CloseHandle(handle)
                        raise OSError(1, "secure_fs_owner_changed") from None
            else:
                handle = _windows_path_handle(
                    path,
                    directory=False,
                    access=access,
                    disposition=disposition,
                    security=security if disposition == _CREATE_NEW else None,
                )
        finally:
            descriptor.close()
        flags = {"x": os.O_WRONLY, "x+": os.O_RDWR, "r+": os.O_RDWR, "a": os.O_WRONLY | os.O_APPEND}
        try:
            return msvcrt.open_osfhandle(handle, flags[mode])
        except BaseException:
            _kernel32.CloseHandle(handle)
            raise

    def _windows_mkdir(path):
        descriptor = _OwnerOnlyDescriptor(directory=True)
        try:
            security = descriptor.attributes()
            if not _kernel32.CreateDirectoryW(_extended(path), ctypes.byref(security)):
                _raise_last()
        finally:
            descriptor.close()

    class _WindowsDirectory:
        _ACCESS = _FILE_LIST_DIRECTORY | _FILE_TRAVERSE | _FILE_READ_ATTRIBUTES

        def __init__(self, handle):
            self.handle = handle

        @classmethod
        def open(cls, path):
            return cls(_windows_path_handle(path, directory=True, access=cls._ACCESS))

        def child(self, name):
            handle = _nt_open(self.handle, name, access=self._ACCESS, options=_FILE_DIRECTORY_FILE)
            try:
                _require_kind(handle, True)
            except BaseException:
                _kernel32.CloseHandle(handle)
                raise
            return _WindowsDirectory(handle)

        def duplicate(self):
            process = _kernel32.GetCurrentProcess()
            target = wintypes.HANDLE()
            if not _kernel32.DuplicateHandle(
                process, self.handle, process, ctypes.byref(target), 0, False, 0x2
            ):
                _raise_last()
            return _WindowsDirectory(target.value)

        def _listing(self):
            buffer = ctypes.create_string_buffer(65536)
            information = 15  # FileFullDirectoryRestartInfo
            while True:
                if not _kernel32.GetFileInformationByHandleEx(
                    self.handle, information, buffer, len(buffer)
                ):
                    error = ctypes.get_last_error()
                    if error == 18:  # ERROR_NO_MORE_FILES
                        return
                    raise ctypes.WinError(error)
                information = 14  # FileFullDirectoryInfo
                offset = 0
                while True:
                    following, _, *_, size, _, attributes, length, _ = struct.unpack_from(
                        "<IIqqqqqqIII", buffer, offset
                    )
                    raw = ctypes.string_at(ctypes.addressof(buffer) + offset + 68, length)
                    name = raw.decode("utf-16-le", "surrogatepass")
                    if name not in (".", ".."):
                        yield name, attributes, size
                    if not following:
                        break
                    offset += following

        def entries(self, limit):
            rows = []
            for name, attributes, size in self._listing():
                if len(rows) > limit:
                    break
                if attributes & _ATTR_REPARSE:
                    kind = "link"
                elif attributes & _ATTR_DIRECTORY:
                    kind = "directory"
                else:
                    kind = "file"
                rows.append((name, kind, size))
            return rows

        def names(self):
            return [name for name, _, _ in self._listing()]

        def open_file(self, name):
            handle = _nt_open(
                self.handle,
                name,
                access=_FILE_READ_DATA | _FILE_READ_ATTRIBUTES | _READ_CONTROL,
                options=_FILE_NON_DIRECTORY_FILE,
            )
            try:
                _require_kind(handle, False)
                return msvcrt.open_osfhandle(handle, os.O_RDONLY)
            except BaseException:
                _kernel32.CloseHandle(handle)
                raise

        def create_private(self, name):
            descriptor = _OwnerOnlyDescriptor(directory=False)
            try:
                handle = _nt_open(
                    self.handle,
                    name,
                    access=_GENERIC_WRITE | _FILE_READ_ATTRIBUTES,
                    options=_FILE_NON_DIRECTORY_FILE,
                    disposition=_FILE_CREATE,
                    descriptor=descriptor.pointer,
                )
            finally:
                descriptor.close()
            try:
                return msvcrt.open_osfhandle(handle, os.O_WRONLY)
            except BaseException:
                _kernel32.CloseHandle(handle)
                raise

        def unlink(self, name):
            handle = _nt_open(
                self.handle,
                name,
                access=_DELETE | _FILE_READ_ATTRIBUTES,
                options=_FILE_NON_DIRECTORY_FILE | _FILE_DELETE_ON_CLOSE,
            )
            _kernel32.CloseHandle(handle)

        def rename(self, source, destination):
            _check_name(destination)
            handle = _nt_open(
                self.handle,
                source,
                access=_DELETE | _FILE_READ_ATTRIBUTES,
                options=_FILE_NON_DIRECTORY_FILE,
            )
            try:
                encoded = destination.encode("utf-16-le", "surrogatepass")

                class _Rename(ctypes.Structure):
                    _fields_ = [
                        ("ReplaceIfExists", ctypes.c_ubyte),
                        ("RootDirectory", wintypes.HANDLE),
                        ("FileNameLength", wintypes.ULONG),
                        ("FileName", ctypes.c_byte * len(encoded)),
                    ]

                value = _Rename(0, self.handle, len(encoded))
                ctypes.memmove(value.FileName, encoded, len(encoded))
                status_block = _IoStatusBlock()
                status = _ntdll.NtSetInformationFile(
                    handle,
                    ctypes.byref(status_block),
                    ctypes.byref(value),
                    ctypes.sizeof(value),
                    10,
                )
                if status < 0:
                    _raise_status(status)
            finally:
                _kernel32.CloseHandle(handle)

        def close(self):
            if self.handle is not None:
                _kernel32.CloseHandle(self.handle)
                self.handle = None


def _windows_ready():
    if not WINDOWS:
        return False
    try:
        _user_sid()
    except OSError:  # pragma: no cover - token access denied
        return False
    return True
