#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""xtools.py

    Various tools to use with xchat,
    hexchat also works  (as long as the API stays compatible).
    This includes /commands that provide specific functionality
    not normally found in xchat/hexchat/irc, or /commands that enhance the
    irc experience.

    This script is now over 2000+ lines, and I really wish it weren't so.
    It's time to shut this little project down before it requires a
    RAM upgrade. I really wanted this to be a single script project, but
    things like command help, and non-xchat functions really need
    their own home.

    -Christopher Welborn
    Version: 0.3.6
        More encoding errors,
    Version: 0.3.5-4
        Fixed encoding errors when printing unicode.
"""
from __future__ import print_function
from code import InteractiveInterpreter
from collections import deque
from datetime import datetime
import os
import re
import sys
from threading import Thread
# XChat style version info.
__module_name__ = 'xtools'
__module_version__ = '0.3.8'
__module_description__ = 'Various commands for extending HexChat or XChat...'
# Convenience version str for help commands.
VERSIONSTR = '{} v. {}'.format(__module_name__, __module_version__)

try:
    import hexchat as xchat
    xchat.EAT_XCHAT = xchat.EAT_HEXCHAT
    CHATDIR = os.path.expanduser('~/.config/hexchat')
except ImportError:
    try:
        import xchat
        CHATDIR = os.path.expanduser('~/.xchat2')
    except ImportError:
        print('Can\'t find xchat or hexchat.')
        sys.exit(1)


class XToolsConfig(object):

    """ Class for global configuration and session-settings container """

    def __init__(self):
        self.xchat_dir = CHATDIR
        # Default config file.
        if os.path.isdir(self.xchat_dir):
            self.config_file = os.path.join(self.xchat_dir, 'xtools.conf')
        else:
            self.config_file = os.path.join(os.getcwd(), 'xtools.conf')

        # Titles for extra tabs.
        self.xtools_tab_title = '[xtools]'
        self.msgs_tab_title = '[caught-msgs]'

        # Default settings. (prefs file overrides these)
        self.settings = {'redirect_msgs': False, 'enable_utf8': True}

        # Ignored nicks (loaded from prefs if available)
        # contains nicks as keys, {'index': 0, 'pattern': repattern} as values
        self.ignored_nicks = {}
        self.max_ignored_msgs = 250
        self.ignored_msgs = deque(maxlen=self.max_ignored_msgs)

        # Msg catchers (regex/text to catch and save msgs)
        self.msg_catchers = {}
        self.max_caught_msgs = 250
        self.caught_msgs = {}
        self.msg_filters = {'nicks': {}, 'filters': {}}
        # When redirected, these are updated to be the latest maximum needed.
        self.format_settings = {'chanspace': 7, 'nickspace': 3}
# Global settings/containers
xtools = XToolsConfig()


class StdOutCatcher(object):

    """ Context that catches stdout for code inside the 'with' block.
        This only catches sys.stdout, otherwise you can use:
            contextlib.redirect_stdout(fileobj)


        Usage:
            with StdOutCatcher(safe=True, maxlength=160) as fakestdout:
                # stdout is stored in fakestdout.output
                print('okay')
            # stdout is back to normal
            # retrieve the captured output..
            print('output was: {}'.format(fakestdout.output))
    """

    def __init__(self, safe=True, maxlength=160):
        # Use safe_output?
        self.safe = safe
        # Maximum length before trimming output
        self.maxlength = maxlength
        # Output
        self.outlines = []
        self.output = ''

    def __enter__(self):
        # Replace stdout with self, stdout.write() will be self.write()
        self.oldstdout = sys.stdout
        sys.stdout = self
        return self

    def __exit__(self, type, value, traceback):
        # Fix stdout.
        sys.stdout = self.oldstdout

    def safe_output(self, s):
        """ Make output safe for chat (no newlines, length trimmed) """

        s = s.replace('\n', '\\n')
        if (self.maxlength > 0) and (len(s) > self.maxlength):
            s = '{} (..truncated)'.format(s[:self.maxlength])
        return s

    def write(self, s):
        s = s.strip('\n')
        if s:
            # Use chat-safe output.
            if self.safe:
                s = self.safe_output(s)
            # Save output
            self.outlines.append(s)
            self.output = '\\n'.join(self.outlines)


class StdErrCatcher(StdOutCatcher):

    """ Same as StdOutCatcher, but works with stderr instead.
        This only catches sys.stderr, otherwise you can use:
            contextlib.redirect_stderr(fileobj)
    """

    def __enter__(self):
        self.oldstderr = sys.stderr
        sys.stderr = self
        return self

    def __exit__(self, type, value, traceback):
        sys.stderr = self.oldstderr


class TabWaiter(object):

    """ Waits for a user-defined amount of time for
        a certain tab to become focused.
        Use with caution!
    """

    def __init__(self, tabtitle=None, timeout=5, focus=True):
        self.tabtitle = tabtitle if tabtitle else xtools.xtools_tab_title
        self.timeout = timeout
        self.focus = focus
        self._context = None

    def _check_tab(self):
        """ This must run in a seperate thread, or xchat will lock up. """
        foundtab = xchat.find_context(channel=self.tabtitle)
        while not foundtab:
            foundtab = xchat.find_context(channel=self.tabtitle)
        # set result.
        self._context = foundtab

    def ensure_tab(self):
        """ ensure that this tab is opened.
            times out after self.timeout seconds.
            returns the tab's context on success, or None on timeout.
        """
        tabcontext = xchat.find_context(channel=self.tabtitle)
        if tabcontext:
            # tab already opened
            return tabcontext
        # open and wait for tab.
        self.open_tab()
        return self.wait_for_tab()

    def open_tab(self):
        if self.focus:
            xchat.command('QUERY {}'.format(self.tabtitle))
        else:
            xchat.command('QUERY -nofocus {}'.format(self.tabtitle))

    def wait_for_tab(self):
        finder = Thread(target=self._check_tab, name='TabWaiter')
        finder.start()
        finder.join(timeout=self.timeout)
        return self._context


def add_catcher(catcherstr):
    """ Add a catcher to the catchers list. """

    msg_catchers = []
    # regex to grab quoted spaces.
    quotepat = re.compile('(["][^"]+["])|([\'][^\']+[\'])')
    quoted = quotepat.findall(catcherstr)
    if quoted:
        # gather quoted strings, and left overs.
        catchers = []
        for grp1, grp2 in quoted:
            if grp1:
                catchers.append(grp1.strip('"'))
                catcherstr = catcherstr.replace(grp1, '')
            if grp2:
                catchers.append(grp2.strip("'"))
                catcherstr = catcherstr.replace(grp2, '')

        # look for leftovers
        nonquoted = [s.strip() for s in catcherstr.split() if s]
        if nonquoted:
            catchers.extend(nonquoted)
    else:
        # This will accept several catchers separated by spaces.
        catchers = catcherstr.split()

    for msg in catchers:
        if msg in xtools.msg_catchers.keys():
            # Skip nick already on the list.
            print_status('{} is already caught.'.format(msg))
            continue
        repat, reerr = compile_re(msg)
        if not repat:
            # Skip bad regex.
            print_error(('Invalid regex pattern for that catcher: '
                         '{}'.format(msg)),
                        boldtext=msg,
                        exc=reerr)
            continue
        xtools.msg_catchers[msg] = {'index': len(xtools.msg_catchers),
                                    'pattern': repat,
                                    }

        msg_catchers.append(msg)

    # Fix indexes so they are sorted.
    build_catcher_indexes()
    if msg_catchers and save_catchers() and save_prefs():
        return msg_catchers
    # Failure saving.
    print_error('Unable to save catchers...')
    return []


def add_caught_msg(msginfo):
    """ add a message to the caught-msgs dict, if it doesn't exist. """
    # Run filters to see if this message is worthy of being caught.
    if is_filtered_msg(msginfo):
        return False
    # Caught messages need to have a unique id for each caught msg,
    # or else it will cause double msgs, or recursion in some cases.
    # hince the need for add_caught_msg(), which generates and checks
    # duplicate msg ids.

    msgid = generate_msg_id(msginfo)
    existingmsg = xtools.caught_msgs.get(msgid, None)
    if existingmsg:
        return False

    # This would be really slow, if the msg len has exceeded the max and
    # a lot of msgs are being added.
    if len(xtools.caught_msgs) >= xtools.max_caught_msgs:
        # pop the first item from caught msgs.
        firstkey = list(sorted(
            xtools.caught_msgs.keys(),
            key=lambda msgid: xtools.caught_msgs[msgid]['time'])
        )[0]
        xtools.caught_msgs.pop(firstkey)
    xtools.caught_msgs[msgid] = msginfo

    # Print to caught-msgs tab?
    if xtools.settings.get('redirect_msgs', False):
        # Check latest channel/nick lengths. Update spacing for msgs as needed
        # It will eventually max out. Adding a lot of extra space when
        # channels names/nicks may be short looks ugly. So always use the
        # current longest nick/channel as the max.
        chanspace = longest(get_channel_names())
        nickspace = len(remove_mirc_color(msginfo['nick']))
        if chanspace > xtools.format_settings['chanspace']:
            xtools.format_settings['chanspace'] = chanspace
        if nickspace > xtools.format_settings['nickspace']:
            xtools.format_settings['nickspace'] = nickspace
        # Print this saved message as a 'redirected' message.
        print_saved_msg(msginfo,
                        chanspace=xtools.format_settings['chanspace'],
                        nickspace=xtools.format_settings['nickspace'],
                        focus=False,
                        redirect=True)

    return True


def add_filter(filterstr, fornick=False):
    """ Add a filter to the msg_filters config. """

    msg_filters = []
    # regex to grab quoted spaces.
    quotepat = re.compile('(["][^"]+["])|([\'][^\']+[\'])')
    quoted = quotepat.findall(filterstr)
    if quoted:
        # gather quoted strings, and left overs.
        filters = []
        for grp1, grp2 in quoted:
            if grp1:
                filters.append(grp1.strip('"'))
                filterstr = filterstr.replace(grp1, '')
            if grp2:
                filters.append(grp2.strip("'"))
                filterstr = filterstr.replace(grp2, '')

        # look for leftovers
        nonquoted = [s.strip() for s in filterstr.split() if s]
        if nonquoted:
            filters.extend(nonquoted)
    else:
        # This will accept several catchers separated by spaces.
        filters = filterstr.split()

    # Choose msg filter key for msg_filters config.
    filtertype = 'nicks' if fornick else 'filters'

    for msg in filters:
        if msg in xtools.msg_filters[filtertype].keys():
            # Skip nick already on the list.
            print_status('{} is already filtered.'.format(msg))
            continue
        repat, reerr = compile_re(msg)
        if not repat:
            # Skip bad regex.
            print_error(('Invalid regex pattern for that filter: '
                         '{}'.format(msg)),
                        boldtext=msg,
                        exc=reerr)
            continue
        xtools.msg_filters[filtertype][msg] = {
            'index': len(xtools.msg_catchers),
            'pattern': repat,
        }

        msg_filters.append(msg)

    # Fix indexes so they are sorted.
    build_filter_indexes()
    if msg_filters and save_filters() and save_prefs():
        return msg_filters
    # Failure saving.
    print_error('Unable to save filters...')
    return []


