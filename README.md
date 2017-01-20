# HexChat

This is a collection of hexchat plugins that improve the functionality of
hexchat by providing highlights and extra commands. They are designed for
a Linux system, and probably won't work on Windows.

They were originally designed for XChat, but HexChat has since updated to
Python 3 so they won't work anymore.

You can use `/help` or `/help <plugin-name>` to see usage information.

## xgoogler

This provides a `/google` command that will open your browser to a google
search page using one of `xdg-open`, `kfmclient`, `gnome-ope`n,
or `gvfs-open`.

## xhighlights

Highlights links and name mentions with customizable colors. This can also
highlight anything you want by setting a custom pattern. Just run
`/help highlights` to get more information.

A more detailed description can be found at the
[project page](https://welbornprod.com/misc/xhighlights)
.

I use it to highlight links and names, but also to replace any occurrence of
`PEP-?{NUM}` into a clickable link for that Python PEP.

The actual pattern for that is:
```
^(?P<lbl>[Pp][Ee][Pp][-]?)(?P<num>[\d]{1,4}) bold,darkblue PEP{num} http://python.org/dev/peps/pep-{num:0>4}
```

It can be added with `/highlights -a <pattern_as_above>`

## xtools

Provides search tools for chat/people, message catchers, message ignoring,
python evaluation, and a chat clear command. Run `/xtools` to see a list
of commands it provides, and `/help <command>` to see more information for
each command.

I use it to catch messages with my name in them, and send them to another tab.

If you run `/catch -p`, or put `redirect_msgs = True` in
`~/.config/hexchat/xtools.conf`, then messages will always be directed to
another tab. Otherwise, you will need to print them on demand
(with `/catch -m`).

A more detailed description can be found at the
[project page](https://welbornprod.com/misc/xtools)
.
