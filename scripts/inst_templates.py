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

from django.template import Context, Template

import settings

_script_dir = os.path.realpath(os.path.dirname(__file__))
_default_tptlist = os.path.join(_script_dir, 'tpt-static-files.lst')

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "transcription.settings")


def inst_templates(settings_module, tpt_list=_default_tptlist):
    if tpt_list is None:
        return

    def _cond_abspath(slashed_path):
        path = slashed_path.replace('/', os.sep)
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


if __name__ == "__main__":
    inst_templates(settings)
