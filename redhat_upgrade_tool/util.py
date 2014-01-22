# util.py - various shared utility functions
#
# Copyright (C) 2012 Red Hat Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Author: Will Woods <wwoods@redhat.com>

import os, struct
from shutil import rmtree
from subprocess import Popen, PIPE, STDOUT
from pipes import quote as shellquote

from redhat_upgrade_tool import pkgname
import logging
log = logging.getLogger(pkgname+".util")

try:
    from ctypes import cdll, c_bool
    selinux = cdll.LoadLibrary("libselinux.so.1")
    is_selinux_enabled = selinux.is_selinux_enabled
    is_selinux_enabled.restype = c_bool
except (ImportError, AttributeError, OSError):
    is_selinux_enabled = lambda: False

class CalledProcessError(Exception):
    """From subprocesses.CalledProcessError in Python 2.7"""
    def __init__(self, returncode, cmd, output=None):
        self.returncode = returncode
        self.cmd = cmd
        self.output = output
    def __str__(self):
        return "Command '%s' returned non-zero exit status %d" % (self.cmd, self.returncode)

def call(*popenargs, **kwargs):
    return Popen(*popenargs, **kwargs).wait()

def check_output(*popenargs, **kwargs):
    if 'stdout' in kwargs:
        raise ValueError('stdout argument not allowed, it will be overridden.')
    process = Popen(stdout=PIPE, *popenargs, **kwargs)
    output, unused_err = process.communicate()
    retcode = process.poll()
    if retcode:
        cmd = kwargs.get("args")
        if cmd is None:
            cmd = popenargs[0]
        raise CalledProcessError(retcode, cmd, output=output)
    return output

def check_call(*popenargs, **kwargs):
    retcode = call(*popenargs, **kwargs)
    if retcode:
        cmd = kwargs.get("args")
        if cmd is None:
            cmd = popenargs[0]
        raise CalledProcessError(retcode, cmd)
    return 0

def listdir(d):
    for f in os.listdir(d):
        yield os.path.join(d, f)

def rlistdir(d):
    for root, files, dirs in os.walk(d):
        for f in files:
            yield os.path.join(root, f)

def mkdir_p(d):
    try:
        os.makedirs(d)
    except OSError, e:
        if e.errno != 17:
            raise

def rm_f(f, rm=os.remove):
    if not os.path.lexists(f):
        return
    try:
        rm(f)
    except (IOError, OSError), e:
        log.warn("failed to remove %s: %s", f, str(e))

def rm_rf(d):
    if os.path.isdir(d):
        rm_f(d, rm=rmtree)
    else:
        rm_f(d)

def kernelver(filename):
    '''read the version number out of a vmlinuz file.'''
    # this algorithm came from /usr/share/magic
    f = open(filename)
    try:
        f.seek(514)
        if f.read(4) != 'HdrS':
            return None
        f.seek(526)
        (offset,) = struct.unpack("<H", f.read(2))
        f.seek(offset+0x200)
        buf = f.read(256)
    finally:
        f.close()
    uname, rest = buf.split('\0', 1)
    version, rest = uname.split(' ', 1)
    return version

def df(mnt, reserved=False):
    s = os.statvfs(mnt)
    if reserved:
        free = s.f_bfree
    else:
        free = s.f_bavail
    return s.f_bsize * free

def hrsize(size, si=False, use_ib=False):
    powers = 'KMGTPEZY'
    if si:
        multiple = 1000
    else:
        multiple = 1024
    if si:       suffix = 'B'
    elif use_ib: suffix = 'iB'
    else:        suffix = ''
    size = float(size)
    for p in powers:
        size /= multiple
        if size < multiple:
            if p in 'KM': # don't bother with sub-MB precision
                return "%u%s%s" % (int(size)+1, p, suffix)
            else:
                return "%.1f%s%s" % (size, p, suffix)
