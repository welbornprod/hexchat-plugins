#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""xgoogler.py

    Adds a /google command to open a google search.
    -Christopher Welborn
"""

__module_name__ = 'xgoogler'
__module_version__ = '0.1.1'
__module_description__ = 'Adds a /google command to xchat.'

import commands
from os import system as ossystem
from os import path as ospath
from urllib import quote as urlquote

try:
    import hexchat as xchat
    xchat.EAT_XCHAT = xchat.EAT_HEXCHAT
except ImportError:
    try:
        import xchat
    except ImportError:
        print('Can\'t find xchat or hexchat.')
        exit(1)


def get_browser_command():
    """ Retrieves first command found that will open the default browser. """

    # Names of openers in try-first order
    openernames = ('xdg-open', 'kfmclient', 'gnome-open', 'gvfs-open')
    # Extra info for openers (if any is needed)
    openers = {'xdg-open': {'args': None},
               'kfmclient': {'args': 'exec'},
               'gnome-open': {'args': None},
               'gvfs-open': {'args': None}}

    openerloc = ''
    goodopener = None
    for opener in openernames:
        sout = commands.getoutput('which {}'.format(opener))
        if sout:
            openerloc = sout
            goodopener = opener
            break
    
    if ospath.isfile(openerloc) or ospath.islink(openerloc):
        args = openers[goodopener]['args']
        if args:
            # opener requires args
            return ' '.join([openerloc, args])
        else:
            return openerloc
    else:
        return None


def open_site(site, debug=False):
    """ Opens a site using the default system browser """

    openercmd = get_browser_command()
    if openercmd:
        fullcmd = ' '.join([openercmd, '"{}"'.format(site)])
        if debug:
            print('Found browser opener: {}'.format(openercmd))
            print('Running: {}'.format(fullcmd))
        retcode = ossystem(fullcmd)
        if retcode:
            # opener errored
            print('Error opening site: {}'.format(fullcmd))
        return retcode
    else:
        print('No valid command found to open that site: {}'.format(site))
        return 1


def cmd_google(word, word_eol, userdata=False):
    """ /GOOGLE Command Handler: userdata is debug."""
    debug = False
    for debugarg in ('-d', '--debug'):
        if debugarg in word:
            word.remove(debugarg)
            debug = True

    try:
        if len(word) < 2:
            print(help_str)
            return None
            
        userquery = '+'.join([urlquote(s) for s in word[1:]])
        site = 'https://www.google.com/search?q=%s' % (userquery)
        if debug:
            print('Opening site: {}'.format(site))
        nonzero = open_site(site, debug=debug)
        if nonzero:
            print('Unable to google.')
        else:
            if debug:
                print('\nGoogled {}'.format(site))
        return None
    except Exception as ex:
        print('Error during that google:\n{}'.format(ex))
        return None


# START OF SCRIPT
help_str = '\n'.join([
    'Usage: /GOOGLE <SearchQuery> [-d]',
    '\nOptions:',
    '    -d,--debug  : Print extra debugging info.\n',
])
xchat.hook_command('GOOGLE', cmd_google, userdata=False,
                   help=help_str)


print('{}xgoogler v. {} loaded.'.format('02', __module_version__))
