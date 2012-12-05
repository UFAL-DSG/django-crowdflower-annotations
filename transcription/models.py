#!/usr/bin/env python2
# -*- coding: UTF-8 -*-
import os.path
from django.db import models
from django.contrib.auth.models import User
from settings import CONVERSATION_DIR, CODE_LENGTH, CODE_LENGTH_EXT

# Create your models here.


class Dialogue(models.Model):
    """Provides the mapping between conversation IDs and corresponding
    dirnames."""
    dirname = models.FilePathField(path=CONVERSATION_DIR,
                                   recursive=True,
                                   unique=True)
    """ the original name of the dialogue directory """
    cid = models.CharField(max_length=40, unique=True, db_index=True)
    code = models.CharField(max_length=CODE_LENGTH)
    code_corr = models.CharField(max_length=CODE_LENGTH_EXT)
    code_incorr = models.CharField(max_length=CODE_LENGTH_EXT)

    def __unicode__(self):
        return u'({c}: {d})'.format(c=self.cid, d=self.dirname)

    def get_codes(self):
        return self.code, self.code_corr, self.code_incorr


class Transcription(models.Model):
    timestamp = models.DateTimeField()
    user = models.ForeignKey(User)
    text = models.TextField()
    turn_id = models.SmallIntegerField()
    object_id = models.ForeignKey(Dialogue, to_field='dirname')
    program_version = models.TextField()
    is_gold = models.BooleanField(default=False)
    breaks_gold = models.BooleanField(default=False)
    # `some_breaks_gold' says whether any of all the transcriptions for the
    # current dialogue from the current user mismatched a gold item
    some_breaks_gold = models.BooleanField(default=False)

    def __unicode__(self):
        return u'({g}{b}{B} u:{u}, t:{t}, f:{f}, "{trs}")'\
            .format(g=(u"G" if self.is_gold else u"_"),
                    b=(u"b" if self.some_breaks_gold else u"_"),
                    B=(u"B" if self.breaks_gold else u"_"),
                    u=self.user,
                    t=self.turn_id,
                    f=self.object_id,
                    trs=self.text)