def add_ignored_nick(nickstr):
    """ Add a nick to the ignored list. """
    ignored_nicks = []

    if ((nickstr.startswith('"') and nickstr.endswith('"')) or
            (nickstr.endswith("'") and nickstr.endswith("'"))):
        # quoted spaces..
        nicks = nickstr[1:-1]
    else:
        # This will accept several nicks separated by spaces.
        nicks = nickstr.split()

    for nick in nicks:
        if nick in xtools.ignored_nicks.keys():
            # Skip nick already on the list.
            print_status('{} is already ignored.'.format(nick))
            continue
        repat, reerr = compile_re(nick)
        if not repat:
            # Skip bad regex.
            print_error(
                'Invalid regex pattern for that nick: {}'.format(
                    nick),
                boldtext=nick,
                exc=reerr)
            continue
        xtools.ignored_nicks[nick] = {
            'index': len(xtools.ignored_nicks),
            'pattern': repat,
        }

        ignored_nicks.append(nick)

    # Fix indexes so they are sorted.
    build_ignored_indexes()
    if ignored_nicks and save_ignored_nicks() and save_prefs():

        return ignored_nicks
    # Failure saving.
    return []


def add_message(addfunc, nick, msgtext, **kwargs):
    """ Uses the given 'add function' to add a filtered/saved msg.
        This builds a universal message format that should be used
        anywhere a message is saved.
        ex:
            add_message(xtools.ignored_msgs.append, 'user1', 'my message')
            # or
            add_message(add_caught_msg, 'user2', 'my msg')
            .. will use xtools.ignored_msgs.append, or add_caught_msg
               to save the message.
        The addfunc function has to receive a single argument,
        which is a msg in the universal format.

        Arguments:
            addfunc     : Function that will deal with the msg after building.
            nick        : Nick the message came from.
            msgtext     : Text for the message.
            msgtype     : The XChat/HexChat message type.
                          (Channel Message, etc.)
            matchlist   : [.group()] or .groups() from the regex match.
                          Whichever one isn't empty :)
            filtertype  : Type of filter that caught the message,
                          'nick' or 'message'.
    """
    msgtype = kwargs.get('msgtype', None)
    matchlist = kwargs.get('matchlist', None)
    filtertype = kwargs.get('filtertype', None)

    chan = xchat.get_context().get_info('channel')
    msgtime = datetime.now()
    if msgtype:
        # set message type (channelmessage, channelaction, etc.)
        msgtype = msgtype.lower().replace(' ', '')
    else:
        # no message type set.
        msgtype = ''
    msg = {
        'nick': nick,
        'time': msgtime.time().strftime('%H:%M:%S'),
        'date': msgtime.date().strftime('%m-%d-%Y'),
        'channel': chan,
        'type': msgtype,
        'msg': msgtext,
        'matchlist': matchlist,
        'filtertype': filtertype,
    }
    try:
        addfunc(msg)
        return True
    except Exception as ex:
        if hasattr(addfunc, '__name__'):
            addfuncname = addfunc.__name__
        else:
            addfuncname = repr(addfunc)
        print_error('Error adding saved msg with: {}'.format(addfuncname),
                    exc=ex,
                    boldtext=addfuncname)
        return False


def bool_mode(modestr):
    """ Translates common words to bool values.
        Acceptable values for modestr:
            True  : on, true, yes, y, 1 , +,
                    (any number returning True for bool(int(number))
            False : off, false, no, n, 0, -
        Returns True/False per mode.
    """
    # Try int val first
    try:
        intmode = int(modestr)
        return bool(intmode)
    except (TypeError, ValueError):
        pass
    # Try string val..
    modestr = modestr.lower()
    if modestr in {'on', 'true', 'yes', 'y', '+'}:
        mode = True
    elif modestr in {'off', 'false', 'no', 'n', '-'}:
        mode = False
    else:
        invalidmsg = 'Invalid mode for ON/OFF!: {}'.format(modestr)
        print_error(invalidmsg, boldtext=modestr)
        return xchat.EAT_ALL
    return mode


def build_catcher_indexes():
    """ Builds indexes for msg catchers. """
    for index, msg in enumerate(sorted(xtools.msg_catchers.keys())):
        xtools.msg_catchers[msg]['index'] = index


def build_filter_indexes():
    """ Builds indexes for catcher-filters. """
    for ftype in ('nicks', 'filters'):
        for index, msg in enumerate(sorted(xtools.msg_filters[ftype].keys())):
            xtools.msg_filters[ftype][msg]['index'] = index


def build_ignored_indexes():
    """ Builds indexes for ignored nicks. """
    for index, nick in enumerate(sorted(xtools.ignored_nicks.keys())):
        xtools.ignored_nicks[nick]['index'] = index


def build_color_table():
    """ Builds a dict of {colorname: colorcode} and returns it. """
    start = ''
    boldcode = ''
    underlinecode = ''
    resetcode = ''

    # Codes (index is the color code)
    codes = ['none', 'black', 'darkblue',
             'darkgreen', 'darkred', 'red', 'darkpurple',
             'brown', 'yellow', 'green', 'darkcyan',
             'cyan', 'blue', 'purple', 'darkgrey', 'grey']

    # Build basic table.
    colors = {}
    for i, code in enumerate(codes):
        colors[code] = {'index': i,
                        'code': '{}{}'.format(start, str(i)),
                        }

    # Add style codes.
    # (made up an index for them for now, so color_code(97) will work.)
    colors['bold'] = {'index': 98, 'code': boldcode}
    colors['underline'] = {'index': 97, 'code': underlinecode}
    colors['reset'] = {'index': 99, 'code': resetcode}

    # Add alternate names for codes.
    colors['b'] = colors['bold']
    colors['u'] = colors['underline']
    colors['normal'] = colors['none']
    colors['darkgray'] = colors['darkgrey']
    colors['gray'] = colors['grey']

    return colors


def clear_catchers():
    """ Clears all catchers """

    if not xtools.msg_catchers:
        print_error('The catch-msg list is already empty.')
        return False

    xtools.msg_catchers = {}
    if save_catchers() and save_prefs():
        return True
    return False


def clear_caught_msgs():
    """ Clears all caught msgs. """

    if not xtools.caught_msgs:
        print_error('No messages have been caught.')
        return False

    xtools.caught_msgs = {}
    return True


def clear_filters(fornick=False):
    """ Clears all catcher-filters. """
    filtertype = 'nicks' if fornick else 'filters'
    if not xtools.msg_filters[filtertype]:
        print_error('The catcher-filters are already empty. ')
        return False

    xtools.msg_filters[filtertype] = {}
    if save_filters() and save_prefs():
        return True
    return False


def clear_ignored_nicks():
    """ Clears all ignored nicks. """

    if not xtools.ignored_nicks:
        print_error('The ignore list is already empty.')
        return False

    xtools.ignored_nicks = {}
    if save_ignored_nicks() and save_prefs():
        return True
    return False


def color_code(color):
    """ Returns a color code by name or mIRC number. """

    try:
        code = xtools.colors[color]['code']
    except KeyError:
        # Try number.
        try:
            codeval = int(color)
            start = ''
            code = '{}{}'.format(start, str(codeval))
        except (TypeError, ValueError):
            code = None

    if code:
        return code
    else:
        # Can't find that color! this is the coders fault :(
        print_error('Script error: Invalid color for color_code: '
                    '{}'.format(str(color)),
                    boldtext=str(color))
        return xtools.colors['reset']['code']


def colormulti(color=None, words=None, bold=False, underline=False):
    """ Same as colorstr, but it accepts a list of strings,
        and returns a list of colorized strings.
    """

    return [colorstr(color=color, text=s, bold=bold, underline=underline)
            for s in words]


def colorstr(color=None, text=None, bold=False, underline=False):
    """ return a color coded word.
        the text argument is automatically str() wrapped,
        so colorstr('red', len(list)) is fine.
        Keyword Arguments:
            color      : Named color, or mIRC color number.
            text       : Text to be colored.
            bold       : Boolean,  whether text is bold or not.
            underline  : Boolean. whether text is underlined or not.
    """

    # normal color code
    boldcode = ''
    underlinecode = ''
    normal = ''
    code = color_code(color)
    # initial text items (basic coloring)
    strcodes = [code, str(text)]
    # Handle extra formatting (bold, underline)
    if underline:
        strcodes.insert(0, underlinecode)
    if bold:
        strcodes.insert(0, boldcode)

    return '{}{}'.format(''.join(strcodes), normal)


def compile_re(restr):
    """ Try compiling a regex, returns (repat, exception)
        so it fails, it returns (None, exception)
        if it succeeds, it returns (repat, None)
    """
    try:
        compiled = re.compile(restr)
    except Exception as ex:
        return False, ex
    else:
        return compiled, None


def filter_caught_msgs(filtertxt, fornick=False):
    """ Filter/remove caught msgs that contain filtertxt,
        add this as a new filter.

        filtertxt is compiled to a regex pattern.
        Returns None on empty msgs or bad regex.
        Returns filtered count otherwise.
    """

    if not xtools.caught_msgs:
        print_error('No messages have been caught.')
        return None

    try:
        repat = re.compile(filtertxt)
    except Exception as ex:
        print_error('Invalid pattern for filter: {}'.format(filtertxt),
                    exc=ex, boldtext=filtertxt)
        return None

    filtercnt = 0

    def matchtext(k):
        return repat.search(xtools.caught_msgs[k]['msg'])

    if fornick:
        def matchnick(k):
            return repat.search(xtools.caught_msgs[k]['nick'])

        def isfiltered(k):
            return matchtext(k) or matchnick(k)
    else:
        def isfiltered(k):
            return matchtext(k)

    filtered = filter(isfiltered, xtools.caught_msgs)
    for msgid in filtered:
        xtools.caught_msgs.pop(msgid)
        add_filter(filtertxt, fornick=fornick)
        filtercnt += 1
    return filtercnt


def generate_msg_id(msginfo):
    """ Generate a unique msg id for caught msgs. """

    chan = xchat.strip(msginfo['channel'])
    nick = xchat.strip(msginfo['nick'])
    msg = xchat.strip(msginfo['msg'])

    return hash('{}{}{}'.format(chan, nick, msg))


def get_all_users(channels=None):
    """ Retrieve a list of all users (no dupes) """

    if not channels:
        channels = xchat.get_list('channels')
    usernames = []
    allusers = []
    for context in [c.context for c in channels]:
        if context:
            users = context.get_list('users')
            for user in users:
                if user.nick not in usernames:
                    allusers.append(user)
                    usernames.append(user.nick)
    return allusers


def get_channel_attrs(attr=None):
    """ Retrieve a channel attribute from all channels.
        ex:
            contexts = get_channel_attrs(attr='context')
    """

    try:
        return [getattr(c, attr) for c in xchat.get_list('channels')]
    except Exception as ex:
        print_error('Error retrieving channel attribute: '
                    '{}'.format(str(attr)),
                    exc=ex,
                    boldtext=str(attr))
        return []


def get_channel_names():
    """ Retrieve all channel names. """

    return [c.channel for c in xchat.get_list('channels')]


def get_channels_users(channels=None):
    """ Return a dict with {channel: [userlist] """
    if not channels:
        channels = xchat.get_list('channels')
    channelusers = {}
    for channel in channels:
        if channel.context:
            users = channel.context.get_list('users')
            channelusers[channel.channel] = users

    return channelusers


def get_cmd_args(word_eol, arglist):
    """ Combination of get_cmd_restm and get_flag_args.
        Returns commandname, nonflagdata, argdict
        Example:
            word = '/TEST this stuff -d'
            cmdname, cmdargs, argd = get_cmd_args(word_eol, ('-d', '--debug'))
            # returns:
            #   cmdname == '/TEST'
            #   cmdargs == 'this stuff'
            #      argd == {'--debug': True}
    """
    # Make my own 'word', because the py-plugin removes extra spaces in word.
    word = word_eol[0].split(' ')
    cmdname = word[0]
    word, argd = get_flag_args(word, arglist)
    cmdargs = get_cmd_rest(word)
    return cmdname, cmdargs, argd


