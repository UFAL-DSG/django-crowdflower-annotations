#!/usr/bin/env python2
# -*- coding: UTF-8 -*-
# This code is PEP8-compliant. See http://www.python.org/dev/peps/pep-0008/.
from __future__ import unicode_literals

import sys
from alex_da.components.slu import da
from django.core.exceptions import ValidationError
import settings


def validate_dai(dai):
    # XXX Why do we compare to None at one place, and to '' elsewhere?
    if dai.name is None and dai.value is None:
        if dai.dat not in settings.nullary_dat:
            raise ValidationError('Unknown dat: {0}'.format(dai.dat))
    elif dai.name != '' and dai.value == '':
        if dai.dat not in settings.unary_dat_with_slot:
            raise ValidationError('Unknown dat: {0}'.format(dai.dat))
        if dai.name not in settings.name_of_slot:
            raise ValidationError('Unknown slot: {0}'.format(dai.name))
    elif dai.name == '' and dai.value != '':
        if dai.dat not in settings.unary_dat_with_value:
            raise ValidationError('Unknown dat: {0}'.format(dai.dat))
    else:
        if dai.dat not in settings.binary_dat:
            raise ValidationError('Unknown dat: {0}'.format(dai.dat))
        if dai.name not in settings.name_of_slot:
            raise ValidationError('Unknown slot: {0}'.format(dai.name))


def validate_slu(value):
    try:
        diag_act = da.DialogueAct(value)
    except:
        raise ValidationError('Wrong format: {0}'.format(value))
    for dai in diag_act.dais:
        validate_dai(dai)
