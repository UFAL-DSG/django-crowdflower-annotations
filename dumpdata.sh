#!/bin/bash
./manage.py dumpdata auth.User --indent 2 >`date +%y%m%d`_aotb_trss_users-dump.json
./manage.py dumpdata transcription --indent 2 >`date +%y%m%d`_aotb_trss-dump.json

