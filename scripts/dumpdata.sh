#!/bin/bash
../manage.py dumpdata auth.User --indent 2 \
	>../data/dumps/`date +%y%m%d`_trss_users-dump.json
../manage.py dumpdata transcription --indent 2 \
	>../data/dumps/`date +%y%m%d`_trss-dump.json
