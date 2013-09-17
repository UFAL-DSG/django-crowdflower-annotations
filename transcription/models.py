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
    LISTS_DIR, USE_CF, EXTRA_QUESTIONS


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

    # Create the optional fields (all that should be created).
    if 'quality' in EXTRA_QUESTIONS:
        QUALITY_NOISY = 0
        QUALITY_CLEAR = 1
        QUALITY_CHOICES = (('0', 'noisy'),
                           (QUALITY_NOISY, 'noisy'),
                           ('1', 'clear'),
                           (QUALITY_CLEAR, 'clear'))
        quality = models.CharField(max_length=1,
                                   choices=QUALITY_CHOICES,
                                   default=1)
        qual_tpt = ' q: {q};'
    else:
        qual_tpt = ''
    if 'accent' in EXTRA_QUESTIONS:
        accent = models.CharField(max_length=100, blank=True, default="")
        acc_tpt = ' acc: {acc};'
    else:
        acc_tpt = ''
    if 'offensive' in EXTRA_QUESTIONS:
        offensive = models.BooleanField(default=False)
        off_tpt = ' off: {off};'
    else:
        off_tpt = ''
    # uni_tpt: template for self.__unicode__
    uni_tpt = ('(u: {{u}}; saved: {{ds}};{q_tpt}{acc_tpt}{off_tpt} dg: {{dg}})'
               .format(q_tpt = qual_tpt, acc_tpt = acc_tpt, off_tpt = off_tpt))
    del qual_tpt, acc_tpt, off_tpt

    # Common fields.
    dialogue = models.ForeignKey(Dialogue)
    notes = SizedTextField(max_length=500, blank=True, default="", rows=3)
    program_version = models.CharField(max_length=40, editable=False)
    date_saved = models.DateTimeField(auto_now_add=True, editable=False)
    date_paid = models.DateTimeField(null=True, blank=True)
    finished = models.BooleanField(default=True)
    user = models.ForeignKey(User, null=True, blank=True)

    def __unicode__(self):
        if self.user is not None:
            username = self.user.username
        else:
            username = 'anonymous'
        return self.uni_tpt.format(u=username,
                                   ds=self.date_saved,
                                   q=self.get_quality_display(),
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
        # This transcription being saved.
        trs = kwargs.pop('instance')
        # Other transcriptions of the same dialogue annotation.
        this_ann_trss = Transcription.objects.filter(
            dialogue_annotation=trs.dialogue_annotation)\
                .exclude(pk=trs.pk)
        # `is_gold = True' shall dictate values for `breaks_gold' and
        # `some_breaks_gold'
        if trs.breaks_gold:
            if trs.is_gold:
                # Check whether another transcribed segment from the same
                # annotation breaks gold too.
                other_breaks_gold = this_ann_trss.filter(breaks_gold=True)\
                    .exists()
                # If no other transcription breaks gold, reset their
                # `other_breaks_gold' field and update them in the database.
                if not other_breaks_gold:
                    # Update this transcription's `breaks_gold' field.
                    trs.breaks_gold = False
                    trs.some_breaks_gold = False
                    for ann_trs in this_ann_trss:
                        ann_trs.some_breaks_gold = False
                        ann_trs.save()
                # In any case, this is gold, thus breaks not gold.
                trs.breaks_gold = False
            # If this transcription breaks gold,
            else:
                # make sure all the other in the same dialogue annotation know
                # about it.
                this_ann_trss.filter(some_breaks_gold=False)\
                    .update(some_breaks_gold=True)
                # Update for self.
                trs.some_breaks_gold = True
        # If not trs.breaks_gold,
        else:
            # Check that at least one does break gold or all have
            # some_breaks_gold=False.
            other_breaks_gold = this_ann_trss.filter(breaks_gold=True)\
                .exists()
            if other_breaks_gold:
                return

            some_breaks_gold = (this_ann_trss.filter(some_breaks_gold=True)
                                .exists())
            if some_breaks_gold:
                this_ann_trss.update(some_breaks_gold=False)
                trs.some_breaks_gold = False


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


if USE_CF:
    class CrowdflowerJob(models.Model):
        """
        Maps dialogue prices onto Crowdflower jobs created.
        """
        cents = models.PositiveSmallIntegerField()
        """ price of a dialogue in USD cents """
        job_id = models.CharField(max_length=8,  # CF currently uses 6 chars
                                  unique=True)
        """ ID of the Crowdflower job """
        active = models.BooleanField(default=True)
        """ whether this Crowdflower job is currently in use """
        date_created = models.DateTimeField(auto_now_add=True, editable=False)
        """ date when this job was asked to be created by Django """

        class Meta:
            get_latest_by = 'date_created'

        @classmethod
        def dollars2cents(cls, dollars):
            return int(dollars * 100)

        @classmethod
        def cents2dollars(cls, cents):
            return cents / 100.

        def __unicode__(self):
            return '{job} ({price}c)'.format(job=self.job_id, price=self.cents)
