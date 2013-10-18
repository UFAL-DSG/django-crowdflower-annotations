#!/usr/bin/python
# -*- coding: UTF-8 -*-

from __future__ import unicode_literals

from transcription.models import Dialogue, DialogueAnnotation
import settings


def config_vars(request):
    return {'USE_CF': settings.USE_CF,
            'APP_URL': settings.APP_URL,
            'SUB_SITE': settings.SUB_SITE}


def trs_stats(request):
    if request.user.is_authenticated():
        dgs_all = Dialogue.objects.all()
        dgs_trsed = Dialogue.objects.filter(
            dialogueannotation__finished=True).distinct()
        dgs_trsed_by_me = DialogueAnnotation.objects.filter(
            user=request.user,
            finished=True).values_list('dialogue', flat=True).distinct()
        return {'n_trsed_by_me': len(dgs_trsed_by_me),
                'n_trsed': len(dgs_trsed),
                'n_trss': len(dgs_all)}
    else:
        return dict()