def get_cmd_rest(word):
    """ Return the rest of a command. (removing /COMMAND) """
    if word and (len(word) > 1):
        return ' '.join(word[1:])
    # no args, only the cmdname.
    return ''


def get_eval_comment(s):
    """ Retrieve comment from single line of code.
        Return the comment text if any, otherwise return None.
    """
    if not s:
        return None

    quotedpat = re.compile('[\'"](.+)?#(.+?)[\'"]')
    # remove quoted # characters.
    parsed = quotedpat.sub('', s)
    # Still has comment char.
    if '#' in parsed:
        return parsed[parsed.index('#') + 1:]
    else:
        return None


def get_flag_args(word, arglist):  # noqa
    """ Retrieves flag args from a command,
        returns a tuple with:
            (cleaned_word, {'--longopt': True/False, ...})
            ...where clean_word has all args removed,
            ...and the dict has long options with True/False value.

        expects:
            word    : from cmd_ word list.
            arglist : list of tuples with [('-s', '--long', False), ...]
                      ('shortoption', 'longoption', default_value)
                      ...default_value is optional and defaults to False.

        Example:
            word = '/cmd -a This is extra stuff.'.split()
            word, argd = get_flag_args(word, [('-a', '--all', False),
                                              ('-c', '--count', True),
                                              ('-d', '--debug', False)])

            Results in:
                word == '/cmd This is extra stuff.'
                argd == {'--all': True,    # the -a flag was used
                         '--count': True,  # it's default is True
                         '--debug': False, # no -d flag was given.
                         }
                * Notice the /cmd is kept, it is useful for certain commands.
                * get_cmd_rest(word) can remove it and return extra stuff
                  only.
    """

    def safe_remove(lst, items):
        """ Safely removes list of items from a lst. """
        for i in items:
            try:
                lst.remove(i)
            except ValueError:
                # Item was not in the list.
                pass

    # Build default arg info.
    builtarglist = []
    arginfo = {}
    for argset in arglist:
        if len(argset) < 3:
            shortopt, longopt = argset
            arginfo[longopt] = False
        elif len(argset) == 3:
            shortopt, longopt, default = argset
            arginfo[longopt] = default
        else:
            print_safe(
                '\nInvalid arglist for get_flag_args!: {}'.format(
                    repr(argset)))
            return {}
        # Add the proper arg info, for parsing.
        builtarglist.append((shortopt, longopt))

    # Parse args, remove them from word as we go.
    newword = [c for c in word]
    for shortarg, longarg in builtarglist:
        if (shortarg in word) or (longarg in word):
            # Remove both short and long options from word.
            safe_remove(newword, [shortarg, longarg])
            # Flag was found, set it.
            arginfo[longarg] = True

    while newword and (newword[0] == ''):
        newword.pop(0)
    while newword and (newword[-1] == ''):
        newword.pop(len(newword) - 1)

    # Return cleaned word, and arg dict.
    return newword, arginfo


def get_pref(opt):
    """ Retrieve a preference from settings.
        Returns None if it's not available.
    """

    if opt in xtools.settings.keys():
        return xtools.settings[opt]
    return None


def get_window(tabtitle, focus=True):
    """ Open a tab, and wait for it to be available.
        Returns the tab's context (unless it times out, then None)
    """

    tabwaiter = TabWaiter(tabtitle=tabtitle, focus=focus)
    xchatwin = tabwaiter.ensure_tab()
    return xchatwin


def get_xtools_window(focus=True):
    """ Open the xtools tab, and wait for it to be focused.
        Returns the xtools-tab context (unless it times out, then None)
    """

    tabwaiter = TabWaiter(tabtitle=xtools.xtools_tab_title, focus=focus)
    xchatwin = tabwaiter.ensure_tab()
    return xchatwin


def indentlines(s, padding=8, maxlength=40):
    """ Turns a single line of text into an indented block.
        The first line (within maxlength) isn't touched. Any line
        after that is indented to 'padding' length.
        Returns a list of lines.
    """
    lines = []
    currentline = []
    words = s.split()
    for i, word in enumerate(words):
        currentlinestr = ' '.join(currentline)
        if len(currentlinestr) < (maxlength - len(word) + 1):
            currentline.append(word)
        else:
            lines.append(currentlinestr)
            currentline = [word]

    # Append the last line we built.
    if currentline:
        lines.append(' '.join(currentline))

    if lines:
        spc = ' ' * padding
        return [
            '{}{}'.format(spc, l) if i else l for i, l in enumerate(lines)
        ]
    # No lines were built.
    return [s]


def is_filtered_msg(msginfo):
    """ Return True if the msg filters catch this message. """
    nick = remove_mirc_color(msginfo['nick'])
    for ftxt, nickfilter in xtools.msg_filters['nicks'].items():
        if nickfilter['pattern'].search(nick):
            return True

    for ftxt, msgfilter in xtools.msg_filters['filters'].items():
        if msgfilter['pattern'].search(msginfo['msg']):
            return True
    # Passed
    return False


def load_catchers():
    """ Loads msg-catchers from preferences. """

    catcher_str = get_pref('msg_catchers')
    if catcher_str:
        catchers = [s.strip() for s in catcher_str.split('{|}')]
    else:
        catchers = []

    # Validate nicks.
    valid = {}
    for msg in catchers:
        repat, reerr = compile_re(msg)
        if reerr:
            print_error('Invalid regex pattern for msg-catcher in config: '
                        '{}'.format(msg),
                        boldtext=msg,
                        exc=reerr)
            continue
        # Have good nick pattern, add it.
        valid[msg] = {'index': len(valid), 'pattern': repat}

    # Save to global.
    xtools.msg_catchers.update(valid)
    # Rebuild indexes
    build_catcher_indexes()
    return True


def load_filters():
    """ Loads catcher-filters from preferences. """
    filtertypes = (
        ('nicks', 'msg_filter_nicks'),
        ('filters', 'msg_filters'),
    )
    for filtertype, configopt in filtertypes:
        filter_str = get_pref(configopt)
        if filter_str:
            filters = [s.strip() for s in filter_str.split('{|}')]
        else:
            filters = []

        # Validate nicks.
        valid = {}
        for msg in filters:
            repat, reerr = compile_re(msg)
            if reerr:
                print_error(('Invalid regex pattern for {} '
                             'in config: {}').format(configopt, msg),
                            boldtext=msg,
                            exc=reerr)
                continue
            # Have good nick pattern, add it.
            valid[msg] = {'index': len(valid), 'pattern': repat}

        # Save to global.
        xtools.msg_filters[filtertype].update(valid)

    # Rebuild indexes
    build_filter_indexes()
    return True


def load_ignored_nicks():
    """ Loads ignored nicks from preferences. """

    ignored_str = get_pref('ignored_nicks')
    if ignored_str:
        if ',' in ignored_str:
            ignored = [s.strip() for s in ignored_str.split(',')]
        else:
            ignored = [ignored_str.strip()]
    else:
        ignored = []

    # Validate nicks.
    valid = {}
    for nick in ignored:
        repat, reerr = compile_re(nick)
        if reerr:
            print_error('Invalid regex pattern for nick in config: '
                        '{}'.format(nick),
                        boldtext=nick,
                        exc=reerr)
            continue
        # Have good nick pattern, add it.
        valid[nick] = {'index': len(valid), 'pattern': repat}

    # Save to global.
    xtools.ignored_nicks.update(valid)
    # Rebuild indexes
    build_ignored_indexes()
    return True


def load_prefs():
    """ Load all preferences (if available). """

    try:
        with open(xtools.config_file, 'r') as fread:
            configlines = fread.readlines()
    except (IOError, OSError) as exio:
        if not os.path.isfile(xtools.config_file):
            return False
        # Actual error, alert the user.
        print_error('Can\'t open config file: {}'.format(xtools.config_file),
                    boldtext=xtools.config_file,
                    exc=exio)
        return False

    # Have config lines.
    for line in configlines:
        line = line.strip()
        if line.startswith('#') or (line.count('=') != 1):
            # Skip comment/bad config line.
            continue
        # Have good config line.
        opt, val = [s.strip() for s in line.split('=')]
        xtools.settings[opt] = val
    return True


def longest(lst):
    return len(max(lst, key=len))


def parse_scrollback_line(line):
    """ Parses info out of a xchat scrollback.txt.
        Returns:
            (datetime, nick, msg)
        Or on failure:
            (None, None, None)
    """
    if not line:
        return None, None, None

    lineparts = line.split()
    try:
        # All valid lines consist of: T <timestamp> Nick> Message
        if not line.startswith('T'):
            return None, None, None

        # Parse timestamp.
        timestamp = ' '.join(lineparts[1:2])
        timedate = datetime.fromtimestamp(float(timestamp))

        # Get Message info.
        nickmsg = ' '.join(lineparts[2:])
        if '>' not in nickmsg:
            return None, None, None
        msgparts = nickmsg.split('>')
        nick = msgparts[0].strip('\n').replace(' ', '')
        text = '>'.join(msgparts[1:])
    except (IndexError, ValueError):
        # This was not a channel msg, it was probably plugin output.
        return None, None, None

    if not nick:
        nick = None
    if not text:
        text = None

    return timedate, nick, text


def print_catchers(newtab=False):
    """ Prints all msg catchers. """

    if not xtools.msg_catchers:
        print_status('No msg catchers have been set.', newtab=newtab)
        return True

    catchlen, caughtlen = colormulti(
        'blue',
        [len(xtools.msg_catchers), len(xtools.caught_msgs)]
    )
    statusmsg = ' '.join((
        'Message Catchers',
        '({} catchers - {} caught msgs):')).format(catchlen, caughtlen)

    print_status(statusmsg, newtab=newtab)

    def msgsortkey(k):
        return xtools.msg_catchers[k]['index']

    for msg in sorted(xtools.msg_catchers.keys(), key=msgsortkey):
        index = xtools.msg_catchers[msg]['index'] + 1
        line = '    {}: {}'.format(colorstr('blue', index, bold=True),
                                   colorstr('blue', msg))
        print_safe(line, newtab=newtab)
    return True


def print_caught_msgs(newtab=False):
    """ Prints all caught messages for this session. """

    if xtools.caught_msgs:
        # Print ignored messages.
        msglen = len(xtools.caught_msgs)
        msglenstr = colorstr('blue', msglen, bold=True)
        msgplural = 'message' if msglen == 1 else 'messages'
        chanspace = longest((xtools.caught_msgs[m]['channel']
                             for m in xtools.caught_msgs))
        nickspace = longest((xtools.caught_msgs[m]['nick']
                             for m in xtools.caught_msgs))

        print_status('You have {} caught {}:\n'.format(msglenstr, msgplural),
                     newtab=newtab)

        def sortkey(k):
            return xtools.caught_msgs[k]['time']

        for msgid in sorted(xtools.caught_msgs, key=sortkey):
            print_saved_msg(xtools.caught_msgs[msgid],
                            chanspace=chanspace,
                            nickspace=nickspace,
                            newtab=newtab)
        return True
    else:
        # print 'no messages' warning.
        catchlen = len(xtools.msg_catchers)
        catchlenstr = colorstr('blue', catchlen)
        catchplural = 'msg-catcher' if catchlen == 1 else 'msg-catchers'
        catcherstr = '({} {} set.)'.format(catchlenstr, catchplural)
        print_status('No messages have been caught. {}'.format(catcherstr),
                     newtab=newtab)
        return False


