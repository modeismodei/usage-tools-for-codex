# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Usage Tools for Codex contributors
"""Small native file/lock primitives; POSIX callers retain their original semantics."""
import errno
import os
import pathlib
import stat
from contextlib import contextmanager

WINDOWS = os.name == 'nt'

if WINDOWS:
    import ctypes as ct
    from ctypes import wintypes as wt
    import msvcrt

    kernel = ct.WinDLL('kernel32', use_last_error=True)
    security = ct.WinDLL('advapi32', use_last_error=True)

    class SecurityAttributes(ct.Structure):
        _fields_ = [('length', wt.DWORD), ('descriptor', wt.LPVOID), ('inherit', wt.BOOL)]

    class FileInformation(ct.Structure):
        _fields_ = [('attributes', wt.DWORD), ('creation', wt.FILETIME),
                    ('access', wt.FILETIME), ('write', wt.FILETIME),
                    ('volume', wt.DWORD), ('size_high', wt.DWORD), ('size_low', wt.DWORD),
                    ('links', wt.DWORD), ('index_high', wt.DWORD), ('index_low', wt.DWORD)]

    def api(dll, name, result, *args):
        fn = getattr(dll, name)
        fn.restype, fn.argtypes = result, args
        return fn

    close_handle = api(kernel, 'CloseHandle', wt.BOOL, wt.HANDLE)
    local_free = api(kernel, 'LocalFree', wt.LPVOID, wt.LPVOID)
    create_file = api(kernel, 'CreateFileW', wt.HANDLE, wt.LPCWSTR, wt.DWORD, wt.DWORD,
                      ct.POINTER(SecurityAttributes), wt.DWORD, wt.DWORD, wt.HANDLE)
    file_info = api(kernel, 'GetFileInformationByHandle', wt.BOOL, wt.HANDLE, ct.POINTER(FileInformation))
    file_type = api(kernel, 'GetFileType', wt.DWORD, wt.HANDLE)
    create_directory = api(kernel, 'CreateDirectoryW', wt.BOOL, wt.LPCWSTR, ct.POINTER(SecurityAttributes))
    convert_sd = api(security, 'ConvertStringSecurityDescriptorToSecurityDescriptorW', wt.BOOL,
                     wt.LPCWSTR, wt.DWORD, ct.POINTER(wt.LPVOID), ct.POINTER(wt.DWORD))
    convert_sid = api(security, 'ConvertSidToStringSidW', wt.BOOL, wt.LPVOID, ct.POINTER(wt.LPWSTR))
    open_token = api(security, 'OpenProcessToken', wt.BOOL, wt.HANDLE, wt.DWORD, ct.POINTER(wt.HANDLE))
    get_token = api(security, 'GetTokenInformation', wt.BOOL, wt.HANDLE, ct.c_int, wt.LPVOID,
                    wt.DWORD, ct.POINTER(wt.DWORD))
    get_process = api(kernel, 'GetCurrentProcess', wt.HANDLE)
    get_security = api(security, 'GetFileSecurityW', wt.BOOL, wt.LPCWSTR, wt.DWORD,
                       wt.LPVOID, wt.DWORD, ct.POINTER(wt.DWORD))
    get_dacl = api(security, 'GetSecurityDescriptorDacl', wt.BOOL, wt.LPVOID,
                   ct.POINTER(wt.BOOL), ct.POINTER(wt.LPVOID), ct.POINTER(wt.BOOL))
    get_ace = api(security, 'GetAce', wt.BOOL, wt.LPVOID, wt.DWORD, ct.POINTER(wt.LPVOID))

    def checked(ok):
        if not ok:
            raise ct.WinError(ct.get_last_error())

    def sid_text(sid):
        value = wt.LPWSTR()
        checked(convert_sid(sid, ct.byref(value)))
        try:
            return value.value
        finally:
            local_free(ct.cast(value, wt.LPVOID))

    def user_sid():
        token = wt.HANDLE()
        checked(open_token(get_process(), 8, ct.byref(token)))  # TOKEN_QUERY
        try:
            size = wt.DWORD()
            get_token(token, 1, None, 0, ct.byref(size))  # TokenUser
            buf = ct.create_string_buffer(size.value)
            checked(get_token(token, 1, buf, size, ct.byref(size)))
            return sid_text(ct.cast(buf, ct.POINTER(wt.LPVOID))[0])
        finally:
            close_handle(token)

    @contextmanager
    def private_security(directory=False):
        inheritance = 'OICI' if directory else ''
        descriptor = wt.LPVOID()
        acl = 'D:P' + ''.join(f'(A;{inheritance};FA;;;{sid})'
                              for sid in (user_sid(), 'SY', 'BA'))
        checked(convert_sd(acl, 1, ct.byref(descriptor), None))
        try:
            yield SecurityAttributes(ct.sizeof(SecurityAttributes), descriptor, False)
        finally:
            local_free(descriptor)

    def validate_private_directory(path):
        """Do not rewrite existing ACLs; reject unsafe sidecar inheritance instead."""
        size = wt.DWORD()
        get_security(str(path), 4, None, 0, ct.byref(size))
        buf = ct.create_string_buffer(size.value)
        checked(get_security(str(path), 4, buf, size, ct.byref(size)))
        present, defaulted, acl = wt.BOOL(), wt.BOOL(), wt.LPVOID()
        checked(get_dacl(buf, ct.byref(present), ct.byref(acl), ct.byref(defaulted)))
        if not present or not acl:
            raise ValueError('State directory needs a private ACL; choose a new data directory')
        # ACL header: revision, padding, size, ACE count, padding.
        count = ct.cast(acl, ct.POINTER(ct.c_ushort))[2]
        allowed = {user_sid(), 'S-1-5-18', 'S-1-5-32-544', 'S-1-3-0', 'S-1-3-4'}
        for i in range(count):
            ace = wt.LPVOID()
            checked(get_ace(acl, i, ct.byref(ace)))
            kind = ct.c_ubyte.from_address(ace.value).value
            if kind == 1:  # A deny ACE cannot broaden access.
                continue
            if kind != 0 or sid_text(ace.value + 8) not in allowed:
                raise ValueError('State directory needs a private ACL; choose a new data directory')

    def windows_open(path, mode):
        read = mode == 'rb'
        exclusive = mode in ('x', 'xb')
        with private_security() as sa:
            handle = create_file(str(path), 0x80000000 if read else 0x40000000,
                                 3, ct.byref(sa), 3 if read else 1 if exclusive else 4,
                                 0x00200000 | 0x02000000, None)
            error = ct.get_last_error()
        if handle == wt.HANDLE(-1).value:
            raise ct.WinError(error)
        try:
            info = FileInformation()
            checked(file_info(handle, ct.byref(info)))
            if file_type(handle) != 1 or info.attributes & (0x400 | 0x10) or info.links != 1:
                raise ValueError('State file must be regular and have one link: '+path.name)
            flags = (os.O_RDONLY if read else os.O_WRONLY) | os.O_BINARY
            if not read and not exclusive:
                flags |= os.O_APPEND
            fd = msvcrt.open_osfhandle(handle, flags)
            handle = None  # fd now owns the handle.
            try:
                os.set_inheritable(fd, False)
                return os.fdopen(fd, mode)
            except BaseException:
                os.close(fd)
                raise
        finally:
            if handle is not None:
                close_handle(handle)
