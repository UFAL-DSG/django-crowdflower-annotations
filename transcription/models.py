#!/usr/bin/env python2
# -*- coding: UTF-8 -*-
# This code is PEP8-compliant. See http://www.python.org/dev/peps/pep-0008/.
from __future__ import unicode_literals

from django.db import models
from django.db.models.signals import post_save, pre_save
from django.contrib.auth.models import User

from db_fields import ROCharField, WavField, SizedTextField
from session_xml import XMLSession
from settings import CODE_LENGTH, CODE_LENGTH_EXT, CONVERSATION_DIR, \
    LISTS_DIR


class Dialogue(models.Model):
    """
    Provides the mapping between conversation IDs and corresponding dirnames.
    """
    cid = ROCharField(max_length=40, unique=True, primary_key=True)
    """ conversation ID """
    dirname = ROCharField(max_length=40, unique=True)
    """ the original name of the dialogue directory """
    code = ROCharField(max_length=CODE_LENGTH)
    """ check code -- the base """
    code_corr = ROCharField(max_length=CODE_LENGTH_EXT)
    """ check code -- the extension in case of no mismatch with gold items """
    code_incorr = ROCharField(max_length=CODE_LENGTH_EXT)
    """ check code -- the extension in case of a mismatch with gold items """
    transcription_price = models.FloatField(null=True)
    """ price of this dialogue's transcriptions in USD """
    list_filename = models.FilePathField(path=LISTS_DIR, recursive=True,
                                         null=True, blank=True)

    def __unicode__(self):
        return '({c}: {d})'.format(c=self.cid, d=self.dirname)

    def get_codes(self):
        return self.code, self.code_corr, self.code_incorr

    def get_code_gold(self):
        return self.code + self.code_corr


class DialogueAnnotation(models.Model):
    """Represents a single submit of an annotation for a single dialogue."""
    QUALITY_NOISY = 0
    QUALITY_CLEAR = 1
    QUALITY_CHOICES = ((u'0', 'noisy'),
                       (QUALITY_NOISY, 'noisy'),
                       (u'1', 'clear'),
                       (QUALITY_CLEAR, 'clear'))
    dialogue = models.ForeignKey(Dialogue)
    quality = models.CharField(max_length=1,
                               choices=QUALITY_CHOICES,
                               default=1)
    accent = models.CharField(max_length=100, blank=True, default="")
    offensive = models.BooleanField(default=False)
    notes = SizedTextField(max_length=500, blank=True, default="", rows=3)
    program_version = models.CharField(max_length=40, editable=False)
    date_saved = models.DateTimeField(auto_now_add=True, editable=False)
    date_paid = models.DateTimeField(null=True, blank=True)
    finished = models.BooleanField(default=True)
    user = models.ForeignKey(User)

    def __unicode__(self):
        return ('(u: {u}; saved: {ds}; q: {q}; acc: {acc}; off: {off}; dg: '
                '{dg})').format(u=self.user.username,
                                ds=self.date_saved,
                                q=DialogueAnnotation.QUALITY_CHOICES[
                                    int(self.quality)][1],
                                acc=(self.accent or "native"),
                                off=self.offensive,
                                dg=self.dialogue.cid)


class DialogueTurn(models.Model):
    """An abstract class for one turn in a dialogue."""
    dialogue = models.ForeignKey(Dialogue)
    turn_number = models.PositiveSmallIntegerField()

    class Meta(object):
        abstract = True


class SystemTurn(DialogueTurn):
    """A system turn, provided with a textual representation of the prompt."""
    text = ROCharField(max_length=255)

    def __unicode__(self):
        return '<SysTurn: n:{num}; "{text}">'.format(
            num=self.turn_number,
            text=self.text.replace('"', '\\"'))


class UserTurn(DialogueTurn):
    """A user turn, provided with a path to the recorded sound."""
    wav_fname = WavField(path=CONVERSATION_DIR, recursive=True, unique=True)

    def __unicode__(self):
        return '<UserTurn: n:{num}; f:"{file_}">'.format(
            num=self.turn_number,
            file_=self.wav_fname)


class Transcription(models.Model):
    """Transcription of one dialogue turn."""
    text = SizedTextField(rows='3')
    turn = models.ForeignKey(UserTurn)
    dialogue_annotation = models.ForeignKey(DialogueAnnotation)
    is_gold = models.BooleanField(default=False)
    breaks_gold = models.BooleanField(default=False)
    some_breaks_gold = models.BooleanField(default=False)
    """`some_breaks_gold' says whether any of all the transcriptions for the
    current dialogue from the current user mismatched a gold item."""
    date_updated = models.DateTimeField(auto_now=True)

    def __unicode__(self):
        return '({g}{b}{B} u:{u}, t:{t}, d:{d}, "{trs}")'\
            .format(g=("G" if self.is_gold else u"_"),
                    b=("b" if self.some_breaks_gold else u"_"),
                    B=("B" if self.breaks_gold else u"_"),
                    u=self.dialogue_annotation.user,
                    t=self.turn.turn_number,
                    d=self.dialogue_annotation.dialogue.dirname,
                    trs=self.text)

    @staticmethod
    def pre_save(sender, **kwargs):
        """
        Makes sure that the specified values from the user are consistent.
        """
        trs = kwargs.pop('instance')
        # `is_gold = True' shall dictate values for `breaks_gold' and
        # `some_breaks_gold'
        if trs.is_gold and trs.breaks_gold:
            # Check whether another transcribed segment from the same
            # annotation breaks gold too.
            trss = Transcription.objects.filter(
                dialogue_annotation=trs.dialogue_annotation)
            some_breaks_gold = False
            for ann_trs in trss:
                if ann_trs == trs:
                    continue
                if ann_trs.breaks_gold:
                    some_breaks_gold = True
                    break
            # If no other transcription breaks gold, reset their
            # `some_breaks_gold' field and update them in the database.
            if not some_breaks_gold:
                for ann_trs in trss:
                    ann_trs.some_breaks_gold = False
                    ann_trs.breaks_gold = False  # For sure.
                    if ann_trs != trs:
                        # NOTE Beware, this could easily cause an infinite
                        # loop if the code is changed with not enough care.
                        ann_trs.save()
            # Update this transcription's `breaks_gold' field.
            trs.breaks_gold = False

    @staticmethod
    def post_save(sender, **kwargs):
        # Only continue if this is an update -- ignore inserts.
        if kwargs.pop('created'):
            return
        trs = kwargs.pop('instance')
        cid = trs.dialogue_annotation.dialogue.cid
        # Read the XML session file.
        with XMLSession(cid) as session:
            # Find the transcription's element.
            trs_xml = session.find_or_create_transcription(trs)
            # Update the transcription's element.
            # NOTE Should a new attribute be added to the element, it has to be
            # added also in views.py:transcribe() (the case of a valid bound
            # form).
            attribs = trs_xml.attrib
            attribs['annotation'] = str(trs.dialogue_annotation.pk)
            attribs['is_gold'] = '1' if trs.is_gold else '0'
            attribs['breaks_gold'] = '1' if trs.breaks_gold else '0'
            attribs['some_breaks_gold'] = '1' if trs.some_breaks_gold else '0'
            attribs['date_updated'] = session.format_datetime(trs.date_updated)
            trs_xml.text = trs.text


pre_save.connect(Transcription.pre_save, sender=Transcription)
post_save.connect(Transcription.post_save, sender=Transcription)