def print_cmdhelp(cmdname=None, newtab=False):
    """ Prints help for a command based on the name.
        If no cmdname is given, all help is shown.
        For /xtools <cmdname>.
        Returns True on success, False on failure (bad cmdname)
    """

    def formathelp(chelpstr):
        """ Color code help string. """
        helplines = chelpstr.split('\n')
        fmthelp = []
        for line in helplines:
            if ':' in line:
                # Color code 'arg : description'
                helpparts = line.split(':')
                argfmt = colorstr('blue', helpparts[0])
                descfmt = colorstr('darkgrey', helpparts[1])
                line = ':'.join([argfmt, descfmt])
            else:
                # Default color for other lines.
                line = colorstr('darkgrey', line)
            # Add indented help line.
            fmthelp.append('    {}'.format(line))
        return '\n'.join(fmthelp)

    def formatcmd(cname):
        """ Format header and help for a command. """
        header = '\nHelp for {}:'.format(cname)
        helpstr = formathelp(commands[cname]['help'])
        return '{}\n{}\n'.format(header, helpstr)

    if cmdname:
        # Single command
        cmdname = cmdname.lower().strip('/')
        if cmdname in commands.keys():
            helplist = [formatcmd(cmdname)]
        else:
            print_error('No command named {}'.format(cmdname),
                        boldtext=cmdname,
                        newtab=newtab)
            return False
    else:
        # All commands.
        helplist = [formatcmd(cname) for cname in sorted(commands.keys())]

    # Print the list of help lines.
    print_safe(''.join(helplist), newtab=newtab)
    return True


def print_cmddesc(cmdname=None, newtab=False):
    """ Prints the description for a command or all commands. """

    # Calculate space needed for formatting, and make a helper function.
    cmdkeys = sorted(commands.keys())
    longestname = len(max(cmdkeys, key=len))

    def getspacing(cname):
        return (' ' * (longestname - len(cname) + 4))

    def formatdesc(cname, cdesc):
        """ Format a single description with color codes and spacing. """
        return '{}{} : {}'.format(
            getspacing(cname),
            colorstr('blue', cname),
            colorstr('darkgrey', cdesc))

    if cmdname:
        # Single description, name passed from user.
        cmdname = cmdname.lower().strip('/')
        try:
            cmddesc = commands[cmdname]['desc']
            desclist = [formatdesc(cmdname, cmddesc)]
            cmdheader = '\nCommand description for {}:'.format(
                colorstr('blue', cmdname))
            print_safe(cmdheader, newtab=newtab)
        except KeyError:
            print_error(
                'No command named {}'.format(cmdname),
                boldtext=cmdname,
                newtab=newtab)
            return False
    else:
        # All descriptions.
        # Build a list of formatted descriptions for enabled commands.
        desclist = []
        for cname in cmdkeys:
            if commands[cname]['enabled']:
                desclist.append(formatdesc(cname, commands[cname]['desc']))
        print_safe(
            '\nCommand descriptions for {}:'.format(VERSIONSTR),
            newtab=newtab)

    # Print command descriptions.
    print_safe('\n{}\n'.format('\n'.join(desclist)), newtab=newtab)


def print_colordemo():
    """ A test of color_code and therefor build_color_table also... """

    print_xtools('\nTesting colors:\n')
    for cname in sorted(xtools.colors.keys(),
                        key=lambda k: xtools.colors[k]['index']):
        cindex = xtools.colors[cname]['index']
        demotxt = colorstr(color=cname, text='{} : {}'.format(cindex, cname))
        print_xtools(demotxt)
    print_xtools('')


def print_error(msg, exc=None, boldtext=None, newtab=False):
    """ Prints a red formatted error msg.
        Arguments:
            msg       : Normal message to print in red.
            exc       : Exception() object to print (or None)
            boldtext  : Text that should be in Bold (or None)
            newtab    : Print output to xtools tab (default: False)
        Ex:
            print_error('Error in: Main', exc=None, boldtext='Main')
    """

    # Make boldtext bold if it was passed.
    if boldtext:
        # All parts of the message except boldtext.
        msgpart = msg.split(boldtext)
        # Copy of the boldtext, formatted.
        # If it is an integer, special handling is needed.
        try:
            int(boldtext)
            boldfmt = colorstr('red', '({})'.format(boldtext), bold=True)
        except ValueError:
            # normal handling.
            boldfmt = colorstr('red', boldtext, bold=True)
        # Formatted normal message parts.
        msgfmt = (colorstr('red', s) if s else '' for s in msgpart)
        # Final formatted message.
        msg = boldfmt.join(msgfmt)
    else:
        # Normal message.
        msg = '{}\n'.format(colorstr('red', msg))

    # Append xtools so you know where this error is coming from.
    msg = '\n{}{}'.format(colorstr('grey', 'xtools: '), msg)
    # Print formatted message.
    print_safe(msg, newtab=newtab)

    # Print exception.
    if exc:
        print_safe(colorstr('red', '\n{}'.format(exc)), newtab=newtab)


def print_evalresult(cquery, coutput, **kwargs):
    """ Format eval code-output for chat before sending,
        or format for screen output.
        Arguments:
            cquery      : Original code evaled.
            coutput     : Output when code was ran.

        Keyword Arguments:
            chat        : Send to chat?
                          Default: False
            chatnick    : Nick to mention in chat msg.
                          Default: None
            comment     : Comment after the result.
                          Default: None
            newtab      : Send output to new xchat tab?
                          Default: False
            resultonly  : Don't include original code, only the result.
                          Default: False
    """
    chat = kwargs.get('chat', False)
    chatnick = kwargs.get('chatnick', None)
    comment = kwargs.get('comment', None)
    resultonly = kwargs.get('resultonly', False)
    newtab = kwargs.get('newtab', False)

    if chat:
        # Send to channel as user.
        # Wrap it in () to separate it from the result.
        queryfmt = '({})'.format(cquery.replace('\n', '\\n'))

        if resultonly:
            # don't include the query in the msg.
            chanmsg = coutput
        else:
            # include query; == result in the msg.
            chanmsg = '{} == {}'.format(queryfmt, coutput)
        # add directed message nick if given.
        if chatnick:
            chanmsg = '{}: {}'.format(chatnick, chanmsg)
        # add comment to the end of the result.
        if comment:
            chanmsg = '{} # {}'.format(chanmsg, comment)
        # Output.
        print_tochan(chanmsg)
    else:
        # Print to screen.
        # Add comment to the end of the result.
        if comment:
            coutput = '{}\n# {}'.format(coutput, comment)
        # Output.
        print_status('Code Output:', newtab=newtab)
        print_safe(coutput, newtab=newtab)


def print_evalerror(cquery, eoutput, **kwargs):
    """ Format eval error msg for chat before sending,
        or format for printing to screen.
        Arguments:
            cquery      : Original code evaled.
            eoutput     : Output when code was ran.

        Keyword Arguments:
            chat        : Send to chat?
                          Default: False
            chatnick    : Nick to mention in chat msg.
                          Default: None
            comment     : Comment after the result.
                          Default: None
            newtab      : Send output to new xchat tab?
                          Default: False
            resultonly  : Don't include original code, only the result.
                          Default: False
    """
    chat = kwargs.get('chat', False)
    chatnick = kwargs.get('chatnick', None)
    comment = kwargs.get('comment', None)
    resultonly = kwargs.get('resultonly', False)
    newtab = kwargs.get('newtab', False)

    if chat:
        # Format chat msg, so its not too long.
        lastline = eoutput.split('\\n')[-1]
        # send to usual output printer/displayer.
        print_evalresult(cquery,
                         lastline,
                         chat=chat,
                         chatnick=chatnick,
                         comment=comment,
                         resultonly=resultonly,
                         newtab=newtab)
    else:
        # Not a chat send, no trimming is needed.
        errorsfmt = eoutput.replace('\\n', '\n')
        # Add comment to end of output.
        if comment:
            errorsfmt = '{}\n# {}'.format(errorsfmt, comment)
        # Output.
        print_error('Code Error:\n{}'.format(errorsfmt), newtab=newtab)


def print_filters(newtab=False, fornick=False):
    """ Print catcher-filters. """

    filtertype = 'nicks' if fornick else 'filters'
    statustype = 'nick' if fornick else 'message'
    if not xtools.msg_filters[filtertype]:
        print_status('No {}-filters have been set.'.format(statustype),
                     newtab=newtab)
        return True

    filterlen, caughtlen = colormulti('blue',
                                      [len(xtools.msg_filters[filtertype]),
                                       len(xtools.caught_msgs)])

    statusmsg = ''.join(('Catcher-Filters ({}s) '.format(statustype),
                         '({} filters - '.format(filterlen),
                         '{} caught msgs):'.format(caughtlen)))

    print_status(statusmsg, newtab=newtab)

    def msgsortkey(k):
        return xtools.msg_filters[filtertype][k]['index']

    for msg in sorted(xtools.msg_filters[filtertype].keys(), key=msgsortkey):
        index = xtools.msg_filters[filtertype][msg]['index'] + 1
        line = '    {}: {}'.format(colorstr('blue', index, bold=True),
                                   colorstr('blue', msg))
        print_safe(line, newtab=newtab)
    return True


def print_ignored_msgs(newtab=False):
    """ Prints all ignored messages for this session. """

    if not xtools.ignored_msgs:
        print_status('No messages have been ignored.', newtab=newtab)
        return False

    # Print ignored messages.
    msglen = len(xtools.ignored_msgs)
    msglenstr = colorstr('blue', msglen, bold=True)
    msgplural = 'message' if msglen == 1 else 'messages'
    print_status('You have {} ignored {}:\n'.format(msglenstr, msgplural),
                 newtab=newtab)

    chanspace = longest((k['channel'] for k in xtools.ignored_msgs))
    nickspace = longest((k['nick'] for k in xtools.ignored_msgs))
    for msg in sorted(xtools.ignored_msgs, key=lambda k: k['time']):
        print_saved_msg(msg,
                        chanspace=chanspace,
                        nickspace=nickspace,
                        newtab=newtab)
    return True


def print_ignored_nicks(newtab=False):
    """ Prints all ignored nicks. """

    if not xtools.ignored_nicks:
        print_status('No nicks are being ignored.', newtab=newtab)
        return True

    ignorelenstr = str(len(xtools.ignored_nicks))
    msglenstr = str(len(xtools.ignored_msgs))
    statusmsg = ('Ignoring {} nicks ({} ignored msgs):'.format(
        colorstr('blue', ignorelenstr),
        colorstr('blue', msglenstr))
    )
    print_status(statusmsg, newtab=newtab)

    def nicksortkey(k):
        return xtools.ignored_nicks[k]['index']

    for nick in sorted(xtools.ignored_nicks.keys(), key=nicksortkey):
        istr = str(xtools.ignored_nicks[nick]['index'] + 1)
        line = '    {}: {}'.format(
            colorstr('blue', istr, bold=True),
            colorstr('blue', nick))
        print_safe(line, newtab=newtab)
    return True


def print_safe(s, newtab=False, focus=True):
    """ Just a wrapper for print, to ensure it is a function (py 2)
        and help with utf8 encoding.
    """
    if newtab:
        return print_xtools(s, focus=focus)
    if xtools.settings.get('enable_utf8', False):
        print(s.encode('utf-8'))
    else:
        print(s)


