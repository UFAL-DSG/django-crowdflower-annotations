#!/usr/bin/env python
import os
import os.path
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
    sys.path.insert(0, os.path.join(os.path.dirname(
        os.path.abspath(__file__)), 'trs_site'))

    sys.path.extend(['/webapps/transcription_cs/libs/python',
                     '/webapps/transcription_cs/libs/django-1.4.1',
                     '/webapps/transcription_cs/libs/python',
                     '/webapps/transcription_cs/libs/django-1.4.1',
                     '/usr/lib/python2.7/',
                     '/usr/lib/python2.7/plat-linux2',
                     '/usr/lib/python2.7/lib-tk',
                     '/usr/lib/python2.7/lib-old',
                     '/usr/lib/python2.7/lib-dynload',
                     ])

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
