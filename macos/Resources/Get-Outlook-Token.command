#!/bin/zsh
SCRIPT_DIRECTORY="${0:A:h}"
"$SCRIPT_DIRECTORY/worker/MailWorker" --outlook-token