def print_saved_msg(msg, chanspace=16, nickspace=16,
                    newtab=False, focus=True, redirect=False):
    """ Print a single saved msg from xtools.ignored_msgs,
        or xtools.caught_msgs.
        Must be the actual msg, not the msg id
        ..from xtools.ignored_msgs, or xtools.caught_msgs[msgid].
    """

    msgtime = '({})'.format(colorstr('grey', msg['time']))
    chan = '[{}]'.format(colorstr('green', msg['channel']))
    # manually get channel spacing, instead of .ljust() including color codes
    chan = '{}{}'.format(chan, (' ' * (chanspace - len(msg['channel']))))
    # strip color from nick, and add our own.
    nick = remove_mirc_color(msg['nick'])
    if 'action' in msg['type']:
        nick = colorstr('darkblue', nick.ljust(nickspace))
        # user action, add a big * on it.
        nick = '{}{}'.format(colorstr('red', '*', bold=True), nick)
    else:
        # normal channel msg
        nick = colorstr('darkblue', nick.ljust(nickspace + 1))

    # Format long messages
    msglabel = '{} {} {}: '.format(msgtime, chan, nick)
    # Figure maximum width for label + msg, and for msg alone.
    # Making the max width of a message shorter than the usual chat window,
    # so maybe it will look good under normal circumstances.
    maxoverall = 130  # 160 if redirect else 130 --> using only 1 width now.
    # Indenting messages by 4.
    # Figure label length for spacing without colors.
    msgspace = len(remove_mirc_color(msglabel))
    maxmsglen = maxoverall - msgspace

    def msglines(s):
        """ Chunk a msg, add space to all but the first line. """
        return indentlines(s, padding=msgspace, maxlength=maxmsglen)

    # Wrap long lines with msglines() if needed, colorize highlighted msgs.
    if 'hilight' in msg['type']:
        # highlighted msg.
        msgtext = '\n'.join(colorstr('red', s) for s in msglines(msg['msg']))
    else:
        # normal msg.
        msgtext = '\n'.join(msglines(msg['msg']))
        # Highlight matching text if available.
        for matchtext in msg['matchlist']:
            colormatch = colorstr(color='red', text=matchtext, bold=True)
            msgtext = re.sub(matchtext, colormatch, msgtext)

    # Build final message.
    msgfmt = '{}{}'.format(msglabel, msgtext)

    # Print it to the correct tab.
    if redirect:
        # This is a redirected msg, print to the xtools-msgs tab.
        print_totab(xtools.msgs_tab_title, msgfmt, focus=False)
    else:
        # This could be an ignored msg, or a caught msg.
        # Whether or not it's printed to the xtools tab is determined
        # by the user with the --tab argument (which sets newtab)
        print_safe(msgfmt, newtab=newtab, focus=focus)


def print_status(msg, newtab=False):
    """ Print an xtools status message. """

    finalmsg = '\n{} {}'.format(colorstr('grey', 'xtools:'), msg)
    print_safe(finalmsg, newtab=newtab)


def print_tochan(msg, channel=None):
    """ Prints a message as the user to a channel.
        If no channel is given, the current channel is used.
    """

    if not msg:
        print_error('No msg to send to channel.')
        return False

    if not channel:
        channel = xchat.get_context().get_info('channel')

    if not channel:
        print_error('No channel to send msg to.')
        return False

    xchat.command('MSG {} {}'.format(channel, msg))


def print_totab(tabtitle, msg, focus=True):
    """ Print to any tab, opens the tab if not available.
        Prints to current tab if opening fails.
    """
    # Find existing xchat tab, or open a new one.
    context = get_window(tabtitle, focus=focus)
    if context is None:
        # Can't find xtools tab (timed out), print to the current tab.
        print_safe(msg)
    else:
        # print to xtools tab.
        context.prnt(msg)


def print_version(newtab=False):
    """ Print xtools version. """

    print_safe(colorstr('blue', VERSIONSTR, bold=True), newtab=newtab)


def print_xtools(s, focus=True):
    """ Print to the [xchat] tab/window """

    # Find existing xchat tab, or open a new one.
    context = get_xtools_window(focus=focus)
    if context is None:
        # Can't find xtools tab (timed out), print to the current tab.
        print_safe(s)
    else:
        # print to xtools tab.
        try:
            context.prnt(s)
        except UnicodeDecodeError as ex:
            print_error(
                'Error printing this string: {!r}'.format(s),
                exc=ex)


def remove_catcher(catcherstr):
    """ Removes a msg-catcher by string. """

    def get_key(kstr):
        if kstr in xtools.msg_catchers.keys():
            return kstr
        else:
            # Try by index.
            try:
                intval = int(kstr)
            except (TypeError, ValueError):
                return None
            for msg in xtools.msg_catchers.keys():
                msgindex = xtools.msg_catchers[msg]['index']
                if msgindex == (intval - 1):
                    return msg

            return None

    removed_catchers = []
    for msg in catcherstr.split():
        msgkey = get_key(msg)
        if msgkey:
            # Good key, remove it.
            xtools.msg_catchers.pop(msgkey)
            removed_catchers.append(msgkey)
        else:
            print_error('Can\'t find that in the msg-catcher list: '
                        '{}'.format(msg),
                        boldtext=msg)
            continue

    # Fix indexes
    build_catcher_indexes()
    # Return status.
    if removed_catchers and save_catchers() and save_prefs():
        return removed_catchers
    else:
        return False


def remove_filter(filterstr, fornick=False):
    """ Removes a catcher-filter by string. """
    filtertype = 'nicks' if fornick else 'filters'

    def get_key(kstr):
        if kstr in xtools.msg_filters[filtertype].keys():
            return kstr
        else:
            # Try by index.
            try:
                intval = int(kstr)
            except (TypeError, ValueError):
                return None
            for msg in xtools.msg_filters[filtertype].keys():
                msgindex = xtools.msg_filters[filtertype][msg]['index']
                if msgindex == (intval - 1):
                    return msg

            return None

    removed_filters = []
    for msg in filterstr.split():
        msgkey = get_key(msg)
        if msgkey:
            # Good key, remove it.
            xtools.msg_filters[filtertype].pop(msgkey)
            removed_filters.append(msgkey)
        else:
            print_error('Can\'t find that in the filter list: '
                        '{}'.format(msg),
                        boldtext=msg)
            continue

    # Fix indexes
    build_filter_indexes()
    # Return status.
    if removed_filters and save_filters() and save_prefs():
        return removed_filters
    else:
        return False


def remove_ignored_nick(nickstr):
    """ Removes an ignored nick by name. """

    def get_key(kstr):
        if kstr in xtools.ignored_nicks.keys():
            return kstr
        else:
            # Try by index.
            try:
                intval = int(kstr)
            except (TypeError, ValueError):
                return None
            for nick in xtools.ignored_nicks.keys():
                nickindex = xtools.ignored_nicks[nick]['index']
                if nickindex == (intval - 1):
                    return nick

            return None

    removed_nicks = []
    for nick in nickstr.split():
        nickkey = get_key(nick)
        if nickkey:
            # Good key, remove it.
            xtools.ignored_nicks.pop(nickkey)
            removed_nicks.append(nickkey)
        else:
            print_error('Can\'t find that in the ignored list: '
                        '{}'.format(nick),
                        boldtext=nick)
            continue

    # Fix indexes
    build_ignored_indexes()
    # Return status.
    if removed_nicks and save_ignored_nicks() and save_prefs():
        return removed_nicks
    else:
        return False


def remove_mirc_color(text):
    """ Removes color code from text
    """
    badchars = ['{}<'.format(chr(8)), chr(8), chr(15)]
    for badchar in badchars:
        if badchar in text:
            text = text.replace(badchar, '')

    text = xchat.strip(text)
    return text


def save_catchers():
    """ Save msg-catchers in preferences. """

    if xtools.msg_catchers:
        catcher_str = '{|}'.join(list(xtools.msg_catchers.keys()))
        xtools.settings['msg_catchers'] = catcher_str
    else:
        # no msg catchers
        if 'msg_catchers' in xtools.settings.keys():
            xtools.settings.pop('msg_catchers')
    return True


def save_filters():
    """ Save msg-catchers in preferences. """
    filtertypes = (
        ('nicks', 'msg_filter_nicks'),
        ('filters', 'msg_filters')
    )
    for filtertype, configopt in filtertypes:
        if xtools.msg_filters[filtertype]:
            filter_names = list(xtools.msg_filters[filtertype].keys())
            filter_str = '{|}'.join(filter_names)
            xtools.settings[configopt] = filter_str
        else:
            # no msg catchers
            if configopt in xtools.settings.keys():
                xtools.settings.pop(configopt)
    return True


def save_ignored_nicks():
    """ Save ignored nicks in preferences. """

    if xtools.ignored_nicks:
        ignored_str = ','.join(list(xtools.ignored_nicks.keys()))
        xtools.settings['ignored_nicks'] = ignored_str
    else:
        # nick list is empty.
        if 'ignored_nicks' in xtools.settings.keys():
            xtools.settings.pop('ignored_nicks')

    return True


def save_prefs():
    """ Saves xtools.settings to preferences file. """
    try:
        with open(xtools.config_file, 'w') as fwrite:
            for opt, val in xtools.settings.items():
                if val:
                    fwrite.write('{} = {}\n'.format(opt, val))
            fwrite.flush()
        return True
    except (IOError, OSError) as exio:
        # Error writing/opening preferences.
        print_error('Can\'t save preferences to: '
                    '{}'.format(xtools.config_file),
                    boldtext=xtools.config_file,
                    exc=exio)
        return False


def toggle_redirect_msgs(newtab=False):
    """ Toggle the 'redirect_msgs' setting,
        print it's status (to the xtools tab if newtab=True)
    """
    redirectmsgs = (not xtools.settings.get('redirect_msgs', False))
    xtools.settings['redirect_msgs'] = redirectmsgs
    # set color coded status msg.
    statuscolr = 'green' if redirectmsgs else 'red'
    redirectstate = colorstr(statuscolr, redirectmsgs, bold=True)

    enablestr = colorstr('blue', 'Caught-msg printer enabled')
    if save_prefs():
        statusmsg = 'Saved message printer setting.\n    {}: {}'
    else:
        statusmsg = '{}: {}'
    print_status(statusmsg.format(enablestr, redirectstate), newtab=newtab)


def validate_int_str(intstr, minval=5, maxval=60):
    """ Validates a string that is to be converted to an int.
        If minval, maxval is set then ints are auto-rounded to fit
        to the nearest min/max
        Returns: integer on success, None if int(intstr) fails.
    """

    try:
        intval = int(intstr)
    except (TypeError, ValueError):
        return None

    if intval < minval:
        intval = minval
    elif intval > maxval:
        intval = maxval

    return intval


# Commands -------------------------------------------------------------------

