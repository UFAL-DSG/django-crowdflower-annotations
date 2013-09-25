#!/bin/bash
SCRIPT_DIR=$(dirname $(readlink -e $0))

"$SCRIPT_DIR"/../manage.py dumpdata auth.User --indent 2 \
	>"$SCRIPT_DIR"/../data/dumps/`date +%y%m%d`_trss_users-dump.json
"$SCRIPT_DIR"/../manage.py dumpdata transcription --indent 2 \
	>"$SCRIPT_DIR"/../data/dumps/`date +%y%m%d`_trss-dump.json
