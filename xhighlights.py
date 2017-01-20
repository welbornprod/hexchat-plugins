#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""xhighlights.py

    Highlights URLS and Nicks in XChat...
    Colors/Styles are customisable.
    -Christopher Welborn
"""
import logging
import pickle
import os
import re

__module_name__ = 'xhighlights'
__module_version__ = '1.0.0'
__module_description__ = (
    'Highlights URLs, nicks, and custom patterns in the chat window.')
VERSIONSTR = '{} v. {}'.format(__module_name__, __module_version__)


class logger(object):

    """ Simple file logger, created with mylog = logger('logname').log """

    def __init__(self, logname, filename=None, level=None, maxbytes=2097152):
        """ Initialize a new logger.
            Arguments:
                logname  : Name for this logger (shows in logfile)

            Keyword Arguments:
                filename  : File name to use, defaults to:
                            logname.lower().replace(' ', '-')
                level     : Logging level, defaults to: logging.DEBUG
                maxbytes  : Delete old logfile on init if bigger than maxbytes.
                            Default: 2097152 (~2MB)
        """

        # initialize logger with name
        self.log = logging.getLogger(logname)
        # select file name.
        if filename:
            self.filename = filename
        else:
            self.filename = '{}.log'.format(logname.lower().replace(' ', '-'))
        # Check existing log size if available...
        if self.rotate_logfile(maxbytes=maxbytes):
            print('xhighlights: log was rotated.')
        # Set logging level.
        self.setlevel(logging.DEBUG if level is None else level)

        # prepare file handler.
        # build handler
        self.filehandler = logging.FileHandler(self.filename)
        # format for logging messages
        log_format = ('%(asctime)s - [%(levelname)s] '
                      '%(name)s.%(funcName)s (%(lineno)d):\n %(message)s\n')
        self.formatter = logging.Formatter(log_format)
        self.filehandler.setFormatter(self.formatter)
        self.log.addHandler(self.filehandler)

    def rotate_logfile(self, maxbytes=2097152):
        """ Removes an old log if it is over a certain size.
            This can't be done while it is in use.
            It must be done before the logger is initialized.
        """
        if os.path.isfile(self.filename):
            try:
                logsize = os.path.getsize(self.filename)
            except:
                return False
            if logsize > maxbytes:
                # Remove old log file.
                try:
                    os.remove(self.filename)
                    return True
                except:
                    return False
        return False

    def setlevel(self, lvl):
        self.level = lvl
        self.log.setLevel(self.level)


# File for config. CWD is used, it usually defaults to /home/username
try:
    CWD = os.path.split(__file__)[0]
except Exception:
    CWD = os.getcwd()
CONFIGFILE = os.path.join(CWD, 'xhighlights.conf')
LOGFILE = os.path.join(CWD, 'xhighlights.log')
CUSTOMFILE = os.path.join(CWD, 'xhighlights.pkl')


# Logger for xhighlights main.
_log = logger('xhighlights', level=logging.ERROR).log
_log.debug('{} loaded.'.format(VERSIONSTR))

# Regex for matching a link..
# Prefixes (as found in xchat/src/common/url.c)
url_pre = (
    'irc\.', 'ftp\.', 'www\.',
    'irc\://', 'ftp\://', 'http\://', 'https\://',
    'file\://', 'rtsp\://', 'ut2004\://',
)

# Extension (as found in xchat/src/common/url.c)
url_ext = ('org', 'net', 'com', 'edu', 'html', 'info', 'name')
# Start is optional, but will trigger a match.
start = r'(^({})(.))'.format('|'.join(url_pre))
# Middle (when no prefix is found, middle and end are required)
middle = r'([\w\-]+)'
end = r'([\.]({})([^\w\.]|$))'.format('|'.join(url_ext))

# Basic pattern for an email address.
email = r'(.+\@.+\..+)'
# Combine all patterns.
# Middle and End will trigger a match.
linkpattern = '{}?{}{}'.format(start, middle, end)  # , extended)
# Prefix will trigger a match.
linkpattern = ''.join((linkpattern, '|{}{}({})?'.format(start, middle, end)))
# Email address triggers a match.
linkpattern = ''.join((linkpattern, '|{}'.format(email)))
# Final pattern for highlighting a link.
link_re = re.compile(linkpattern)


# Global flag to stop emit_print recursion.
# (not sure why this script started recursing just by changing the regex
#  to catch links, but this flag will ensure that message_filter doesn't
#  try to 'filter' my own emit_print())
# See emit_highlighted() and message_filter().
EMITTING = False


def add_custom_pattern(cmdargs):
    """ Add a custom pattern to highlight/replace.
        Based on user arguments from --add command.
        Expects: 'pattern style template'
    """

    # Parse user args for --add.
    argparts = cmdargs.split(' ')
    if len(argparts) == 3:
        pattxt, style, template = argparts
    elif len(argparts) == 2:
        pattxt, style = argparts
        template = '{}'
    else:
        errmsg = 'Invalid arguments for --add: {}'.format(cmdargs)
        print_error(errmsg, boldtext=cmdargs)
        return None
    # Make sure pattern is valid.
    try:
        custompat = re.compile(pattxt)
    except re.error as exre:
        errmsg = 'Invalid pattern for --add: {}'.format(pattxt)
        print_error(errmsg, exc=exre, boldtext=pattxt)
        return None
    # Test template.
    try:
        fmted = template.format('test')
    except (KeyError, ValueError) as extmp:
        errmsgs = [str(extmp)]
        try:
            keypat = re.compile(r'\{(\w+)[:\}]')
            keynames = keypat.findall(template)
            fmted = template.format(**{k: 'test' for k in keynames})
        except KeyError as exdict:
            errmsgs.append(str(exdict))
            errheader = 'Invalid template for --add: {}'.format(template)
            errmsgs.insert(0, errheader)
            errmsg = '\n'.join(errmsgs)
            print_error(errmsg, boldtext=template)
            return None
    # Make sure the template wasn't empty.
    if not fmted:
        errmsg = 'Invalid (empty) template for --add!'
        print_error(errmsg)
        return None
    # Test style.
    style = style.lower().strip()
    stylecodes = get_stylecodes(style)
    if not stylecodes:
        # get_stylecodes() will already print the error. Just return here.
        return None

    # We have a successful pattern, style, and template.
    custompat = {
        'pattern': custompat,
        'patterntext': pattxt,
        'stylecodes': stylecodes,
        'style': style,
        'template': template
    }
    Codes.custom.append(custompat)
    save_user_patterns()
    return None


def build_color_table():
    """ Builds a dict of {colorname: colorcode} and returns it. """
    start = ''
    boldcode = ''
    underlinecode = ''
    resetcode = ''

    # Codes (index is the color code)
    codes = [
        'none', 'black', 'darkblue',
        'darkgreen', 'darkred', 'red', 'darkpurple',
        'brown', 'yellow', 'green', 'darkcyan',
        'cyan', 'blue', 'purple', 'darkgrey', 'grey'
    ]

    # Build basic table.
    colors = {}
    for i, code in enumerate(codes):
        colors[code] = {
            'index': i,
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


def cmd_xhighlights(word, word_eol, userdata):
    """ Handles / XHIGHLIGHTS command.
        Allows you to set default colors / styles.
    """

    # Clean word and get flags for command.
    word, argd = get_flag_args(
        word, [
            ('-a', '--add', False),
            ('-c', '--colors', False),
            ('-h', '--help', False),
            ('-l', '--link', False),
            ('-n', '--nick', False),
            ('-p', '--patterns', False),
            ('-r', '--remove', False),
        ])
    cmdargsraw = get_cmd_rest(word).strip()
    cmdargs = cmdargsraw.lower()
    # Add a custom pattern.
    if argd['--add']:
        add_custom_pattern(cmdargsraw)
        return xchat.EAT_ALL

    # Remove a custom pattern.
    if argd['--remove']:
        remove_custom_pattern(cmdargs)
        return xchat.EAT_ALL

    # Print custom patterns.
    if argd['--patterns']:
        print_custom_patterns()
        return xchat.EAT_ALL

    # Just print styles..
    if argd['--colors']:
        print_styles()
        return xchat.EAT_ALL

    # Print help
    if argd['--help']:
        # prints help for correct cmdname even if an alias was used.
        print_help(word[0])
        return xchat.EAT_ALL

    # Check ambiguous args.
    if argd['--link'] and argd['--nick']:
        print_error('Cannot use --link and --nick at the same time.')
        return xchat.EAT_ALL

    # If no style was passed, just print the current style.
    if not cmdargs:
        if not (argd['--link'] or argd['--nick']):
            # No args at all. Print all styles.
            print_currentstyles()
        else:
            # Print single style, for whatever arg was passed.
            print_currentstyles(link=argd['--link'], nick=argd['--nick'])
        return xchat.EAT_ALL

    # Set nick code.
    if argd['--nick']:
        set_style(cmdargs, 'nick')
    # Set link style.
    elif argd['--link']:
        set_style(cmdargs, 'link')

    return xchat.EAT_ALL


def color_code(color, suppresswarning=False):
    """ Returns a color code by name or mIRC number. """

    try:
        code = COLORS[color]['code']
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

    if suppresswarning:
        return None

    # Can't find that color! this is the coders fault :(
    print_error(
        'Script error: Invalid color for color_code: {}'.format(
            color
        ),
        boldtext=color
    )
    return COLORS['reset']['code']


def color_text(color=None, text=None, bold=False, underline=False):
    """ return a color coded word.
        Keyword Arguments:
            color:
                Named color, or mIRC color number.
            text:
                Text to be colored.
            bold:
                Boolean, whether text is bold or not.
            underline:
                Boolean. whether text is underlined or not.
    """

    # normal color code
    boldcode = ''
    underlinecode = ''
    normal = ''
    code = color_code(color)
    # initial text items (basic coloring)
    strcodes = [code, text]
    # Handle extra formatting (bold, underline)
    if underline:
        strcodes.insert(0, underlinecode)
    if bold:
        strcodes.insert(0, boldcode)

    return '{}{}'.format(''.join(strcodes), normal)


def get_cmd_rest(word):
    """ Return the rest of a command. (removing / COMMAND) """

    if word:
        if len(word) == 1:
            return ''
        else:
            rest = word[1:]
            return ' '.join(rest)
    return ''


def get_flag_args(word, arglist):
    """ Retrieves flag args from a command,
        returns a tuple with:
            (cleaned_word, {'--longopt': True / False, ...})
            ...where clean_word has all args removed,
            ...and the dict has long options with True / False value.

        expects:
            word:
                from cmd_ word list.
            arglist:
                list of tuples with [('-s', '--long', False), ...]
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
                         '--debug': False,  # no -d flag was given.
                         }
                * Notice the / cmd is kept, it is useful for certain commands.
                * get_cmd_rest(word) can remove it and return extra stuff only.
    """

    def safe_remove(lst, items):
        """ Safely removes list of items from a lst. """
        for i in items:
            try:
                lst.remove(i)
            except:
                # Item was not in the list.
                pass

    # Build default arg info.
    builtarglist = []
    for argset in arglist:
        if len(argset) < 3:
            shortopt, longopt = argset
            default = False
        elif len(argset) == 3:
            shortopt, longopt, default = argset
        else:
            print('\nInvalid arglist for get_flag_args!: '
                  '{}'.format(repr(argset)))
            return {}
        # Add the proper arg info, for parsing.
        builtarglist.append((shortopt, longopt, default))

    # Parse args, remove them from word as we go.
    newword = [c for c in word]
    arginfo = {}
    for shortarg, longarg, default in builtarglist:
        if (shortarg in word) or (longarg in word):
            # Remove both short and long options from word.
            safe_remove(newword, [shortarg, longarg])
            # Flag was found, set it.
            arginfo[longarg] = True
        else:
            # No short or long, set default.
            arginfo[longarg] = default

    # Return cleaned word, and arg dict.
    return newword, arginfo


def get_stylecodes(userstyle):
    """ Parse and return the actual style codes from a users style string. """
    stylenames = parse_styles(userstyle)
    stylecodes = try_stylecodes(stylenames)
    if not stylecodes:
        print_error(
            'Invalid style code: {}'.format(userstyle),
            boldtext=userstyle
        )
        return None
    return stylecodes


def emit_highlighted(*emitargs):
    """ Emits a print by unhooking, emitting, and rehooking to prevent
        recursion.
        (this used to not recurse anyway, it's under investigation..)

        Arguments:
            *emitargs: Arguments for emit_print.
    """
    global EMITTING
    EMITTING = True
    xchat.get_context().emit_print(*emitargs)
    EMITTING = False
    return xchat.EAT_ALL


def highlight_custom(word, patterninfo):
    """ Highlight a custom word. """
    template = patterninfo['template']

    def colorize(s):
        """ Wraps a word with the user styles and a reset. """
        codes = patterninfo['stylecodes']
        return '{}{}{}'.format(codes, s, Codes.normal)

    rematch = patterninfo['pattern'].match(word)
    if not rematch:
        return word
    matchgroupdict = rematch.groupdict()
    if matchgroupdict:
        # User is using named groups.
        try:
            newword = colorize(template.format(**matchgroupdict))
        except Exception as ex:
            errfmt = 'Unable to use .groupdict(): {}\n    with: {}\n    {}'
            errmsg = errfmt.format(matchgroupdict, template, ex)
            _log.error(errmsg)
            return word
        else:
            return newword

    matchgroups = rematch.groups()
    if matchgroups:
        # User is using groups with the template.
        try:
            newword = colorize(template.format(*matchgroups))
        except Exception as ex:
            errfmt = 'Unable to use .groups(): {}\n    with: {}\n    {}'
            _log.error(errfmt.format(matchgroups, template, ex))
            return word
        else:
            # Return colorized groups.
            return newword

    # Simple single word highlight.
    return colorize(template.format(word))


def highlight_word(s, style='link', ownmsg=False):
    """ Highlight a single word (string) in the prefferred style
        s:
            The word(string) to highlight.
        style:
            Type of word, either 'nick' or 'link'
    """
    if not style:
        style = 'link'
    # Own messages are grey on my system.
    # so grey is normal if its my own message.
    # Otherwise, black is normal (actually 'normal' is normal)
    colornormal = Codes.ownmsg if ownmsg else Codes.normal
    resetcode = Codes.normal + colornormal if ownmsg else colornormal

    if style == 'link':
        # LINK Highlighting
        stylecode = Codes.link
    elif style == 'nick':
        # NICK Highlighting
        stylecode = Codes.nick
    else:
        # Not implemented
        stylecode = Codes.normal
    formatted = '{style}{word}{reset}'.format(
        style=stylecode,
        word=s,
        reset=resetcode
    )
    return formatted


def load_user_color(stylename):
    """ Loads colors from preferences, or uses defaults on error. """
    stylename = stylename.lower().strip()
    user_pref = pref_get('xhighlights_{}'.format(stylename))
    if user_pref:
        if not set_style(user_pref, stylename, silent=True):
            # Failure
            print_status('Default {} style will be used.'.format(stylename))
            try:
                defaultcode = getattr(Codes, 'default{}'.format(stylename))
                setattr(Codes, stylename, defaultcode)
            except Exception as ex:
                print_error('Unable to set default style: '
                            '{}'.format(stylename),
                            exc=ex)
            return False
    return True


def load_user_patterns():
    """ Load custom user patterns from the pickle file.
        If it doesn't exist, then do nothing.
    """
    if not os.path.isfile(CUSTOMFILE):
        Codes.custom = []
        return False

    try:
        with open(CUSTOMFILE, 'rb') as f:
            data = f.read()
            if not data:
                return False
            data = pickle.loads(data)
    except EnvironmentError as ex:
        errmsg = 'Unable to load custom patterns!'
        print_error(errmsg, exc=ex)
        return False
    Codes.custom = data[:]


def message_filter(word, word_eol, userdata):
    """ Filter all messages coming into the chat window.
        Arguments:
            word:
                List of data[nick, message]
            word_eol:
                Same as word except [nick message, message]
            userdata:
                The event this message came from (used to emit_print())
    """
    if EMITTING:
        _log.debug('Skipping own emit type: {}'.format(userdata))
        return xchat.EAT_NONE
    _log.debug('Filtering message type: {}'.format(userdata))

    # Get list of nicks.
    userslist = [u.nick for u in xchat.get_list('users')]

    # Get nick for message, and current users nick
    msgnick = word[0]

    # The actual message.
    msg = word[1]
    # Words in the actual message.
    msgwords = msg.split(' ')
    # Flag for when messsages are modified
    # (otherwise we don't emit or EAT anything.)
    highlighted = False

    if userdata and ('Msg Hilight' in userdata):
        normalmsg = False
    else:
        normalmsg = True

    usernick = (xchat.get_context()).get_info('nick')
    msgnick = remove_mirc_color(word[0])
    # Determine if this is the users own message
    # (changes highlight_word() settings)
    userownmsg = (usernick == msgnick)

    for i, eachword in enumerate(msgwords):
        # Word is users own nick name?
        ownnick = (eachword == usernick) or (eachword[:-1] == usernick)
        # Word is any user name?
        nickword = (eachword in userslist) or (eachword[:-1] in userslist)

        # Custom patterns.
        for custompat in Codes.custom:
            if custompat['pattern'].match(eachword):
                msgwords[i] = highlight_custom(eachword, custompat)
                # Set eachword to the newly highlighted custom pattern
                # If it was turned into a link, it will be highlighted.
                eachword = msgwords[i]
                highlighted = True
                break

        # Link highlighting
        linkmatch = link_re.search(eachword)
        if linkmatch is not None:
            # Highlight it
            msgwords[i] = highlight_word(
                eachword,
                'link',
                ownmsg=userownmsg
            )
            highlighted = True

        # Nick highlighting
        # (Don't highlight your own nick, thats for Channel Msg Hilight)
        elif (normalmsg and (not ownnick)) and nickword:
            msgwords[i] = highlight_word(
                eachword,
                'nick',
                ownmsg=userownmsg
            )
            highlighted = True

    # Replace old message.
    word[1] = ' '.join(msgwords)

    # Print to the chat window.
    if highlighted:
        _log.debug('Highlighted: {}'.format(' '.join(word)))
        # Emit modified message (with highlighting)
        # (userdata=Event Name, word = Modifed Message)
        return emit_highlighted(*([userdata] + word))
    else:
        # Nothing was done to this message
        return xchat.EAT_NONE


def parse_styles(txt):
    """ Parses comma - separated styles. """
    return [s.strip() for s in txt.split(',')]


def pref_get(opt):
    """ Retrieves an XHighlights preference.
        Does not depend on XChats preferences file anymore.
        It will read from the global CONFIGFILE.
    """
    # Load prefs data.
    if os.path.isfile(CONFIGFILE):
        try:
            with open(CONFIGFILE, 'r') as fread:
                allprefs = fread.readlines()
        except (IOError, OSError) as ex:
            print_error('Unable to open config file: {}'.format(CONFIGFILE),
                        exc=ex,
                        boldtext=CONFIGFILE)
            return False
    else:
        # No prefs file.
        allprefs = []
    existingopt = None
    for line in allprefs:
        if line.startswith(opt):
            # Found the line, retrieve its whole content.
            existingopt = line
            break

    # No option found.
    if not existingopt:
        return None

    # Parse option.
    if '=' in existingopt:
        val = existingopt.strip('\n').split('=')[1].strip()
        return val
    else:
        # Bad config
        return None


def pref_set(opt, val):
    """ Sets an XHighlights preference.
        Does not depend on the XChat preferences file.
        Will store in global CONFIGFILE.
    """

    # Load prefs data.
    if os.path.isfile(CONFIGFILE):
        try:
            with open(CONFIGFILE, 'r') as fread:
                allprefs = fread.readlines()
        except (IOError, OSError) as ex:
            print_error('Unable to open config file: {}'.format(CONFIGFILE),
                        exc=ex,
                        boldtext=CONFIGFILE)
            return False
    else:
        # No config file yet.
        allprefs = []

    # new options line for xchat.conf.
    optline = '{} = {}'.format(opt, str(val))

    # Search preferences for this option.
    existingopt = None
    for line in allprefs:
        if line.startswith(opt):
            # Found the line, retrieve its whole content.
            existingopt = line
            break

    # Existing pref.
    if existingopt:
        if existingopt == optline:
            # Pref already set.
            return True

        allprefs[allprefs.index(existingopt)] = optline
    # New pref.
    else:
        allprefs.append(optline)

    # Remove blank lines..
    while '' in allprefs:
        allprefs.remove('')
    while '\n' in allprefs:
        allprefs.remove('\n')

    # Write preferences.
    try:
        with open(CONFIGFILE, 'w') as fwrite:
            fwrite.writelines(allprefs)
            fwrite.write('\n')
            return True
    except (IOError, OSError) as ex:
        print_error(
            'Unable to write to config file: {}'.format(CONFIGFILE),
            exc=ex,
            boldtext=CONFIGFILE
        )
        return False


def print_currentstyles(link=True, nick=True):
    """ Print the current settings. """

    if not (link or nick):
        return False

    if link and nick:
        header = 'Current styles are:'
    else:
        header = 'Current link style:' if link else 'Current nick style:'
    print('\n{}'.format(header))
    if link:
        print('    {}Link'.format(Codes.link))
    if nick:
        print('    {}Nick'.format(Codes.nick))


def print_custom_patterns():
    """ Print all of the custom patterns to the window. """
    if not Codes.custom:
        print_error('No custom patterns have been set. Set them with --add.')
        return None

    print_status('Current custom patterns:')
    patfmt = '{index}: {txt} {style} {template}'
    for i, custompat in enumerate(Codes.custom):
        patstr = patfmt.format(
            index=color_text('blue', str(i), bold=True),
            txt=color_text('green', custompat['patterntext']),
            style=custompat['style'],
            template=color_text('red', custompat['template']))
        print(patstr)


def print_error(msg, exc=None, boldtext=None):
    """ Prints a red formatted error msg.
        Arguments:
            msg:
                Normal message to print in red.
            exc:
                Exception() object to print (or None)
            boldtext:
                Text that should be in Bold(or None)

        Ex:
            print_error('Error in: Main', exc=None, boldtext='Main')
    """

    # Make boldtext bold if it was passed.
    if boldtext:
        # All parts of the message except boldtext.
        msgpart = msg.split(boldtext)
        # Copy of the boldtext, formatted.
        boldfmt = color_text('red', boldtext, bold=True)
        # Formatted normal message parts.
        msgfmt = [color_text('red', s) if s else '' for s in msgpart]
        # Final formatted message.
        msg = boldfmt.join(msgfmt)
    else:
        # Normal message.
        msg = '\n{}\n'.format(color_text('red', msg))

    # Append xtools so you know where this error is coming from.
    msg = '{}{}'.format(color_text('grey', 'xtools: '), msg)
    # Print formatted message.
    print(msg)

    # Print exception.
    if exc:
        print(color_text('red', '\n{}'.format(exc)))


def print_help(cmdname):
    """ Prints the command help, plus a little debugging info.
        Arguments:
            cmdname   : Name of command to get help for.
                        (must be in cmd_help)
    """
    if cmdname.startswith('/'):
        cmdname = cmdname.lower().strip('/')

    if cmdname not in cmd_help.keys():
        return None

    # Header
    print('\nHelp for {} ({}):'.format(color_text('grey', VERSIONSTR),
                                       color_text('red', cmdname, bold=True)))
    # Actual help lines.
    for line in cmd_help[cmdname].split('\n'):
        if ('--' in line) and (':' in line):
            # option line, color code it.
            parts = line.split(':')
            if len(parts) == 2:
                opt, desc = parts
                print('    {}:{}'.format(color_text('blue', opt),
                                         color_text('grey', desc)))

        elif line.startswith('        '):
            # Continuation of opt/desc line.
            print('    {}'.format(color_text('grey', line)))

        elif line.strip().startswith('*'):
            # Notes line..
            print('    {}'.format(color_text('blue', line)))

        else:
            # Usage or other line.
            print('    {}'.format(line))

    # Debug info (file locations)
    loglevel = str(_log.getEffectiveLevel())
    debuglines = [
        '    Configuration File: {}'.format(str(CONFIGFILE)),
        '   Custom Pattern File: {}'.format(str(CUSTOMFILE)),
        '              Log File: {}'.format(str(LOGFILE)),
        '             Log Level: {}'.format(loglevel),
    ]
    for line in debuglines:
        print(color_text('grey', line))


def print_status(s):
    """ Prints a formatted status message. """

    print('\n{}\n'.format(color_text('green', s)))


# Helper function for remove_mirc_color (for preloading sub function)
mirc_color_regex = re.escape('\x03') + r'(?:(\d{1,2})(?:,(\d{1,2}))?)?'
mirc_sub_pattern = re.compile(mirc_color_regex).sub


def print_styles():
    """ Print all available styles. """

    print('Available styles:')
    for cname in sorted(COLORS.keys(), key=lambda x: COLORS[x]['index']):
        cindex = str(COLORS[cname]['index'])
        if len(cindex) == 1:
            cindex = '0{}'.format(cindex)
        print('    {} : {}'.format(cindex, color_text(cname, cname)))
    print('')


def remove_custom_pattern(index):
    """ Remove a custom pattern from the list, by index. """

    try:
        index = int(index)
    except (TypeError, ValueError):
        errmsg = 'Invalid index for custom pattern: {}'.format(index)
        print_error(errmsg, boldtext=str(index))
        return None
    try:
        item = Codes.custom.pop(index)
    except IndexError as exindex:
        errmsg = 'Error removing custom pattern: {}'.format(index)
        print_error(errmsg, exc=exindex, boldtext=str(index))
        return None
    itempat = item['patterntext']
    print_status('Removed: {}'.format(itempat))
    if save_user_patterns():
        return item
    # Error saving.
    return None


def remove_mirc_color(text, _resubpat=mirc_sub_pattern):
    """ Removes color code from text
        (idea borrowed from nosklos clutterless.py)
        Sub pattern is preloaded on function definition,
        like nosklos(but more readable i think)
    """
    return _resubpat('', text)


def save_user_patterns():
    """ Save CUSTOMPATS to a pickle file.
        Returns True on success, False on failure.
        Prints status/error messages.
    """
    try:
        with open(CUSTOMFILE, 'wb') as f:
            pickle.dump(Codes.custom, f)
    except EnvironmentError as expickle:
        errmsg = 'Unable to save custom patterns!'
        print_error(errmsg, exc=expickle)
        return False
    print_status('Custom patterns were saved. [{}]'.format(len(Codes.custom)))
    return True


def set_style(userstyle, stylename=None, silent=False):
    """ Sets the current style for 'link' or 'nick' """

    userstyle = userstyle.lower().strip()
    stylename = stylename.lower().strip() if stylename else 'link'

    stylecodes = get_stylecodes(userstyle)

    if stylename == 'link':
        Codes.link = stylecodes
    elif stylename == 'nick':
        Codes.nick = stylecodes
    else:
        print_error(
            'Invalid style name: {}'.format(stylename),
            boldtext=stylename
        )
        return False

    # Save preference.
    if not pref_set('xhighlights_{}'.format(stylename), userstyle):
        print_error('Unable to save preference for {}.'.format(stylename))
        return False

    if not silent:
        print_status('Set style for {}: {}{}'.format(
            stylename,
            stylecodes,
            userstyle
        ))
    return True


def try_stylecodes(styles):
    """ Trys to retrieve multiple style codes, and returns a string
        containing them.
        Returns None if one of them fails.
    """

    final = ''
    for style in styles:
        stylecode = color_code(style, suppresswarning=True)
        if not stylecode:
            return None
        final = final + stylecode
    return final


# START OF SCRIPT
# Load colors (must be loaded before class Codes()).
COLORS = build_color_table()


class Codes(object):
    """ Holds current highlight styles. """
    defaultlink = color_code('u') + color_code('blue')
    defaultnick = color_code('green')
    link = defaultlink
    nick = defaultnick
    ownmsg = color_code('darkgrey')
    normal = color_code('reset')
    custom = []


# Load user preferences.
for stylename in ('link', 'nick'):
    load_user_color(stylename)
load_user_patterns()


# Commands and command help strings.
cmd_help = {
    'xhighlights': (
        'Usage: /XHIGHLIGHTS [-n [style] | -l [style]]\n'
        '       /XHIGHLIGHTS -a <pattern> <style> [template]\n'
        '       /XHIGHLIGHTS -r <index>\n'
        'Options:\n'
        '    -a p s t,--add p s t   : Add a custom pattern/word to\n'
        '                             highlight. Its needs a pattern or\n'
        '                             word to match, a color/style in the\n'
        '                             same format as -c, and a replacement\n'
        '                             template.\n'
        '                             The template must at least consist of:\n'
        '                             "{}" ..but advanced use would be like:\n'
        '                             "http://google.com?q={}"\n'
        '                             If the { or } characters must be used,\n'
        '                             they should be doubled ({{ and }}).\n'
        '    -c,--colors            : Show available styles.\n'
        '    -h,--help              : Show this message.\n'
        '                             (and some debugging info)\n'
        '    -l style,--link style  : Set link style by name/number.\n'
        '    -n style,--nick style  : Set nick style by name/number.\n'
        '    -p,--patterns          : Show current custom patterns.\n'
        '    -r num,--remove num    : Remove custom pattern by index.\n'
        '\n    * style can be comma separated style names/numbers.\n'
        '    * if no style is given, the current style will be shown.\n'),
}

commands = {
    'xhighlights': {
        'desc': 'Gets and sets options for xhighlights.',
        'func': cmd_xhighlights,
        'enabled': True,
    },
    'highlights': {
        'desc': 'alias',
        'func': cmd_xhighlights,
        'enabled': True,
    },
}

# command aliases.
cmd_aliases = {
    'highlights': {
        'xhighlights': {
            'helpfix': ('XHIGH', 'HIGH')
        },
    },
}

# Fix help and descriptions for aliases
for aliasname in cmd_aliases.keys():
    # Fix help
    for cmd in cmd_aliases[aliasname]:
        replacestr, replacewith = cmd_aliases[aliasname][cmd]['helpfix']
        cmd_help[aliasname] = cmd_help[cmd].replace(replacestr, replacewith)
    # Fix description
    aliasforcmds = list(cmd_aliases[aliasname].keys())
    aliasfor = aliasforcmds[0]
    commands[aliasname]['desc'] = commands[aliasfor]['desc']
try:
    import hexchat as xchat
    xchat.EAT_XCHAT = xchat.EAT_HEXCHAT
except ImportError:
    try:
        import xchat
    except ImportError:
        print('Can\'t find xchat or hexchat.')
        exit(1)
# Hook all enabled commands.
_log.debug('Initial hook into commands...')
command_hooks = {}
for cmdname in commands.keys():
    if commands[cmdname]['enabled']:
        command_hooks[cmdname] = xchat.hook_command(
            cmdname.upper(),
            commands[cmdname]['func'],
            userdata=None,
            help=cmd_help[cmdname]
        )
        _log.debug('Initially hooked command: {}'.format(cmdname))


# Hook into channel msgs
_log.debug('Initial hook into channel messages...')
event_hooks = {}
for eventname in ('Channel Message', 'Channel Msg Hilight', 'Your Message'):
    eventhookname = 'message_filter.{}'.format(
        eventname.lower().replace(' ', '')
    )
    event_hooks[eventhookname] = xchat.hook_print(
        eventname,
        message_filter,
        userdata=eventname
    )
    _log.debug('Initially hooked event: {}'.format(eventhookname))


# Print status
print(color_text('blue', '{} loaded.'.format(VERSIONSTR)))
_log.debug('Initialization finished.')