def cmd_catch(word, word_eol, userdata=None):   # noqa
    """ Handles the /CATCH command to add/remove or list caught msgs. """

    cmdname, cmdargs, argd = get_cmd_args(word_eol, (('-c', '--clear'),
                                                     ('-d', '--delete'),
                                                     ('-f', '--filter'),
                                                     ('-h', '--help'),
                                                     ('-l', '--list'),
                                                     ('-m', '--msgs'),
                                                     ('-p', '--print'),
                                                     ('-r', '--remove'),
                                                     ('-t', '--tab')
                                                     ))
    if argd['--help']:
        print_cmdhelp(cmdname, newtab=argd['--tab'])
        return xchat.EAT_ALL
    elif argd['--clear']:
        if clear_catchers():
            print_status('Catch list cleared.', newtab=argd['--tab'])
    elif argd['--delete']:
        if clear_caught_msgs():
            print_status('Caught messages cleared.', newtab=argd['--tab'])
    elif argd['--filter']:
        if not cmdargs:
            print_error('No filter pattern supplied. See \'/help catch\'...')
            return xchat.EAT_ALL
        filtered = filter_caught_msgs(cmdargs)
        if filtered is None:
            # no msgs, or bad regex/text supplied.
            return xchat.EAT_ALL
        msgplural = 'message' if filtered == 1 else 'messages'
        filtered = colorstr('blue', filtered, bold=True)
        print_status('Filtered {} caught {}.'.format(filtered, msgplural),
                     newtab=argd['--tab'])
        return xchat.EAT_ALL
    elif argd['--list']:
        print_catchers(newtab=argd['--tab'])
    elif argd['--msgs']:
        print_caught_msgs(newtab=argd['--tab'])
    elif argd['--print']:
        toggle_redirect_msgs(newtab=argd['--tab'])
    elif argd['--remove']:
        removed = remove_catcher(cmdargs)
        if removed:
            remstr = colorstr('blue', ', '.join(removed), bold=True)
            print_status('Removed {} from the catch-msg list.'.format(remstr),
                         newtab=argd['--tab'])
    elif cmdargs:
        added = add_catcher(cmdargs)
        if added:
            addedstr = colorstr('blue', ', '.join(added), bold=True)
            print_status('Added {} to the catch-msg list.'.format(addedstr),
                         newtab=argd['--tab'])
    else:
        # default
        print_caught_msgs(newtab=argd['--tab'])

    return xchat.EAT_ALL


def cmd_catchers(word, word_eol, userdata=None):
    """ Shortcut command for /catch --list """
    if word[1:]:
        # If the command has args its just an alias for /CATCH
        return cmd_catch(word, word_eol, userdata=userdata)
    else:
        # No args, default action is to list catchers instead of caught msgs.
        print_catchers(newtab=(('-t' in word) or ('--tab' in word)))
        return xchat.EAT_ALL


def cmd_catchfilter(word, word_eol, userdata=None):
    """ Manages filters to catchers,
        msgs that match the filters aren't caught.
    """
    cmdname, cmdargs, argd = get_cmd_args(word_eol, (('-c', '--clear'),
                                                     ('-h', '--help'),
                                                     ('-l', '--list'),
                                                     ('-n', '--nicks'),
                                                     ('-r', '--remove'),
                                                     ('-t', '--tab')
                                                     ))
    # Flag for whether or not this filter only applies to nicks.
    fornick = argd['--nicks']
    listname = 'filter-nick' if fornick else 'filter-msg'

    if argd['--help']:
        print_cmdhelp(cmdname, newtab=argd['--tab'])
        return xchat.EAT_ALL
    elif argd['--clear']:
        if clear_filters():
            print_status('Filter list cleared.', newtab=argd['--tab'])
    elif argd['--list']:
        print_filters(newtab=argd['--tab'], fornick=fornick)

    elif argd['--remove']:
        removed = remove_filter(cmdargs, fornick=fornick)
        if removed:
            remstr = colorstr('blue', ', '.join(removed), bold=True)
            msg = 'Removed {} from the {} list.'.format(remstr, listname)
            print_status(msg, newtab=argd['--tab'])
    elif cmdargs:
        added = add_filter(cmdargs, fornick=fornick)
        if added:
            addedstr = colorstr('blue', ', '.join(added), bold=True)
            print_status(
                'Added {} to the {} list.'.format(addedstr, listname),
                newtab=argd['--tab'])
    else:
        # default
        print_filters(newtab=argd['--tab'], fornick=fornick)

    return xchat.EAT_ALL


def cmd_eval(word, word_eol, userdata=None):  # noqa
    """ Evaluates your own python code, prints query and result
        to the screen or sends the code and output directly to the channel
        as a msg from you.
        Example:
            cmd_eval(['/eval', '-c', 'print("myoutput")'])
            # does:
            # /msg <currentchannel> myoutput
            cmd_eval(['/eval', 'print("private output")'])
            # prints "private output" to your chat window only.
    """

    # Get args from command.
    cmdname, query, argd = get_cmd_args(word_eol,
                                        (('-c', '--chat'),
                                         ('-h', '--help'),
                                         ('-k', '--code'),
                                         ('-r', '--result'),
                                         ('-e', '--errors'),
                                         ('-t', '--tab')))

    if argd['--help']:
        print_cmdhelp(cmdname, newtab=argd['--tab'])
        return xchat.EAT_ALL

    query = query.strip()

    if not query:
        print_error('No code to evaluate.', newtab=argd['--tab'])
        return xchat.EAT_ALL

    # Grab directed nick msg from word if available.
    msgnick = None
    if argd['--chat']:
        queryparts = query.split(' ')
        firstword = queryparts[0]

        chanusers = xchat.get_context().get_list('users')
        if firstword.lower() in [n.nick.lower() for n in chanusers]:
            # first word is a nick, save it and remove it from the query.
            msgnick = firstword
            query = ' '.join(queryparts[1:])

    # Grab comment if any, trim it from the code.
    comment = get_eval_comment(query)
    if comment:
        query = query.replace(comment, '').strip('#').strip()
        # Strip extra space from comment for formatting later.
        comment = comment.strip()

    # Grab code query, if -c and name were only provided its an error.
    if not query:
        print_error('No code to evaluate.', newtab=argd['--tab'])
        return xchat.EAT_ALL

    # Fix newlines
    # allow users to type \\n to escape real newlines,
    # but use \n as an actual newline (as if ENTER had been pressed)
    query = query.replace('\\\\n', '${nl}')
    query = query.replace('\\n', '\n')
    query = query.replace('${nl}', '\\n')
    # Choose exec mode.
    if '\n' in query:
        mode = 'exec'
        if not query.endswith('\n'):
            query = '{}\n'.format(query)
    else:
        mode = 'single'

    # Make an interpreter to run the code.
    compiler = InteractiveInterpreter()

    # Print formatted/parsed code to window....
    if argd['--code']:
        print_status('Running Code:\n{}'.format(query))

    # stdout/stderr will be captured, for optional chat output.
    with StdErrCatcher() as errors:
        with StdOutCatcher() as captured:
            # execute/evaluate the code.
            incomplete = compiler.runsource(query, symbol=mode)

    # Incomplete source code.
    if incomplete:
        # Code will not compile.
        warnmsg = 'Incomplete source.'
        print_error(warnmsg, boldtext=warnmsg, newtab=argd['--tab'])
    # Print any errors.
    elif errors.output:
        # Send error output. Only send to chat if the -c flag is given AND
        # the --errors flag is given. Otherwise print to screen.
        print_evalerror(query, errors.output,
                        chat=(argd['--chat'] and argd['--errors']),
                        chatnick=msgnick,
                        comment=comment,
                        resultonly=argd['--result'],
                        newtab=argd['--tab'])
    # Code had output.
    elif captured.output:
        # Send good output to screen or chat (with or without nick or query)
        print_evalresult(query, captured.output,
                         chat=argd['--chat'],
                         chatnick=msgnick,
                         comment=comment,
                         resultonly=argd['--result'],
                         newtab=argd['--tab'])
    else:
        # No command output, user didn't print() or something.
        print_error('No Output.', newtab=argd['--tab'])
    return xchat.EAT_ALL


def cmd_findtext(word, word_eol, userdata=None):  # noqa
    """ Finds text, and who said it
        Current chat window, or all chat windows.
    """

    # Get current network.
    network = xchat.get_info('network')
    scrollbackbase = os.path.join(xtools.xchat_dir, 'scrollback', network)
    scrollbackdir = os.path.expanduser(scrollbackbase)

    if not os.path.isdir(scrollbackdir):
        print_safe(
            'Error, no scrollback dir found in: {}'.format(scrollbackdir))
        return xchat.EAT_ALL
    # Get cmd args
    cmdname, query, argd = get_cmd_args(word_eol, (('-a', '--all'),
                                                   ('-h', '--help'),
                                                   ('-n', '--nick'),
                                                   ('-t', '--tab')))

    if argd['--help']:
        print_cmdhelp(cmdname)
        return xchat.EAT_ALL

    if not query:
        # Print help when no query is present.
        print_cmdhelp(cmdname)
        return xchat.EAT_ALL

    # Get channels pertaining to this search
    if argd['--all']:
        channelnames = get_channel_names()
        chanquery = None
    else:
        # Check for channel arg.
        queryparts = query.split()
        chanquery = queryparts[0]
        if chanquery in get_channel_names():
            query = ' '.join(queryparts[1:])
            channelnames = [chanquery]
        else:
            # Do current channel.
            channelnames = [xchat.get_context().get_info('channel')]
            chanquery = None

    if not query:
        # user may have passed a channel with no actual query.
        print_cmdhelp(cmdname)
        return xchat.EAT_ALL

    try:
        querypat = re.compile(query)
    except Exception as exre:
        print_error('\nInvalid search query: {}'.format(query),
                    exc=exre,
                    boldtext=query)
        return xchat.EAT_ALL

    # Search channel data
    statusmsg = '\n{} {}'.format(colorstr('blue', 'Searching for:'),
                                 colorstr('red', query))
    chanmsg = '{} {}\n'.format(colorstr('blue', 'In:'),
                               colorstr('red', ', '.join(channelnames)))

    print_safe('\n'.join((statusmsg, chanmsg)), newtab=argd['--tab'])

    totalmatches = 0
    for chan in channelnames:
        # Open chan file
        chandata = []
        chanfile = os.path.join(scrollbackdir, '{}.txt'.format(chan))

        if ('[' in chanfile) or (']' in chanfile):
            chanfile = chanfile.replace(']', '}').replace('[', '{')

        if os.path.isfile(chanfile):
            try:
                with open(chanfile, 'r') as fread:
                    chandata = fread.readlines()
            except (OSError, IOError) as exio:
                print_error('\nUnable to open: {}'.format(chanfile),
                            exc=exio,
                            boldtext=chanfile)
        else:
            if chan == chanquery:
                print_error('No text for channel: {}'.format(chan))

        # Search channel lines
        for line in chandata:
            timedate, nick, text = parse_scrollback_line(line)
            # Check parsed output, should always have timedate and nick.
            if (timedate is None) or (nick is None):
                continue
            # Nick without colors/codes.
            nickraw = remove_mirc_color(nick)
            # Check for feedback from server/script output.
            noticemsg = (nickraw == '*')
            if noticemsg or (not text):
                # Skip this line.
                continue
            # Some feedback still passes, check again.
            feedback = nickraw.startswith('[')
            if feedback:
                # Skip this line.
                continue

            # Line passed checks, Match nick..
            rematch = querypat.search(remove_mirc_color(nick))

            if (rematch is None) and (not argd['--nick']):
                # Match text if nick_only isn't used.
                rematch = querypat.search(text)

            if (rematch is not None) and rematch.group():
                totalmatches += 1
                matchtext = rematch.group()
                # Found a match, format it.
                # Get time string. (12-Hour:Minutes:Seconds)
                timestr = timedate.time().strftime('%I:%M:%S')
                # Color code matches.
                text = text.replace(matchtext, colorstr(color='red',
                                                        text=matchtext,
                                                        bold=True))
                # Print matches.
                # TODO: Fix bug where /whosaid 'myusername' prints results,
                #       ...with 'myusername' replaced with ''.
                result = '[{}] [{}] {}: {}'.format(
                    colorstr('grey', timestr),
                    colorstr('green', chan),
                    colorstr('blue', nick),
                    text)
                print_safe(result, newtab=argd['--tab'])

    # Finished.
    if totalmatches == 0:
        print_safe(
            colorstr('red', '\nNo matches found.'),
            newtab=argd['--tab'])
    else:
        print_safe(
            '\nFound {} matches.\n'.format(colorstr('blue', totalmatches)),
            newtab=argd['--tab'])

    return xchat.EAT_ALL