else:
    import fcntl


def is_alias(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def private_mkdir(path):
    path = pathlib.Path(path)
    if not WINDOWS:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        return
    if path.exists():
        if not path.is_dir() or is_alias(path):
            raise ValueError('State path must be a regular directory')
        validate_private_directory(path)
        return
    if not path.parent.exists():
        private_mkdir(path.parent)
    with private_security(directory=True) as sa:
        if not create_directory(str(path), ct.byref(sa)):
            if ct.get_last_error() != 183:
                raise ct.WinError(ct.get_last_error())
            private_mkdir(path)


def lock_file(stream):
    if WINDOWS:
        os.lseek(stream.fileno(), 0, os.SEEK_SET)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EDEADLK):
                raise BlockingIOError(errno.EAGAIN, 'Lock is held') from None
            raise
    else:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)


def unlock_file(stream):
    if WINDOWS:
        os.lseek(stream.fileno(), 0, os.SEEK_SET)
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(stream, fcntl.LOCK_UN)


def short_executable_path(path):
    """Keep .cmd files ASCII without changing the user's console code page."""
    short_path = api(kernel, 'GetShortPathNameW', wt.DWORD, wt.LPCWSTR, wt.LPWSTR, wt.DWORD)
    needed = short_path(path, None, 0)
    checked(needed)
    buf = ct.create_unicode_buffer(needed)
    checked(short_path(path, buf, needed))
    if not buf.value.isascii():
        raise ValueError('This Python path has no ASCII short-path alias; install using a Python '
                         'interpreter in an ASCII path. No console code page was changed.')
    return buf.value
