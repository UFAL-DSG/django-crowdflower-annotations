#!/usr/bin/python
# -*- coding: UTF-8 -*-
#
# Use this script to instantiate some of the files needed by the application by
# settings done in the settings module.
#
# Usage: Edit the `tpt-static-files.lst` file (see instructions there), then
# run this script (with no arguments).

from __future__ import unicode_literals

import codecs
import os
import os.path
import sys

# Update the Python path, then do some more imports.
_script_dir = os.path.realpath(os.path.dirname(__file__))
_site_dir = os.path.realpath(os.path.join(_script_dir, os.pardir, 'trs_site'))

if _site_dir not in sys.path:
    sys.path.insert(0, _site_dir)

import settings
# Note that the `settings' module can change what is imported as django.

from django.template import Context, Template


_default_tptlist = os.path.join(_script_dir, 'tpt-static-files.lst')

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")


def inst_templates(settings_module, tpt_list=_default_tptlist):
    """Instantiates various files for the current settings.

    Arguments:
        settings_module -- the settings module in use
        tpt_list -- path towards a file listing what templates should be
            instantiated. For format of that file, peek into
            `tpt-static-files.lst'.

    """

    if tpt_list is None:
        return

    def _cond_abspath(slashed_path):
        """Interprets the loose format of a path from the tpt_list file as an
        absolute path and returns that."""
        path = slashed_path.replace('/', os.sep).replace('..', os.pardir)
        if os.path.isabs(path):
            return path
        return os.path.normpath(os.path.join(os.path.dirname(tpt_list), path))

    context = Context({'settings': settings_module})
    with open(tpt_list) as tpt_list_file:
        for line in tpt_list_file:
            if not line.startswith('#'):
                tpt_fname, inst_fname = map(_cond_abspath,
                                            line.rstrip('\n').split('\t'))
                with codecs.open(tpt_fname, encoding='UTF-8') as tpt_file:
                    tpt_text = tpt_file.read()
                tpt = Template(tpt_text)
                with codecs.open(inst_fname, 'w',
                                 encoding='UTF-8') as inst_file:
                    inst_file.write(tpt.render(context))


def make_dirs(stngs):
    """Creates directories that will be needed based on the current settings.

    Arguments:
        stngs -- the settings module in use

    Returns whether all directories were successfully created.

    """

    errors = False
    dirnames = [stngs.EXPORT_DIR,
                stngs.CONVERSATION_DIR,
                stngs.LISTS_DIR]
    # Add the database dirname ('db'), if applicable.
    try:
        if (stngs.DATABASES['default']['ENGINE'] ==
                'django.db.backends.sqlite3'):
            db_dirname = os.path.dirname(stngs.DATABASES['default']['NAME'])
            dirnames.append(db_dirname)
    except:
        pass
    # Add Crowdflower-specific directories.
    if stngs.USE_CF:
        dirnames.extend([stngs.WORKLOGS_DIR, stngs.CURLLOGS_DIR])
    # Add the directory for emails if they are to be stored in files.
    if (settings.EMAIL_BACKEND ==
            'django.core.mail.backends.filebased.EmailBackend'):
        dirnames.append(settings.EMAIL_FILE_PATH)

    # Make the directories.
    for dirname in dirnames:
        if os.path.exists(dirname):
            continue
        try:
            os.makedirs(dirname)
        except Exception as ex:
            sys.stderr.write('Could not create the "{dirname}" directory.\n'
                             .format(dirname=dirname))
            sys.stderr.write('Reason: ' + str(ex) + '\n')
            errors = True

    return not errors

if __name__ == "__main__":
    inst_templates(settings)
    success = make_dirs(settings)
    if success:
        print >>sys.stderr, 'Everything has been set up.'