def cmd_listusers(word, word_eol, userdata=None):
    """ List all users, with a count also. """

    # Get args
    cmdname, cmdargs, argd = get_cmd_args(word_eol, (('-a', '--all'),
                                                     ('-h', '--help'),
                                                     ('-c', '--count'),
                                                     ('-t', '--tab')))

    if argd['--help']:
        print_cmdhelp(cmdname)
        return xchat.EAT_ALL

    if argd['--all']:
        print_safe(
            colorstr('blue', '\nGathering users...\n'),
            newtab=argd['--tab'])
        channels = xchat.get_list('channels')
        userlist = get_all_users(channels=channels)
        userlen = colorstr('blue', len(userlist))
        chanlen = colorstr('blue', len(channels))
        cntstr = ''.join(['\nFound {} users in '.format(userlen),
                          '{} channels.\n'.format(chanlen)])
    else:
        userlist = xchat.get_context().get_list('users')
        userlen = colorstr('blue', len(userlist))
        cntstr = '\nFound {} users.\n'.format(userlen)
    if argd['--count']:
        # Show count results only.
        print_safe(cntstr, newtab=argd['--tab'])
        return xchat.EAT_ALL

    # Format results.
    def color_result(u):
        return '{} - ({})'.format(
            colorstr('blue', u.nick),
            colorstr('purple', u.host))
    userfmt = [color_result(u) for u in userlist]
    print_safe('    {}'.format('\n    '.join(userfmt)), newtab=argd['--tab'])
    print_safe(cntstr, newtab=argd['--tab'])
    return xchat.EAT_ALL


def cmd_searchuser(word, word_eol, userdata=None):  # noqa
    """ Searches for a user nick,
        expects: word = /searchuser [-a] usernickregex
    """
    # Get command args.
    cmdname, query, argd = get_cmd_args(word_eol, (('-H', '--host'),
                                                   ('-h', '--help'),
                                                   ('-o', '--onlyhost'),
                                                   ('-a', '--all'),
                                                   ('-t', '--tab')))

    if argd['--help']:
        print_cmdhelp(cmdname)
        return xchat.EAT_ALL

    # Get query
    if not query:
        errmsg = ('No query. Use /listusers to view all users or '
                  'use /help {} for help.'.format(cmdname.strip('/')))
        print_error(errmsg, newtab=argd['--tab'])
        return xchat.EAT_ALL

    # Whether the host will be used in matching.
    match_host = (argd['--host'] or argd['--onlyhost'])

    # All users or current chat?
    channels = xchat.get_list('channels')
    if argd['--all']:
        # All users from every channel.
        print_safe(
            colorstr('blue', 'Generating list of all users...'),
            newtab=argd['--tab'])
        channelusers = get_channels_users(channels=channels)
        userchannels = {}
        allusernames = []
        userlist = []
        for channelname in channelusers.keys():
            for userinf in channelusers[channelname]:
                # Don't add the same name twice.
                # (Apparently 'if userinf in userlist' doesn't work,
                #  Hince the need for 2 lists, one of them only tracking
                #  duplicates.)
                if userinf.nick not in allusernames:
                    userlist.append(userinf)
                    allusernames.append(userinf.nick)

                if userinf.nick in userchannels.keys():
                    # Append channel to this users list
                    # if the channel isn't already there.
                    if channelname not in userchannels[userinf.nick]:
                        userchannels[userinf.nick].append(channelname)
                else:
                    # New channel list for user
                    userchannels[userinf.nick] = [channelname]

    else:
        # Current channel only.
        channelusers = None
        userchannels = None
        userlist = xchat.get_context().get_list('users')

    # Try compiling the query into regex.
    try:
        querypat = re.compile(query)
    except (Exception, re.error) as exre:
        print_error('Invalid query: {}'.format(query),
                    exc=exre,
                    boldtext=query,
                    newtab=argd['--tab'])
        return xchat.EAT_ALL

    # Search
    # Print status (searching for: {})
    statusmsg = '\n\n{} {} {}'.format(colorstr('darkblue', 'xtools'),
                                      colorstr('blue', 'searching for:'),
                                      colorstr('red', query))
    print_safe(statusmsg, newtab=argd['--tab'])

    results = []
    for userinf in userlist:
        if argd['--onlyhost']:
            rematch = None
        else:
            rematch = querypat.search(userinf.nick)
        rehostmatch = querypat.search(userinf.host) if match_host else None

        if rematch:
            results.append(userinf)
        elif rehostmatch:
            results.append(userinf)

    # Print results.
    if results:
        # Setup some default colors (formatting functions)
        def colornick(n):
            return colorstr(color='blue', text=n)

        def colorhost(h):
            return colorstr(color='darkpurple', text=h)

        def colorchan(cs):
            return colorstr(color='darkgreen', text=cs)

        # Sort results for better printing..
        results = sorted(results, key=lambda u: u.nick)

        # Include host with results string.
        def sorted_chans(user):
            return sorted(userchannels[user.nick])

        if match_host:
            # If all_users was used, build a channel list for each nick.
            if argd['--all'] and userchannels:
                newresults = []
                for userinf in [n for n in results]:
                    if userinf.nick in userchannels.keys():
                        newresults.append((
                            userinf.nick,
                            userinf.host,
                            ', '.join(sorted_chans(userinf))))
                    else:
                        newresults.append((userinf.nick, userinf.host, ''))

                # Helper function for formatting.
                def formatter(t):
                    return '{} - ({})\n{}{}'.format(
                        colornick(t[0]),
                        colorhost(t[1]),
                        (' ' * 8),
                        colorchan(t[2]))

                # Format the new results.
                resultsfmt = [formatter(i) for i in newresults]
            else:
                # Current channel only, no host.
                def formatter(u):
                    return '{} - ({})'.format(
                        colornick(u.nick),
                        colorhost(u.host))
                resultsfmt = [formatter(i) for i in results]

        # Don't include host with results string.
        else:
            # If all_users was used, build a channel list for each nick.
            if argd['--all'] and userchannels:
                newresults = []
                for usernick in [n.nick for n in results]:
                    if usernick in userchannels.keys():
                        newresults.append((usernick,
                                           ', '.join(userchannels[usernick])))
                    else:
                        newresults.append((usernick, ''))

                # Basic format string for user : (channels, channels)
                def formatter(t):
                    return '{}\n{}{}'.format(
                        colornick(t[0]),
                        (' ' * 8),
                        colorchan(t[1]))

                # Use the formatter to format results.
                resultsfmt = [formatter(i) for i in newresults]
            else:
                # Show nick only
                resultsfmt = [colornick(n.nick) for n in results]

        # Single line results or multi line...
        if len(results) < 5 and (not match_host) and (not argd['--all']):
            # Makes 1 line results.
            indention = ''
            joiner = ', '
        else:
            # List style results.
            indention = '\n    '
            joiner = '\n    '

        formattednicks = '{}{}'.format(indention, joiner.join(resultsfmt))
        # Format footer string.
        if argd['--onlyhost']:
            pluralnicks = 'host' if len(results) == 1 else 'hosts'
        else:
            pluralnicks = 'nick' if len(results) == 1 else 'nicks'
        resultstr = colorstr('blue', len(results), bold=True)
        if argd['--all']:
            chanlen = len(channels)
            channellenstr = ' in {} channels'.format(
                colorstr('blue', chanlen))
        else:
            channellenstr = ' in the current channel'
        resultstr = 'Found {} {}{}: {}\n'.format(
            resultstr,
            pluralnicks,
            channellenstr,
            formattednicks)
        print_safe(resultstr, newtab=argd['--tab'])
    else:
        print_safe(
            colorstr('red', 'No nicks found.\n', bold=True),
            newtab=argd['--tab'])

    return xchat.EAT_ALL


def cmd_whitewash(word, word_eol, userdata=None):
    """ Prints a lot of whitespace to 'clear' the chat window. """

    cmdname, cmdargs, argd = get_cmd_args(word_eol, (('-h', '--help'),))

    if argd['--help']:
        print_cmdhelp(cmdname)
        return xchat.EAT_ALL
    elif cmdargs:
        try:
            linecnt = int(cmdargs)
        except ValueError:
            print_error('Invalid number given!')
            return xchat.EAT_ALL
    else:
        # Default amount.
        linecnt = 50
    # Minimum amount.
    if linecnt < 1:
        linecnt = 1
    elif linecnt > 250:
        print_error('Maximum amount exceeded, defaulting to 250.')
        linecnt = 250

    # Print a bunch of blank lines.
    print_status('Washing the window with {} lines.'.format(str(linecnt)))
    print_safe('\n' * linecnt)
    return xchat.EAT_ALL


def cmd_xignore(word, word_eol, userdata=None):  # noqa
    """ Handles the /XIGNORE command to add/remove or list ignored nicks. """

    cmdname, cmdargs, argd = get_cmd_args(word_eol, (('-c', '--clear'),
                                                     ('-d', '--delete'),
                                                     ('-h', '--help'),
                                                     ('-l', '--list'),
                                                     ('-m', '--msgs'),
                                                     ('-r', '--remove'),
                                                     ('-t', '--tab')
                                                     ))
    if argd['--clear']:
        if clear_ignored_nicks():
            print_status('Ignore list cleared.', newtab=argd['--tab'])
    elif argd['--delete']:
        xtools.ignored_msgs = deque(maxlen=xtools.max_ignored_msgs)
        print_status('Deleted all ignored messages.', newtab=argd['--tab'])
    elif argd['--help']:
        print_cmdhelp(cmdname, newtab=argd['--tab'])
    elif argd['--list']:
        print_ignored_nicks(newtab=argd['--tab'])
    elif argd['--msgs']:
        print_ignored_msgs(newtab=argd['--tab'])
    elif argd['--remove']:
        removed = remove_ignored_nick(cmdargs)
        if removed:
            remstr = colorstr('blue', ', '.join(removed), bold=True)
            print_status('Removed {} from the ignored list.'.format(remstr),
                         newtab=argd['--tab'])
    elif cmdargs:
        added = add_ignored_nick(cmdargs)
        if added:
            addedstr = colorstr('blue', ', '.join(added), bold=True)
            print_status('Added {} to the ignored list.'.format(addedstr),
                         newtab=argd['--tab'])
    else:
        # default
        print_ignored_nicks(newtab=argd['--tab'])

    return xchat.EAT_ALL


def cmd_xtools(word, word_eol, userdata=None):
    """ Shows info about xtools. """

    cmdname, cmdargs, argd = get_cmd_args(word_eol, (('-v', '--version'),
                                                     ('-d', '--desc'),
                                                     ('-h', '--help'),
                                                     ('-cd', '--colordemo'),
                                                     ))
    # Version only
    if argd['--version']:
        print_version()
        return xchat.EAT_ALL

    # Command description or descriptions.
    elif argd['--desc']:
        print_cmddesc(cmdargs)
        return xchat.EAT_ALL

    # Command help.
    elif argd['--help']:
        print_cmdhelp(cmdargs)
        return xchat.EAT_ALL

    # Undocumented test for color_code.
    elif argd['--colordemo']:
        print_colordemo()
        return xchat.EAT_ALL

    # No args, default behavior
    print_cmddesc(cmdargs)
    return xchat.EAT_ALL


