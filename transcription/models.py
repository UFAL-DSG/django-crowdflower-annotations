#!/usr/bin/env python2
# -*- coding: UTF-8 -*-
import os.path
import lxml.etree as etree
from django.db import models
from django.db.models.signals import post_save, pre_save
from django.contrib.auth.models import User
from settings import CODE_LENGTH, CODE_LENGTH_EXT, CONVERSATION_DIR, \
    SESSION_FNAME, XML_AUTHOR_ATTR, XML_DATE_ATTR, XML_DATE_FORMAT, \
    XML_TRANSCRIPTIONS_ELEM, XML_TRANSCRIPTION_ELEM, \
    XML_TURNNUMBER_ATTR, XML_USERTURN_PATH


class Dialogue(models.Model):
    """Provides the mapping between conversation IDs and corresponding
    dirnames."""
    cid = models.CharField(max_length=40, unique=True, primary_key=True)
    """ conversation ID """
    dirname = models.FilePathField(unique=True)
    """ the original name of the dialogue directory """
    code = models.CharField(max_length=CODE_LENGTH)
    """ check code -- the base """
    code_corr = models.CharField(max_length=CODE_LENGTH_EXT)
    """ check code -- the extension in case of no mismatch with gold items """
    code_incorr = models.CharField(max_length=CODE_LENGTH_EXT)
    """ check code -- the extension in case of a mismatch with gold items """
    transcription_price = models.FloatField(null=True)
    """ price of this dialogue's transcriptions in USD """

    def __unicode__(self):
        return u'({c}: {d})'.format(c=self.cid, d=self.dirname)

    def get_codes(self):
        return self.code, self.code_corr, self.code_incorr


class DialogueAnnotation(models.Model):
    """Represents a single submit of an annotation for a single dialogue."""
    QUALITY_NOISY = 0
    QUALITY_CLEAR = 1
    QUALITY_CHOICES = ((QUALITY_NOISY, 'noisy'), (QUALITY_CLEAR, 'clear'))
    dialogue = models.ForeignKey(Dialogue)
    quality = models.CharField(max_length=1,
                               choices=QUALITY_CHOICES,
                               default=1)
    accent = models.CharField(max_length=100, blank=True, default="")
    offensive = models.BooleanField(default=False)
    notes = models.CharField(max_length=500)
    program_version = models.CharField(max_length=40)
    date_saved = models.DateTimeField(auto_now_add=True)
    date_paid = models.DateTimeField(null=True)


class DialogueTurn(models.Model):
    """An abstract class for one turn in a dialogue."""
    dialogue = models.ForeignKey(Dialogue)
    turn_number = models.PositiveSmallIntegerField()

    class Meta:
        abstract = True


class SystemTurn(DialogueTurn):
    """A system turn, provided with a textual representation of the prompt."""
    text = models.CharField(max_length=255)


class UserTurn(DialogueTurn):
    """A user turn, provided with a path to the recorded sound."""
    wav_fname = models.FilePathField(path=CONVERSATION_DIR,
                                     recursive=True,
                                     unique=True)


class Transcription(models.Model):
    """Transcription of one dialogue turn."""
    user = models.ForeignKey(User)
    text = models.TextField()
    # turn_id = models.SmallIntegerField()
    turn = models.ForeignKey(UserTurn)
    # dialogue = models.ForeignKey(Dialogue)
    dialogue_annotation = models.ForeignKey(DialogueAnnotation)
    is_gold = models.BooleanField(default=False)
    breaks_gold = models.BooleanField(default=False)
    some_breaks_gold = models.BooleanField(default=False)
    """`some_breaks_gold' says whether any of all the transcriptions for the
    current dialogue from the current user mismatched a gold item """
    date_updated = models.DateTimeField(auto_now=True)

    def __unicode__(self):
        return u'({g}{b}{B} u:{u}, t:{t}, d:{d}, "{trs}")'\
            .format(g=(u"G" if self.is_gold else u"_"),
                    b=(u"b" if self.some_breaks_gold else u"_"),
                    B=(u"B" if self.breaks_gold else u"_"),
                    u=self.user,
                    t=self.turn_id,
                    d=self.dialogue_annotation.dialogue.dirname,
                    trs=self.text)

    @staticmethod
    def pre_save(sender, **kwargs):
        """Makes sure that the specified values from the user are
        consistent.

        """
        # Only continue if this is an update -- ignore inserts.
        if kwargs.pop('created'):
            return
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
        dg_dir = os.path.join(CONVERSATION_DIR, cid)
        sess_fname = os.path.join(dg_dir, SESSION_FNAME)
        with open(sess_fname, 'r+') as sess_file:
            sess_xml = etree.parse(sess_file)
        # Find the transcription's element.
        trs_xml = sess_xml.find(("{uturn}[@{turn_attr}='{turn}']"
                                 "{trss}/{trs}[@{auth_attr}='{author}']"
                                 "[@{date_attr}='{date}']").format(
                      uturn=XML_USERTURN_PATH,
                      turn_attr=XML_TURNNUMBER_ATTR,
                      turn=str(trs.turn_id),
                      trss=(("/" + XML_TRANSCRIPTIONS_ELEM)
                            if XML_TRANSCRIPTIONS_ELEM else ""),
                      trs=XML_TRANSCRIPTION_ELEM,
                      auth_attr=XML_AUTHOR_ATTR,
                      author=trs.user.username,
                      date_attr=XML_DATE_ATTR,
                      date=(trs.date_updated.strptime(XML_DATE_FORMAT).rstrip()
                            if XML_DATE_FORMAT else
                            unicode(trs.date_updated))))
        # Update the transcription's element.
        attribs = trs_xml.attrib
        attribs['is_gold'] = '1' if trs.is_gold else '0'
        attribs['breaks_gold'] = '1' if trs.breaks_gold else '0'
        attribs['some_breaks_gold'] = '1' if trs.some_breaks_gold else '0'
        attribs['date_updated'] = \
            (trs.date_updated.strptime(XML_DATE_FORMAT) if XML_DATE_FORMAT
             else unicode(trs.date_updated))
        trs_xml.text = trs.text
        # Write the XML session file.
        with open(sess_fname, 'w') as sess_file:
            sess_file.write(etree.tostring(sess_xml,
                                           pretty_print=True,
                                           xml_declaration=True,
                                           encoding='UTF-8'))


pre_save.connect(Transcription.pre_save, sender=Transcription)
post_save.connect(Transcription.post_save, sender=Transcription)
