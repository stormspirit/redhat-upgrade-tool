# commandline.py - commandline parsing functions
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

import os, optparse, platform, sys
from copy import copy

from rhelup import media
from rhelup.sysprep import reset_boot, remove_boot, remove_cache, misc_cleanup
from rhelup import _
from rhelup import pkgname

import logging
log = logging.getLogger(pkgname)

def parse_args(gui=False):
    p = optparse.OptionParser(option_class=Option,
        description=_('Prepare system for upgrade.'),
        # Translators: This is the CLI's "usage:" string
        usage=_('%(prog)s <SOURCE> [options]' % {'prog': os.path.basename(sys.argv[0])}),
    )

    # === basic options ===
    p.add_option('-v', '--verbose', action='store_const', dest='loglevel',
        const=logging.INFO, help=_('print more info'))
    p.add_option('-d', '--debug', action='store_const', dest='loglevel',
        const=logging.DEBUG, help=_('print lots of debugging info'))
    p.set_defaults(loglevel=logging.WARNING)

    p.add_option('--debuglog', default='/var/log/%s.log' % pkgname,
        help=_('write lots of debugging output to the given file'))

    p.add_option('--reboot', action='store_true', default=False,
        help=_('automatically reboot to start the upgrade when ready'))


    # === hidden options. FOR DEBUGGING ONLY. ===
    p.add_option('--skippkgs', action='store_true', default=False,
        help=optparse.SUPPRESS_HELP)
    p.add_option('--skipkernel', action='store_true', default=False,
        help=optparse.SUPPRESS_HELP)
    p.add_option('--skipbootloader', action='store_true', default=False,
        help=optparse.SUPPRESS_HELP)
    p.add_option('-C', '--cacheonly', action='store_true', default=False,
        help=optparse.SUPPRESS_HELP)


    # === yum options ===
    yumopts = p.add_option_group(_('yum options'))
    yumopts.add_option('--enableplugin', metavar='PLUGIN',
        action='append', dest='enable_plugins', default=[],
        help=_('enable yum plugins by name'))
    yumopts.add_option('--disableplugin', metavar='PLUGIN',
        action='append', dest='disable_plugins', default=[],
        help=_('disable yum plugins by name'))
    yumopts.add_option('--nogpgcheck', action='store_true', default=False,
        help=_('disable GPG signature checking'))


    # === <SOURCE> options ===
    req = p.add_option_group(_('options for <SOURCE>'),
                               _('Location to search for upgrade data.'))
    req.add_option('--device', metavar='DEV',
        type="device_or_mnt",
        help=_('device or mountpoint. default: check mounted devices'))
    req.add_option('--iso', type="isofile",
        help=_('installation image file'))
    # Translators: This is for '--network [VERSION]' in --help output
    req.add_option('--network', metavar=_('VERSION'), type="VERSION",
        help=_('online repos matching VERSION (a number or "rawhide")'))


    # === options for --network ===
    net = p.add_option_group(_('additional options for --network'))
    net.add_option('--enablerepo', metavar='REPOID', action='callback', callback=repoaction,
        dest='repos', type=str, help=_('enable one or more repos (wildcards allowed)'))
    net.add_option('--disablerepo', metavar='REPOID', action='callback', callback=repoaction,
        dest='repos', type=str, help=_('disable one or more repos (wildcards allowed)'))
    net.add_option('--repourl', metavar='REPOID=URL', action='callback', callback=repoaction,
        dest='repos', type=str, help=optparse.SUPPRESS_HELP)
    net.add_option('--addrepo', metavar='REPOID=[@]URL',
        action='callback', callback=repoaction, dest='repos', type=str,
        help=_('add the repo at URL (@URL for mirrorlist)'))
    net.add_option('--instrepo', metavar='REPOID', type=str,
        help=_('get upgrader boot images from REPOID (default: auto)'))
    p.set_defaults(repos=[])

    if not gui:
        clean = p.add_option_group(_('cleanup commands'))

        clean.add_option('--resetbootloader', action='store_const',
            dest='clean', const='bootloader', default=None,
            help=_('remove any modifications made to bootloader'))
        clean.add_option('--clean', action='store_const', const='all',
            help=_('clean up everything written by %s') % pkgname)
        p.add_option('--expire-cache', action='store_true', default=False,
            help=optparse.SUPPRESS_HELP)
        p.add_option('--clean-metadata', action='store_true', default=False,
            help=optparse.SUPPRESS_HELP)

    args, _leftover = p.parse_args()

    if not (gui or args.network or args.device or args.iso or args.clean):
        p.error(_('SOURCE is required (--network, --device, --iso)'))

    # allow --instrepo URL as shorthand for --repourl REPO=URL --instrepo REPO
    if args.instrepo and '://' in args.instrepo:
        args.repos.append(('add', 'cmdline-instrepo=%s' % args.instrepo))
        args.instrepo = 'cmdline-instrepo'

    if not gui:
        if args.clean:
            args.resetbootloader = True

    return args

