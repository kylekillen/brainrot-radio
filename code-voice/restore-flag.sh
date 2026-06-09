#!/bin/bash
# Code Voice — restore the voice-enabled flag at login (it lives in /tmp,
# which clears on reboot). Source of truth is the persistent scope file;
# edit that to change the permanent scope. Editing /tmp directly still works
# as a live runtime override until the next reboot.
SRC="$HOME/.config/codevoice/voice-scope"
DST="/tmp/claude-voice-enabled"
[ -f "$SRC" ] && cp "$SRC" "$DST"
exit 0