def filter_chanmsg(word, word_eol, userdata=None):
    """ Filter Channel Messages. """

    # Ignoring messages is easy, just save it and return EAT_ALL.
    msgnick = word[0]
    msg = ' '.join(word[1:]).strip('@').strip()
    for nickkey in xtools.ignored_nicks.keys():
        nickpat = xtools.ignored_nicks[nickkey]['pattern']
        nickmatch = nickpat.search(msgnick)
        if nickmatch:
            # Ignore this message.
            add_message(xtools.ignored_msgs.append,
                        msgnick,
                        msg,
                        msgtype=userdata,
                        matchlist=nickmatch.groups() or [nickmatch.group()],
                        filtertype='nick')
            return xchat.EAT_ALL

    # Caught msgs, needs add_caught_msg because of other scripts emitting
    # duplicate msgs. The add_caught_msg function handles this.
    for catchmsg in xtools.msg_catchers.keys():
        msgpat = xtools.msg_catchers[catchmsg]['pattern']
        msgmatch = msgpat.search(msg)
        if msgmatch:
            add_message(add_caught_msg,
                        msgnick,
                        msg,
                        msgtype=userdata,
                        matchlist=msgmatch.groups() or [msgmatch.group()],
                        filtertype='nick')
            return xchat.EAT_NONE
    # Nothing will be done to this message.
    return xchat.EAT_NONE


def filter_message(word, word_eol, userdata=None):
    """ Filters all channel messages. """

    filter_funcs = {'Channel Message': filter_chanmsg,
                    'Channel Msg Hilight': filter_chanmsg,
                    'Channel Action': filter_chanmsg,
                    'Channel Action Hilight': filter_chanmsg,
                    }

    if userdata in filter_funcs.keys():
        # This event has a function.
        return filter_funcs[userdata](word, word_eol, userdata=userdata)

    return xchat.EAT_NONE

# START OF SCRIPT ------------------------------------------------------------

# List of command names/functions, enabled/disabled, help text.
commands = {
    'catch': {
        'desc': 'Catch messages based on content.',
        'func': cmd_catch,
        'enabled': True,
        'help': '\n'.join((
            'Usage: /CATCH <pattern>',
            '       /CATCH -f <pattern>',
            '       /CATCH -r <pattern>',
            '       /CATCH [-c | -d | -l | -m]',
            'Options:',
            '    <pattern>            : A word or regex pattern, if found in',
            '                           a message it causes the msg to be',
            '                           saved. You can retrieve the msgs',
            '                           with the -m flag.',
            '    -c,--clear           : Clear the msg-catcher list.',
            '    -d,--delete          : Delete all caught messages.',
            '    -f pat,--filter pat  : Remove any saved msgs that contain',
            '                           the given text or regex pattern.',
            '    -l,--list            : List all msg-catcher patterns.',
            '    -m,--msgs            : Print all caught messages.',
            '    -p,--print           : Toggle (enable/disable) the message',
            '                           printer. When enabled, caught msgs',
            '                           are printed to the xtools tab as',
            '                           they are received.',
            '    -r,--remove          : Remove catcher by number or text.',
            '    -t,--tab             : Show output in the xtools tab.',
            '',
            '    * With no arguments passed, all caught msgs are listed.',
            '    * You can pass several space-separated catchers.',
            '    * To include a catcher with spaces, wrap it in quotes.',
        ))},
    'catchers': {
        'desc': 'Shortcut for /CATCH --list, lists all msg-catchers',
        'func': cmd_catchers,
        'enabled': True,
        'help': (
            'Usage: /CATCHERS [/catch args]\n'
            '    ...shortcut for /CATCH --list, lists all msg-catchers.\n'
            '    * any arguments given to this command are sent to the\n'
            '      /CATCH command.')},
    'catchfilter': {
        'desc': 'Adds filters to the msg-catchers to filter certain msgs.',
        'func': cmd_catchfilter,
        'enabled': True,
        'help': (
            'Usage: /CATCHFILTER [-n] <pattern>\n'
            '       /CATCHFILTER -c | -l | -r [-n] [-t]\n'
            'Options:\n'
            '    -c,--clear   : Clear filter list.\n'
            '    -l,--list    : List current filters.\n'
            '    -n,--nicks   : Apply to nicks/nick-filters only,\n'
            '                   not messages.\n'
            '    -r,--remove  : Remove filter by number or text.\n'
            '    -t,--tab     : Show output in the xtools tab.\n'
            '\n'
            '    * With no other arguments, filters are listed.\n'
            '    * There are 2 filter lists, one for nicks, one for msgs.\n'
            '    * Be sure to pass -n to work on the nicks list.\n'
        )},
    'eval': {
        'desc': 'Evaluate python code. Can send output to chat.',
        'func': cmd_eval,
        'enabled': True,
        'help': (
            'Usage: /EVAL [-c [nick] [-e] [-r]] [-k] <code>\n'
            '       /EVAL [-k] [-t] <code>\n'
            'Options:\n'
            '    -c [n],--chat [n] : Send as msg to current channel.\n'
            '                        Newlines are replaced with \\\\n,\n'
            '                        and long output is truncated.\n'
            '                        If a nick (n) is given, mention the\n'
            '                        nick in the message.\n\n'
            '                        * Nick must come before eval code,\n'
            '                          and nick must be present in the\n'
            '                          current channel.\n'
            '    -e,--errors       : Force send any errors to chat.\n'
            '                        This overrides default behavior of\n'
            '                        cancelling chat-sends when exceptions\n'
            '                        are raised.\n'
            '                        Sends the last line of the error msg\n'
            '                        to chat, usually the Exception string.\n'
            '    -k,--code         : Print parsed code to window with\n'
            '                        formatted newlines. Prints before code\n'
            '                        is evaluated.\n'
            '    -r,--result       : When chat-sending, send result only.\n'
            '                        The original query is not sent.\n'
            '    -t,--tab          : Show output in the xtools tab\n\n'
            '    ** Warning: This is an unprotected eval, it will eval\n'
            '                whatever code you give it. It only accepts\n'
            '                input from you, so you only have yourself to\n'
            '                blame when something goes wrong.\n'
            '                It is smarter than the plain eval() function,\n'
            '                which makes it more dangerous too.\n\n'
            '    ** DO NOT import os;os.system(\'rm -rf /\')\n'
            '    ** DO NOT print(open(\'mypassword.txt\').read())\n'
            '    ** DO NOT do anything you wouldn\'t do in a python \n'
            '       interpreter.')},
    'finduser': {
        'desc': None,
        'func': cmd_searchuser,
        'enabled': True,
        'help': None},
    'findtext': {
        'desc': 'Search chat text to see who said what.',
        'func': cmd_findtext,
        'enabled': True,
        'help': (
            'Usage: /FINDTEXT [-a] -[-n] [-t] <text>\n'
            '       /FINDTEXT <#channel> [-n] [-t] <text>\n'
            'Options:\n'
            '     -a,--all   : Search all open windows.\n'
            '     -n,--nick  : Search nicks only.\n'
            '     -t,--tab   : Show output in the xtools tab.')},
    'listusers': {
        'desc': 'List users in all rooms or current room.',
        'func': cmd_listusers,
        'enabled': True,
        'help': (
            'Usage: /LISTUSERS [options]\n'
            'Options:\n'
            '    -a,--all    : List from all channels, not just the\n'
            '                  current channel.\n'
            '    -c,--count  : Show count only.\n'
            '    -t,--tab    : Show output in the xtools tab.')},
    'searchuser': {
        'desc': 'Find users by name or part of a name.',
        'func': cmd_searchuser,
        'enabled': True,
        'help': (
            'Usage: /SEARCHUSER [options] <usernick>\n'
            'Options:\n'
            '    <usernick>     : All or part of a user nick to find.\n'
            '                     Regex is allowed.\n'
            '    -a, --all      : Searches all current channels, not\n'
            '                     just the current channel.\n'
            '    -H,--host      : Search host also.\n' +
            '    -o,--onlyhost  : Only search hosts, not nicks.\n'
            '    -t,--tab       : Show output in the xtools tab.')},
    'wash': {
        'desc': None,
        'func': cmd_whitewash,
        'enabled': True,
        'help': None},
    'whitewash': {
        'desc': 'Prints a lot of whitespace to clear the chat window.',
        'func': cmd_whitewash,
        'enabled': True,
        'help': (
            'Usage: /WHITEWASH [number_of_lines]\n'
            'Options:\n'
            '    number_of_lines  : Print the specified amount of lines.\n'
            '                       Default: 50')},
    'whosaid': {
        'desc': None,
        'func': cmd_findtext,
        'enabled': True,
        'help': None},
    'xignore': {
        'desc': 'Add/Remove or list ignored nicks.',
        'func': cmd_xignore,
        'enabled': True,
        'help': (
            'Usage: /XIGNORE <nick>\n'
            '       /XIGNORE -r <nick>\n'
            '       /XIGNORE [-c | -d | -l | -m]\n'
            'Options:\n'
            '    <nick>       : Regex or text for nick to ignore.\n'
            '    -c,--clear   : Clear the ignored list.\n'
            '    -d,--delete  : Delete all ignored messages.\n'
            '    -l,--list    : List all ignored nicks.\n'
            '    -m,--msgs    : Print all ignored messages.\n'
            '    -r,--remove  : Remove nick by number or name.\n'
            '    -t,--tab     : Show output in the xtools tab\n'
            '\n    * With no arguments passed, all ignored nicks are listed.'
            '\n    * You can pass several space-separated nicks.')},
    'xtools': {
        'desc': 'Show command info or xtools version.',
        'func': cmd_xtools,
        'enabled': True,
        'help': (
            'Usage: /XTOOLS [-v] | [[-d | -h] <cmdname>]\n'
            'Options:\n'
            '    <cmdname>               : Show help for a command.\n'
            '                              (same as /help cmdname)\n'
            '    -d [cmd],--desc [cmd]   : Show description for a command,\n'
            '                              or all commands.\n'
            '    -h [cmd],--help [cmd]   : Show help for a command,\n'
            '                              or all commands.\n'
            '    -v,--version            : Show version.\n'
            '\n    * If no options are given, -d is assumed.')},
}

# Command aliases
# {'aliasname': {'originalcmd': {'helpfix': ('REPLACE', 'REPLACEWITH')}}}
cmd_aliases = {
    'finduser': {'searchuser': {'helpfix': ('SEARCH', 'FIND')}},
    'whosaid': {'findtext': {'helpfix': ('FINDTEXT', 'WHOSAID')}},
    'wash': {'whitewash': {'helpfix': ('WHITEWASH', 'WASH')}},
}

# Load Colors
xtools.colors = build_color_table()

# Load Preferences
load_prefs()
load_ignored_nicks()
load_catchers()
load_filters()


# Fix help and descriptions for aliases
for aliasname in cmd_aliases.keys():
    # Fix help
    for cmd in cmd_aliases[aliasname]:
        replacestr, replacewith = cmd_aliases[aliasname][cmd]['helpfix']
        fixedhelp = commands[cmd]['help'].replace(replacestr, replacewith)
        commands[aliasname]['help'] = fixedhelp
    # Fix description
    aliasforcmds = list(cmd_aliases[aliasname].keys())
    aliasfor = aliasforcmds[0]
    commands[aliasname]['desc'] = commands[aliasfor]['desc']

# Hook all enabled commands.
for cmdname in commands.keys():
    if commands[cmdname]['enabled']:
        xchat.hook_command(cmdname.upper(),
                           commands[cmdname]['func'],
                           userdata=None,
                           help=commands[cmdname]['help'])

# Hook into channel msgs
for eventname in ('Channel Message', 'Channel Msg Hilight',
                  'Channel Action', 'Channel Action Hilight', 'Your Message'):
    xchat.hook_print(eventname, filter_message, userdata=eventname)

# Load Status Message
print_safe(colorstr('blue', '{} loaded.'.format(VERSIONSTR)))