def repoaction(option, opt_str, value, parser, *args, **kwargs):
    '''Hold a list of repo actions so we can apply them in the order given.'''
    action = ''
    if opt_str.startswith('--enable'):
        action = 'enable'
    elif opt_str.startswith('--disable'):
        action = 'disable'
    elif opt_str.startswith('--repo') or opt_str.startswith('--addrepo'):
        action = 'add'
    parser.values.repos.append((action, value))

# check the argument to '--device' to see if it refers to install media
def device_or_mnt(option, opt, value):
    # Handle the default for --device=''
    if not value:
        value = 'auto'

    if value == 'auto':
        media = media.find()
    else:
        media = [m for m in media.find() if arg in (m.dev, m.mnt)]

    if len(media) == 1:
        return media.pop()

    if not media:
        msg = _("no install media found - please mount install media first")
        if value != 'auto':
            msg = "%s: %s" % (value, msg)
    else:
        devs = ", ".join(m.dev for m in media)
        msg = _("multiple devices found. please choose one of (%s)") % devs
    raise optparse.OptionValueError(msg)

# check the argument to '--iso' to make sure it's somewhere we can use it
def isofile(option, opt, value):
    if not os.path.exists(value):
        raise optparse.OptionValueError(_("File not found: %s") % value)
    if not os.path.isfile(value):
        raise optparse.OptionValueError(_("Not a regular file: %s") % value)
    if not media.isiso(value):
        raise optparse.OptionValueError(_("Not an ISO 9660 image: %s") % value)
    if any(value.startswith(d.mnt) for d in media.removable()):
        raise optparse.OptionValueError(_("ISO image on removable media\n"
            "Sorry, but this isn't supported yet.\n"
            "Copy the image to your hard drive or burn it to a disk."))
    return value

def VERSION(option, opt, value):
    if value.lower() == 'rawhide':
        return 'rawhide'

    distro, version, id = platform.linux_distribution()
    version = float(version)

    if float(value) >= version:
        return value
    else:
        msg = _("version must be greater than %i") % version
        raise optparse.OptionValueError(msg)

class Option(optparse.Option):
    TYPES = optparse.Option.TYPES + ("device_or_mnt", "isofile", "VERSION")
    TYPE_CHECKER = copy(optparse.Option.TYPE_CHECKER)

    TYPE_CHECKER["device_or_mnt"] = device_or_mnt
    TYPE_CHECKER["isofile"] = isofile
    TYPE_CHECKER["VERSION"] = VERSION

def do_cleanup(args):
    if not args.skipbootloader:
        print "resetting bootloader config"
        reset_boot()
    if args.clean == 'bootloader':
        return
    if not args.skipkernel:
        print "removing boot images"
        remove_boot()
    if not args.skippkgs:
        print "removing downloaded packages"
        remove_cache()
    print "removing miscellaneous files"
    misc_cleanup()

def device_setup(args):
    # treat --device like --repo REPO=file://$MOUNTPOINT
    if args.device:
        args.repos.append(('add', 'upgradedevice=file://%s' % args.device.mnt))
        args.instrepo = 'upgradedevice'
    elif args.iso:
        try:
            args.device = media.loopmount(args.iso)
        except media.CalledProcessError, e:
            log.info("mount failure: %s", e.output)
            message('--iso: '+_('Unable to open %s') % args.iso)
            raise SystemExit(2)
        else:
            args.repos.append(('add', 'upgradeiso=file://%s' % args.device.mnt))
            args.instrepo = 'upgradeiso'