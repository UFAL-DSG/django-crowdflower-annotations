#!/usr/bin/python
# -*- coding: UTF-8 -*-

from __future__ import unicode_literals

import codecs
from collections import namedtuple
from datetime import datetime
import hashlib
from itertools import chain
import os
import os.path
import random
import shutil
from subprocess import check_output

from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.db import DatabaseError
from django.db.models import Count
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.template import RequestContext
from django.core.urlresolvers import reverse
from django.views.decorators.csrf import csrf_exempt

import crowdflower
from crowdflower import (collect_judgments, create_job, delete_job,
    fire_gold_hooks, price_class_handler, process_worklog, JsonDialogueUpload,
    record_worker)
import dg_util
import session_xml
from session_xml import (FileNotFoundError, XMLSession, UserTurnAbs_nt)
import settings
from tr_normalisation import trss_match
from transcription.forms import DateRangeForm, FileListForm, TranscriptionForm
if settings.USE_CF:
    from transcription.forms import WorkLogsForm, CreateJobForm, DeleteJobForm
from transcription.models import (Transcription, DialogueAnnotation,
    Dialogue, UserTurn, SystemTurn, SemanticAnnotation)
from util import das_match, get_log_path, group_by, catch_locked_database

# Initialisation.
random.seed()

# Some auxiliary classes.
dgstats_nt = namedtuple('DialogueStats', ['list_filename', 'n_annotated_in',
                                          'n_annotated_out', 'n_clean',
                                          'n_all'])
open_annion_nt = namedtuple('OpenAnnotation', ['ann_str', 'link'])


# Auxiliary functions.
def _hash(s):
    return hashlib.sha1(s).hexdigest()


def finished(request):
    return render(request, "trs/finished.html")


def _gen_codes():
    """
    Generates a random code for a dialogue, to be used in validation of CF
    workers' input.
    """

    code = ''.join(random.choice('0123456789')
                   for _ in xrange(settings.CODE_LENGTH))
    code_corr = ''.join(random.choice('0123456789')
                        for _ in xrange(settings.CODE_LENGTH_EXT))
    code_incorr = code_corr
    while code_incorr == code_corr:
        code_incorr = ''.join(random.choice('0123456789')
                              for _ in xrange(settings.CODE_LENGTH_EXT))
    return (code, code_corr, code_incorr)


def _rand_alnum(length=5):
    alnum = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
    return ''.join(random.choice(alnum) for _ in xrange(length))


def _read_dialogue_turns(dg_data, dirname, with_trss=False, only_order=False):
    """
    Reads system and user turns from an XML session file and saves it
    to the DB.  This function should be called after the dialogue in question
    has been copied into the target directory (one called after its CID).

    Arguments:
        dg_data -- the Django object for the dialogue that should be saved
        dirname -- path towards the directory where related WAV files should be
                   looked for
        with_trss -- should any annotations and transcriptions be read too?
            (default: False)
        only_order -- used to fix the order of turns using the `turn_abs_num'
            datum

    """

    if only_order:
        sys_turns = SystemTurn.objects.filter(dialogue=dg_data)
        user_turns = UserTurn.objects.filter(dialogue=dg_data)

        def _get_uturn(uturn_nt):
            uturn = user_turns.get(turn_number=uturn_nt.turn_number)
            uturn.turn_abs_number = uturn_nt.turn_abs_number
            return uturn

        def _get_systurn(systurn_nt):
            systurn = sys_turns.get(turn_number=systurn_nt.turn_number)
            systurn.turn_abs_number = systurn_nt.turn_abs_number
            return systurn
    else:

        def _get_uturn(uturn_nt):
            return UserTurn(dialogue=dg_data,
                            turn_number=turnnum,
                            turn_abs_number=uturn_nt.turn_abs_number,
                            wav_fname=wav_path,
                            asr_hyp=uturn_nt.asr_hyp,
                            slu_hyp=uturn_nt.slu_hyp)

        def _get_systurn(systurn_nt):
            return SystemTurn(dialogue=dg_data,
                              turn_number=systurn_nt.turn_number,
                              turn_abs_number=systurn_nt.turn_abs_number,
                              text=systurn_nt.text)

    with XMLSession(dg_data.cid) as session:

        # Save all the turns as database objects.
        uturns = list()
        for turn_nt in session.iter_turns():
            # Take special care to not overwrite user turns with other user
            # turns with a duplicate turn number (known fault of some XML
            # logs).
            if isinstance(turn_nt, UserTurnAbs_nt):
                if turn_nt.wav_fname is not None:
                    turnnum = turn_nt.turn_number
                    # Do not override turns saved earlier.
                    if (turnnum < len(uturns) and
                            uturns[turnnum] is not None):
                        continue

                    # Create the user turn object.
                    wav_path = os.path.join(dirname, turn_nt.wav_fname)
                    uturn = _get_uturn(turn_nt)

                    # Prepare the `uturns' list for storing the new user
                    # turn.
                    while turnnum > len(uturns):
                        uturns.append(None)

                    # Save the user turn object.
                    uturns.append(uturn)
                    assert (uturns[turnnum] == uturn)
                    uturn.save()
            else:
                _get_systurn(turn_nt).save()

        if only_order:
            return

        # If transcriptions should be read and saved as well,
        if with_trss:
            dummy_user = None

            # Iterate over all dialogue annotations.
            for ann_el in session.iter_annotations():
                # Retrieve all properties of the dialogue annotation
                # object.
                notes = ('' if ann_el.text is None
                         else ann_el.text.strip())
                program_version = ann_el.get('program_version')
                ann_users = User.objects.filter(
                    username=ann_el.get('user'))
                if ann_users.exists():
                    ann_user = ann_users[0]
                else:
                    ann_user = dummy_user

                ann_props = {'dialogue': dg_data,
                             'notes': notes,
                             'user': ann_user,
                             'program_version': program_version}

                if 'accent' in settings.EXTRA_QUESTIONS:
                    accent_str = ann_el.get('accent')
                    accent = ("" if accent_str == 'native' else accent_str)
                    ann_props['accent'] = accent
                if 'offensive' in settings.EXTRA_QUESTIONS:
                    offensive = (ann_el.get("offensive") == "True")
                    ann_props['offensive'] = offensive
                if 'quality' in settings.EXTRA_QUESTIONS:
                    quality = (DialogueAnnotation.QUALITY_CLEAR
                               if ann_el.get('quality') == 'clear'
                               else DialogueAnnotation.QUALITY_NOISY)
                    ann_props['quality'] = quality

                date_saved = session.parse_datetime(ann_el.get('date_saved'))

                # Check whether this object has been imported already.
                if not DialogueAnnotation.objects.filter(
                        date_saved=date_saved, **ann_props):
                    # Save the dialogue annotation.
                    dg_ann = DialogueAnnotation(**ann_props)
                    dg_ann.save()

                    # Find all transcriptions that belong to this dialogue
                    # annotation and save them as database objects.
                    for turnnum, trs_el in session.iter_transcriptions(
                            ann_el):
                        i_gold = (trs_el.get('is_gold') != '0')
                        b_gold = (trs_el.get('breaks_gold') != '0')
                        sb_gold = (trs_el.get('some_breaks_gold') != '0')
                        Transcription(text=trs_el.text,
                                      turn=uturns[turnnum],
                                      dialogue_annotation=dg_ann,
                                      is_gold=i_gold,
                                      breaks_gold=b_gold,
                                      some_breaks_gold=sb_gold).save()


# TODO Move elsewhere (dg_util? models?).
def _create_turn_dicts(dialogue, dg_ann=None):
    """An auxiliary function for gathering important data about dialogue turns
    for use in the transcription form.

    Returns a list of dictionaries, one per turn, to be used with the
    `transcribe.html' template.  The turns are numbered (key `turn_number') but
    this numbering is only for purposes of the template. It does NOT correspond
    to the turn database objects' turn_number attribute.

    Arguments:
        dialogue ... the Dialogue object for whose turns to build the
                     dictionary
        dg_ann   ... a DialogueAnnotation object to use to fill in initial
                     values (default: None)

    """

    _using_slu = 'slu' in settings.TASKS

    transcriptions = None
    last_transcribed = -1
    if dg_ann is not None:
        transcriptions = (Transcription.objects
                          .filter(dialogue_annotation=dg_ann))
        if transcriptions:
            last_transcribed = max(trs.turn.turn_number
                                   for trs in transcriptions)

    uturns = UserTurn.objects.filter(dialogue=dialogue)
    systurns = SystemTurn.objects.filter(dialogue=dialogue)
    max_turn_num = max(max(uturn.turn_abs_number for uturn in uturns) if uturns else 0,
                       max(sturn.turn_abs_number for sturn in systurns) if systurns else 0)

    # Transform data from DialogueTurn objects into dicts.
    turns = [dict() for _ in xrange(max_turn_num)]
    for systurn in systurns:
        # Skip over empty system utterances.
        if systurn.text:
            turns[systurn.turn_abs_number - 1].update(prompt=systurn.text,
                                                      has_rec=False)
    trss_uptoprev = bool(transcriptions)
    trss_uptothis = bool(transcriptions)
    for uturn in uturns:
        # Find the relevant part of the WAV file path.
        seclast_slash = uturn.wav_fname.rfind(
            os.sep, 0, uturn.wav_fname.rfind(os.sep))
        wav_fname_rest = uturn.wav_fname[seclast_slash:]
        # Find if an existing transcription is available for this turn.
        initial_text = ''
        if transcriptions:
            turn_trss = transcriptions.filter(turn=uturn)
            if turn_trss:
                assert len(turn_trss) == 1
                initial_text = turn_trss[0].text
            if uturn.turn_number > last_transcribed:
                trss_uptothis = False
        # SLU
        if _using_slu:
            # Get the DAIs and their textual representation for the SLU
            # hypothesis for this turn.
            if uturn.slu_hyp:
                dais = uturn.slu_hyp.split('&')
                dais_txts = [(dai, settings.dai2text(dai)) for dai in dais]
            else:
                dais_txts = ()
        # Update the last system turn unless it already contains data about the
        # user's utterance.
        prev_turn_idx = uturn.turn_abs_number - 1
        # ...The "-1" is for the different base for indexing.
        for turn_idx in xrange(prev_turn_idx, -1, -1):
            prev_turn = turns[turn_idx]
            # As soon as the last preceding non-empty turn is found,
            if prev_turn:
                # Check whether it has its corresponding user turn yet.
                # If yes,
                if prev_turn['has_rec']:
                    # Put this new user turn to its original index.
                    prev_turn_idx = uturn.turn_abs_number - 1
                # If the last preceding turn is a system turn without a user
                # turn assigned,
                else:
                    # Merge this new user turn to the preceding system turn.
                    prev_turn_idx = turn_idx
                break
        turn_dict = turns[prev_turn_idx]
        turn_dict.update(rec=wav_fname_rest,
                         has_rec=True,
                         uturn_number=uturn.turn_number,
                         initial_text=initial_text,
                         unfold=trss_uptoprev)
        if _using_slu:
            turn_dict['dais_txts'] = dais_txts
        trss_uptoprev = trss_uptothis

    # Number the turns.
    turns = filter(None, turns)
    for turn_number, turn in enumerate(turns, start=1):
        turn['turn_number'] = turn_number
        turn['dbl_turn_num'] = 2 * turn_number
    # Return.
    return turns


def _delete_old_anns():
    sessions_earliest_start = datetime.now() - settings.SESSION_EXPIRED
    old_anns = DialogueAnnotation.objects.filter(
        finished=False,
        date_saved__lte=sessions_earliest_start)
    old_anns.delete()


def _find_free_cids(user=None):
    """
    Finds dialogues that are still free to be annotated by `user`.
    """
    # Count which dialogues do not have the full required number of
    # transcriptions.
    if settings.MAX_ANNOTATIONS_PER_INPUT is None:
        cids_done = set()
    else:
        _max_annions = settings.MAX_ANNOTATIONS_PER_INPUT  # shorthand
        dg_ann_counts = (DialogueAnnotation.objects
                         .annotate(Count('dialogue'))
                         .filter(dialogue__count__gte=_max_annions))
        cids_done = set(ann.dialogue.cid for ann in dg_ann_counts)

    # If being annotated by this user does not imply the dialogue was already
    # included in the above query results,
    filter_out_by_user = (user is not None and
                          (settings.MAX_ANNOTATIONS_PER_INPUT is None or
                           settings.MAX_ANNOTATIONS_PER_INPUT > 1))
    if filter_out_by_user:
        if 'asr' in settings.TASKS:
            # Exclude dialogues annotated by this user explicitly.
            trss_done = Transcription.objects.filter(
                dialogue_annotation__user=user)
            cids_done.update(trs.dialogue_annotation.dialogue.cid
                             for trs in trss_done)
        elif 'slu' in settings.TASKS:
            # Exclude dialogues annotated by this user explicitly.
            anns_done = SemanticAnnotation.objects.filter(
                dialogue_annotation__user=user)
            cids_done.update(sem_ann.dialogue_annotation.dialogue.cid
                             for sem_ann in anns_done)

    cids_todo = set(Dialogue.objects.values_list('cid', flat=True)) - cids_done
    return cids_todo


def _find_open_anns(user):
    return DialogueAnnotation.objects.filter(user=user, finished=False)


def _get_annotation_link(dg_ann):
    cid = dg_ann.dialogue.cid
    base_url = reverse('transcribe')
    return '{base}?cid={cid}'.format(base=base_url, cid=cid)


@login_required
@catch_locked_database
def open_annions(request):
    _delete_old_anns()
    open_annions = _find_open_anns(request.user)
    anns_sorted = sorted(open_annions, key=lambda ann: ann.date_saved)
    anns_dicts = [open_annion_nt(ann_str=unicode(ann),
                                 link=_get_annotation_link(ann))
                  for ann in anns_sorted]
    response = render(request,
                      'trs/open_annions.html',
                      {'open_annions': anns_dicts},
                      context_instance=RequestContext(request))
    return response


@catch_locked_database
def transcribe(request):

    success = None  # whether annotation data have been successfully stored
    cookie_value = None  # value for the transcriber-tracking cookie
    user_anon = not request.user.is_authenticated()

    # If the form has been submitted,
    if request.method == "POST":
        # Check if the transcriber is submitting or just saving a draft.
        finished = 'send' in request.POST

        # Re-create the form object.
        cid = request.POST['cid']
        try:
            dg_data = Dialogue.objects.get(cid=cid)
        except Dialogue.DoesNotExist:
            response = render(request, "trs/nosuchcid.html")
            if settings.USE_CF:
                # NOTE Perhaps not needed after all...
                response['X-Frame-Options'] = 'ALLOWALL'
            return response
        dg_codes = dg_data.get_codes()
        uturns = UserTurn.objects.filter(dialogue=dg_data)
        # Some dialogues have no records of the user whatsoever. If this
        # dialogue had the user saying anything, index the user turns.
        if uturns:
            # uturns_list :: [UserTurn.turn_number -> (None or userturn)]
            uturns_list = [None] * max(uturn.turn_number
                                       for uturn in uturns)
            for uturn in uturns:
                uturns_list[uturn.turn_number - 1] = uturn

            # turn_dicts :: [<template turn number> -> <turn dict>]
            # This is a dense list, no member is None.
            # NOTE that we only consider those user turns that reference
            # a recording of what was said.  This implies that not even
            # semantics can be transcribed for user turns without recordings
            # (where the correct DAT is always 'null()').
            turn_dicts = _create_turn_dicts(dg_data)

            # paired_nums :: [<index to `turn_dicts'>] only for user turns that
            # have a recording to be transcribed
            paired_nums = [tpt_turn_number
                           for tpt_turn_number, turn_dict
                           in enumerate(turn_dicts, start=1)
                           if turn_dict['has_rec']]
        else:
            turn_dicts = None
        form = TranscriptionForm(request.POST, cid=cid, turn_dicts=turn_dicts,
                                 trs_required=finished)

        if form.is_valid():
            dummy_user = None

            # Create the DialogueAnnotation object and save it into DB.
            dg_ann = None
            ex_trss = None
            if not user_anon:
                open_dg_ann = DialogueAnnotation.objects.filter(
                    user=request.user, dialogue=dg_data, finished=False)
                if open_dg_ann.exists():
                    assert len(open_dg_ann) == 1
                    dg_ann = open_dg_ann[0]
                    dg_ann.finished = finished
                    ex_trss = (Transcription.objects
                               .filter(dialogue_annotation=dg_ann))

            if dg_ann is None:
                dg_ann = DialogueAnnotation()
                dg_ann.dialogue = dg_data

            dg_ann.program_version = unicode(check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=settings.PROJECT_DIR).rstrip('\n'))
            if 'quality' in settings.EXTRA_QUESTIONS:
                dg_ann.quality = (DialogueAnnotation.QUALITY_CLEAR if
                                  request.POST['quality'] == 'clear'
                                  else DialogueAnnotation.QUALITY_NOISY)
            if 'accent' in settings.EXTRA_QUESTIONS:
                dg_ann.accent = ("" if request.POST['accent'] == 'native'
                                 else form.cleaned_data['accent_name'])
            if 'offensive' in settings.EXTRA_QUESTIONS:
                dg_ann.offensive = bool(request.POST['offensive'] == 'yes')
            dg_ann.notes = form.cleaned_data['notes']
            if user_anon:
                # A dummy user.
                dg_ann.user = dummy_user
            else:
                dg_ann.user = request.user
            dg_ann.save()

            # Read the XML session file.
            with XMLSession(cid) as session:

                if not uturns:
                    mismatch = False
                else:
                    # Get or set the transcriber ID cookie.
                    cookie_name = settings.TRANSCRIBER_ID_COOKIE
                    if cookie_name not in request.COOKIES:
                        if dg_ann.user is not dummy_user:
                            cookie_value = 'user:{name}'.format(
                                name=dg_ann.user.username)
                        else:
                            n_anns = sum(1 for _ in session.iter_annotations())
                            rand = _rand_alnum(4)
                            cookie_value = '{cid}{rand}_{n_anns}'.format(
                                **locals())
                    else:
                        cookie_value = request.COOKIES[cookie_name]
                    # Insert dialogue annotations into the XML.
                    session.add_annotation(
                        dg_ann, **{settings.TRANSCRIBER_ID_ATTR: cookie_value})
                    # Create Transcription objects and save them into DB.
                    if 'asr' in settings.TASKS:
                        # trss :: [UserTurn.turn_number ->
                        #          (None or transcription)]
                        trss = [None] * len(uturns_list)
                    if 'slu' in settings.TASKS:
                        # sem_anns :: [UserTurn.turn_number ->
                        #              (None or semantic annotation)]
                        sem_anns = [None] * len(uturns_list)
                        checklist = filter(
                            lambda name: name.startswith("check_"),
                            request.POST)

                    for tpt_turn_number in paired_nums:
                        turn_dict = turn_dicts[tpt_turn_number - 1]
                        turn_number = turn_dict['uturn_number']
                        assert turn_dict['has_rec']

                        if 'asr' in settings.TASKS:
                            # Find an existing or create a new Transcription.
                            trs = None
                            uturn = uturns_list[turn_number - 1]
                            if ex_trss:
                                ex_turn_trss = ex_trss.filter(turn=uturn)
                                if ex_turn_trss:
                                    assert len(ex_turn_trss) == 1
                                    trs = ex_turn_trss[0]
                            if trs is None:
                                trs = Transcription()

                            # Retrieve the ASR transcription.
                            trss[turn_number - 1] = trs
                            trs.text = form.cleaned_data[
                                'trs_{0}'.format(tpt_turn_number)]
                            trs.turn = uturn
                            trs.dialogue_annotation = dg_ann

                        if 'slu' in settings.TASKS:
                            # Retrieve the SLU annotation.
                            sem_ann = Transcription()
                            sem_anns[turn_number - 1] = sem_ann
                            # Get a string representation of the DA.
                            dai_strs = list()
                            newdat_prefix = 'newdat_{turn}_'.format(
                                turn=tpt_turn_number)
                            newdat_names = filter(
                                lambda name: name.startswith(newdat_prefix),
                                request.POST)
                            # XXX Use a function from Alex for this. (We might
                            # want to have the DAIs within the DA ordered, for
                            # example.)
                            for dat_name in newdat_names:
                                coords = dat_name[len('newdat_'):]
                                checked_name = "check_{coo}".format(coo=coords)
                                if (request.POST['newdat_{0}'.format(coords)]
                                        and checked_name in checklist):
                                    dat_str = request.POST[dat_name]
                                    slot_str = request.POST.get(
                                        'slot_{coo}'.format(coo=coords), '')
                                    val_str = request.POST.get(
                                        'val_{coo}'.format(coo=coords), '')
                                    if val_str:
                                        dai_tpt = '{dat}({name}={val})'
                                    else:
                                        dai_tpt = '{dat}({name})'
                                    dai_strs.append(dai_tpt.format(
                                        dat=dat_str,
                                        name=slot_str,
                                        val=val_str))
                            sem_ann.da_str = '&'.join(dai_strs)
                            sem_ann.dialogue_annotation = dg_ann

                    # Check the form against any gold items.  If all are OK,
                    # return one code; if not, return another.
                    mismatch = False

                    # - Check transcriptions (ASR).
                    if 'asr' in settings.TASKS:
                        asr_mismatch = False
                        gold_trss = Transcription.objects.filter(
                            dialogue_annotation__dialogue=dg_data,
                            is_gold=True)
                        gold_trss = group_by(gold_trss, ('turn', ))
                        for (turn, ), turn_gold_trss in gold_trss.iteritems():
                            submismatch = True
                            trs = trss[turn.turn_number - 1]
                            for gold_trs in turn_gold_trss:
                                if trss_match(
                                        trs, gold_trs,
                                        max_char_er=settings.MAX_CHAR_ER):
                                    submismatch = False
                                    break
                            if submismatch:
                                mismatch = asr_mismatch = True
                                trs.breaks_gold = True

                    # - Check semantic annotations (SLU).
                    if 'slu' in settings.TASKS:
                        slu_mismatch = False
                        gold_anns = SemanticAnnotation.objects.filter(
                            dialogue_annotation__dialogue=dg_data,
                            is_gold=True)
                        gold_anns = group_by(gold_anns, ('turn', ))
                        for (turn, ), turn_gold_anns in gold_anns.iteritems():
                            submismatch = True
                            ann = sem_anns[turn.turn_number - 1]
                            for gold_trs in turn_gold_trss:
                                if das_match(trs, gold_trs):
                                    submismatch = False
                                    break
                            if submismatch:
                                mismatch = slu_mismatch = True
                                ann.breaks_gold = True

                    # Update transcriptions in the light of their comparison to
                    # gold transcriptions, and save them both into the
                    # database, and to the XML.
                    for tpt_turn_number in paired_nums:
                        turn_dict = turn_dicts[tpt_turn_number - 1]
                        turn_number = turn_dict['uturn_number']
                        assert turn_dict['has_rec']
                        if 'asr' in settings.TASKS:
                            trs = trss[turn_number - 1]
                            trs.some_breaks_gold = asr_mismatch
                            trs.save()
                            # Reflect the transcription in the XML.
                            session.add_transcription(trs)
                        if 'slu' in settings.TASKS:
                            sem_ann = sem_anns[turn_number - 1]
                            sem_ann.some_breaks_gold = slu_mismatch
                            sem_ann.save()
                            # Reflect the transcription in the XML.
                            session.add_sem_annotation(sem_ann)

            context = dict()

            # If working with Crowdflower,
            if finished and settings.USE_CF:
                # Render a page showing the dialogue code.
                context['code'] = dg_codes[0] + (dg_codes[2] if mismatch else
                                                 dg_codes[1])
                response = render(request,
                                  "trs/code.html",
                                  context,
                                  context_instance=RequestContext(request))
                response.set_cookie(cookie_name, cookie_value,
                                    max_age=settings.COOKIES_MAX_AGE,
                                    path=settings.APP_PATH)
                return response
            # Else, if working locally, continue to serving a blank form.
            else:
                success = True

        # If the form is not valid,
        else:
            success = False

            # Touch the current DialogueAnnotation.
            DialogueAnnotation.objects.filter(
                user=request.user, dialogue=dg_data).update(finished=False)

            # Populate the context with data from the previous dialogue (form).
            context = settings.TRANSCRIBE_EXTRA_CONTEXT
            context.update(request.POST)
            context['success'] = str(success)
            context['form'] = form
            context['DOMAIN_URL'] = settings.DOMAIN_URL
            context['APP_PORT'] = settings.APP_PORT
            context['APP_PATH'] = settings.APP_PATH

            response = render(request,
                              "trs/transcribe.html",
                              context,
                              context_instance=RequestContext(request))
            if settings.USE_CF:
                # NOTE Perhaps not needed after all...
                response['X-Frame-Options'] = 'ALLOWALL'
            return response

    # If a blank form is to be served:
    # Find the dialogue to transcribe.
    dg_data = None
    cid = None if request.method == 'POST' else request.GET.get("cid", None)

    # If a specific CID was asked for,
    if cid is not None:
        # Find the corresponding Dialogue object in the DB.
        try:
            dg_data = Dialogue.objects.get(cid=cid)
        except Dialogue.DoesNotExist:
            response = render(request, "trs/nosuchcid.html")
            if settings.USE_CF:
                # NOTE Perhaps not needed after all...
                response['X-Frame-Options'] = 'ALLOWALL'
            return response
    # If an anonymous user is asking for a dialogue without a specific CID,
    elif user_anon:
        # Don't show any dialogues to these anonymous users.
        if request.user.is_anonymous():
            return HttpResponseRedirect("finished")

    assert cid is None or dg_data is not None

    # Try to find open annotations (sessions) if the user is logged in.
    open_annions = None
    cur_annion = None
    if not user_anon:
        if cid is None:
            # Find a suitable dialogue to transcribe.
            # Try using the last started annotation of this user.
            open_annions = _find_open_anns(request.user)
            if open_annions.exists():
                cur_annion = open_annions[0]
                dg_data = cur_annion.dialogue
                cid = dg_data.cid

            # If there is no open annotation for this user, find a dialogue
            # that is free to annotate.
            else:
                # Start by deleting old open transcriptions.
                _delete_old_anns()

                # Find free dialogues for this user.
                cids_todo = _find_free_cids(request.user)

                # Serve him the next free dialogue if there is one, else tell
                # him he is finished.
                try:
                    cid = cids_todo.pop()
                except KeyError:
                    return HttpResponseRedirect("finished")
                dg_data = Dialogue.objects.get(cid=cid)

        else:  # Known user, CID specified => dg_data has been initialized
            # Find if there is a suitable open dialogue annotation.
            open_annions = _find_open_anns(request.user)
            this_dg_annions = open_annions.filter(dialogue=dg_data)
            cur_annion = this_dg_annions[0] if this_dg_annions else None

        # Create or refresh the current DialogueAnnotation.
        if open_annions:
            open_annions.update(finished=False)
        else:
            cur_annion = DialogueAnnotation(user=request.user,
                                            dialogue=dg_data,
                                            finished=False)
            cur_annion.save()

    assert not open_annions or cur_annion is not None

    # Prepare the data about turns into a form suitable for the template.
    turn_dicts = _create_turn_dicts(dg_data, cur_annion)

    context = settings.TRANSCRIBE_EXTRA_CONTEXT
    context['success'] = str(success)
    context['turns'] = turn_dicts
    context['ready_to_submit'] = all(turn['initial_text']
                                     for turn in turn_dicts)
    context['dbl_num_turns'] = 2 * len(turn_dicts)
    context['codes'] = dg_data.get_codes()
    context['form'] = TranscriptionForm(cid=cid, turn_dicts=turn_dicts)

    # SLU-specific.
    if 'slu' in settings.TASKS:
        # TODO Rename to something more telling.
        set1 = set.union(set(settings.nullary_dat),
                         set(settings.unary_dat_with_slot))
        set2 = set.union(set(settings.unary_dat_with_value),
                         set(settings.binary_dat))
        context['all_dat'] = set1 | set2
        context['nul_dat'] = settings.nullary_dat
        context['unar_with_slot'] = settings.unary_dat_with_slot
        context['unar_with_value'] = settings.unary_dat_with_value
        context['bin_dat'] = settings.binary_dat
        context['slot'] = settings.name_of_slot

    # Add selected config variables.
    context['DOMAIN_URL'] = settings.DOMAIN_URL
    context['APP_PORT'] = settings.APP_PORT
    context['APP_PATH'] = settings.APP_PATH
    context['DEBUG'] = settings.DEBUG
    context['USE_ACCORDION'] = (settings.USE_ACCORDION
                                and 'asr' in settings.TASKS)
    context['TASKS'] = settings.TASKS
    response = render(request,
                      "trs/transcribe.html",
                      context,
                      context_instance=RequestContext(request))
    if settings.USE_CF:
        # NOTE Perhaps not needed after all...
        response['X-Frame-Options'] = 'ALLOWALL'
    if cookie_value is not None:
        response.set_cookie(cookie_name, cookie_value,
                            max_age=settings.COOKIES_MAX_AGE,
                            path=settings.APP_PATH)

    return response


@login_required
def home(request):
    return render(request, "trs/home.html")


@login_required
@user_passes_test(lambda u: u.is_staff)
def import_dialogues(request):
    # Check whether the form is yet to be served.
    if not request.GET:
        return render(request, "trs/import.html")

    # Initialisation.
    session_missing = []
    session_empty = []
    copy_failed = []
    save_failed = []
    save_price_failed = []
    dg_existed = []
    dg_updated = []
    count = 0   # number of successfully imported dialogues

    # Read variables from the form.
    csv_fname = request.GET.get('csv_fname', '')
    if not csv_fname:
        csv_fname = os.path.join(settings.CONVERSATION_DIR, 'new_tasks.csv')
    else:
        if not os.path.isabs(csv_fname):
            csv_fname = os.path.join(settings.CONVERSATION_DIR, csv_fname)

    dirlist_fname = os.path.abspath(request.GET['list_fname'])
    with_trss = request.GET.get('with_trss', False) == 'on'
    only_order = request.GET.get('only_order', False) == 'on'
    ignore_exdirs = request.GET.get('ignore_exdirs', False) == 'on'
    upload_to_cf = settings.USE_CF and request.GET.get('upload', False) == 'on'

    # Make sure the output file's directory exists.
    csv_dirname = os.path.dirname(csv_fname)
    if not os.path.isdir(csv_dirname):
        os.makedirs(csv_dirname)

    # Do the import.
    with open(dirlist_fname, 'r') as dirlist_file, \
            open(csv_fname, 'w') as csv_file:
        # Prepare the JSON upload data, and the CSV header.
        if upload_to_cf:
            json_data = JsonDialogueUpload()
        csv_file.write('cid,code,code_gold\n')
        # Process the dialogue files.
        for line in dirlist_file:
            src_fname = line.rstrip().rstrip(os.sep)
            dirname = os.path.basename(src_fname)

            # Check that that directory contains the required session XML file.
            try:
                sess_fname = XMLSession.find_session_fname(src_fname)
            except FileNotFoundError:
                session_missing.append(src_fname)
                continue
            # Check that there are enough user turns in the session.
            # As a by-product, collect names of audio files referred to from
            # the session.
            rec_fnames = list()
            with XMLSession(fname=sess_fname, mode='r') as session:
                n_empty_turns = 0
                for uturn_num, uturn_nt in enumerate(session.iter_uturns(),
                                                     start=1):
                    if not uturn_nt.wav_fname:
                        n_empty_turns += 1
                    else:
                        rec_fnames.append(uturn_nt.wav_fname)
                if uturn_num - n_empty_turns < settings.MIN_TURNS:
                    session_empty.append(src_fname)
                    continue

            # Generate CID.
            cid = _hash(dirname)
            # Check that this CID does not collide with a hash for another
            # dirname.  This is a crude implementation of hashing with
            # replacement.
            same_cid_dgs = Dialogue.objects.filter(cid=cid)
            salt = -1
            while same_cid_dgs and same_cid_dgs[0].dirname != dirname:
                salt += 1
                cid = _hash(dirname + str(salt))
                same_cid_dgs = Dialogue.objects.filter(cid=cid)

            # Copy the dialogue files.
            tgt_fname = os.path.join(settings.CONVERSATION_DIR, cid)
            try:
                # Make the target directory.
                os.mkdir(tgt_fname)
                # Copy the session XML log.
                shutil.copy2(sess_fname, tgt_fname)
                # Copy all the audio needed.
                for rec_fname in rec_fnames:
                    rec_path = os.path.join(src_fname, rec_fname)
                    shutil.copy2(rec_path, tgt_fname)
                # shutil.copytree(src_fname, tgt_fname)
            except:
                if not ignore_exdirs:
                    copy_failed.append(src_fname)
                    continue

            # Create an object for the dialogue and save it in the DB, unless
            # it has been there already.
            if same_cid_dgs:
                # XXX If only updating the absolute turn numbers,
                if only_order:
                    # Do update the order.
                    dg_data = Dialogue.objects.get(cid=cid)
                    _read_dialogue_turns(dg_data, tgt_fname, with_trss,
                                         only_order=True)
                    dg_updated.append(dirname)
                else:
                    dg_existed.append(dirname)

                continue
            # Generate codes and other defining attributes of the dialogue.
            dg_codes = _gen_codes()
            dg_data = Dialogue(cid=cid,
                               code=dg_codes[0],
                               code_corr=dg_codes[1],
                               code_incorr=dg_codes[2],
                               dirname=dirname,
                               list_filename=dirlist_fname)
            try:
                dg_data.save()
            except:
                save_failed.append((dirname, cid))
                continue
            # Read the dialogue turns.
            _read_dialogue_turns(dg_data, tgt_fname, with_trss,
                                 only_order=False)
            # Compute the dialogue price.
            dg_util.update_price(dg_data)
            # Update the dialogue in the DB.
            try:
                dg_data.save()
            except:
                save_price_failed.append((dirname, cid))
                continue

            # Add a record to the CSV for CrowdFlower. (kept for extra safety)
            code_gold = dg_codes[0] + dg_codes[1]
            csv_file.write('{cid},{code},{gold}\n'
                           .format(cid=cid, code=dg_codes[0], gold=code_gold))
            # Add a record to the JSON for CrowdFlower.
            if upload_to_cf:
                json_data.add(dg_data)

            count += 1

    if upload_to_cf:
        cf_ret, cf_msg = json_data.upload()
        if cf_ret is False:
            cf_error = cf_msg
        else:
            cf_error = None
    # Render the response.
    context = dict()
    context['MIN_TURNS'] = settings.MIN_TURNS
    context['session_missing'] = session_missing
    context['session_empty'] = session_empty
    context['copy_failed'] = copy_failed
    context['save_failed'] = save_failed
    context['save_price_failed'] = save_price_failed
    context['dg_existed'] = dg_existed
    context['dg_updated'] = dg_updated
    if upload_to_cf:
        context['cf_upload'] = True
        context['cf_error'] = cf_error
    else:
        context['cf_upload'] = False
    context['csv_fname'] = csv_fname
    context['count'] = count
    context['n_failed'] = (len(session_missing) + len(session_empty)
                           + len(copy_failed) + len(save_failed)
                           + len(save_price_failed) + len(dg_existed)
                           + len(dg_updated))
    return render(request, "trs/imported.html", context)


@login_required
@user_passes_test(lambda u: u.is_staff)
def dialogue_stats(request):
    """Shows how many dialogues have been annotated yet from each filelist."""

    dg_statss = list()  # This will be returned.
    context = dict()    # Context for rendering the template.

    dt_from = dt_to = None

    # If the user specified any dates, try read them.
    if request.method == 'POST':
        form = DateRangeForm(request.POST)
        if form.is_valid():
            dt_from = form.cleaned_data['dt_from']
            dt_to = form.cleaned_data['dt_to']
    else:
        form = DateRangeForm()
    context['form'] = form

    # Prepare the selection criteria for queries.
    lists = Dialogue.objects.values_list('list_filename', flat=True).distinct()
    anned_kwargs = dict()
    if dt_from is not None:
        anned_kwargs['dialogueannotation__date_saved__gt'] = dt_from
    if dt_to is not None:
        anned_kwargs['dialogueannotation__date_saved__lte'] = dt_to
    if not anned_kwargs:
        anned_kwargs['dialogueannotation__isnull'] = False

    # Compute the transcription stats.
    for list_fname in lists:
        list_dgs = Dialogue.objects.filter(list_filename=list_fname)
        anned_dgs = list_dgs.filter(
            dialogueannotation__isnull=False).distinct()
        n_anned = len(anned_dgs)
        n_anned_in_range = len(anned_dgs.filter(**anned_kwargs).distinct())
        n_all = len(list_dgs)
        dg_statss.append(dgstats_nt(list_fname,
                                    n_anned_in_range,
                                    n_anned - n_anned_in_range,
                                    n_all - n_anned,
                                    n_all))

    # Sum up the stats for all lists.
    sums = (sum(dg_stats[idx] for dg_stats in dg_statss)
            for idx in xrange(1, 5))
    dg_statss.append(dgstats_nt('ALL', *sums))

    context['dg_statss'] = dg_statss
    return render(request, 'trs/dialogue-stats.html', context)


@login_required
@user_passes_test(lambda u: u.is_staff)
def delete_list(request):
    """Deletes all dialogues from a single file list from the DB and FS too."""

    # If the user already selected the file list for deletion,
    if request.method == 'POST':
        form = FileListForm(request.POST)
        if form.is_valid():
            # Find which dialogues should be deleted.
            flist = form.cleaned_data['file_list']
            dgs_todelete = Dialogue.objects.filter(list_filename=flist)

            # Try to delete the dialogue directories.
            remaining_dirs = list()  # list of dialogue directories where an
                                     # error occured when deleting them
            for dg in dgs_todelete:
                dg_path = os.path.join(settings.CONVERSATION_DIR, dg.cid)
                try:
                    shutil.rmtree(dg_path)
                except:
                    remaining_dirs.append(dg_path)

            # Delete the dialogues from the database.
            remaining_cids = list()
            # Count some basic statistics of the objects to be deleted.
            n_dgs = len(dgs_todelete)
            dg_anns = dgs_todelete.values_list('dialogueannotation', flat=True)
            n_anns = len(dg_anns)
            try:
                # Delete the dialogues.
                dgs_todelete.delete()
            except DatabaseError:
                # If too many dialogues are selected for deletion, the database
                # may be unable to handle such a long query. Delete the
                # dialogues one by one then.
                n_dgs = 0
                n_anns = 0

                for dg in dgs_todelete:
                    # Count how many annotations this dialogue has.
                    dg_anns = DialogueAnnotation.objects.filter(dialogue=dg)
                    n_dg_anns = len(dg_anns)
                    cid = dg.cid

                    try:
                        dg.delete()
                    except:
                        remaining_cids.append(cid)
                    else:
                        # Count this dialogue and its annotations as deleted.
                        n_dgs += 1
                        n_anns += n_dg_anns
            except:
                remaining_cids = (Dialogue.objects.filter(list_filename=flist)
                                  .values_list('cid', flat=True))
            remaining_cids.sort()

            context = {'n_dgs': n_dgs,
                       'n_anns': n_anns,
                       'remaining_cids': remaining_cids,
                       'remaining_dirs': remaining_dirs}
            return render(request, 'trs/list-deleted.html', context)
        else:
            return render(request, 'trs/delete-list.html', {'form': form})
    else:
        form = FileListForm()
        return render(request, 'trs/delete-list.html', {'form': form})


def temp_test(request):
    # Set up whatever variables you are interested in dumping here.
    assert False


if settings.USE_CF:
    import json

    @login_required
    @user_passes_test(lambda u: u.is_staff)
    def fire_hooks(request):
        # Allow a specific job to be specified as a GET parameter.
        if 'jobid' in request.GET:
            job_ids = [request.GET['jobid']]
        else:
            # If no specific job ID was specified, fire hooks for all jobs.
            job_ids = price_class_handler.get_job_ids()

        for job_id in job_ids:
            fire_gold_hooks(job_id)
        context = {'n_jobs': len(job_ids)}
        return render(request, "trs/hooks-fired.html", context)


    @login_required
    @user_passes_test(lambda u: u.is_staff)
    def reuse_worklogs(request):
        if request.method == 'POST':
            form = WorkLogsForm(request.POST)
            # If the form is valid,
            if form.is_valid():
                # Re-apply the logs.
                logs_by_success = [list() for _ in xrange(4)]
                with open(form.cleaned_data['logs_list_path']) as list_file:
                    for path_line in list_file:
                        log_path = path_line.strip()
                        success = process_worklog(log_path)
                        logs_by_success[success].append(log_path)

                # Compute some auxiliary variables for the template.
                count = sum(map(len, logs_by_success))
                n_failed = count - len(logs_by_success[crowdflower.CF_LOG_OK])
                logs_existed = logs_by_success[crowdflower.CF_LOG_EXISTED]
                logs_no_free_ann = logs_by_success[
                    crowdflower.CF_LOG_NO_FREE_ANN]
                logs_not_applicable = logs_by_success[
                    crowdflower.CF_LOG_NOT_APPLICABLE]
                context = {'count': count,
                           'n_failed': n_failed,
                           'logs_existed': logs_existed,
                           'logs_no_free_ann': logs_no_free_ann,
                           'logs_not_applicable': logs_not_applicable,
                           }
                response = render(request, 'trs/worklogs-reused.html', context,
                                  context_instance=RequestContext(request))

            # If the form was not valid,
            else:
                # Re-render the form.
                context = {'form': form}
                response = render(request, 'trs/reuse-worklogs.html', context,
                                  context_instance=RequestContext(request))
            return response

        # If a new form is to be served,
        else:
            context = {'form': WorkLogsForm()}
            response = render(request, 'trs/reuse-worklogs.html', context,
                              context_instance=RequestContext(request))
            return response


    def fill_in_worker_ids(request):
        ambig_cookies, resolved_cookies, cid_stats = (
            session_xml.fill_in_worker_ids(force=True))
        conflicting_cid_stats = [stats for stats in cid_stats
                                 if stats.n_conflicting]
        n_conflicting = sum(stats.n_conflicting for stats in cid_stats)
        updated_cid_stats = [stats for stats in cid_stats
                             if stats.n_updated]
        n_updated = sum(stats.n_updated for stats in cid_stats)
        kept_empty_cid_stats = [stats for stats in cid_stats
                                if stats.n_kept_empty]
        n_kept_empty = sum(stats.n_kept_empty for stats in cid_stats)
        context = {'ambig_cookies': sorted(ambig_cookies),
                   'resolved_cookies': sorted(resolved_cookies),
                   'n_ambig_both': len(ambig_cookies) + len(resolved_cookies),
                   'cid_stats': sorted(cid_stats),
                   'conflicting_cid_stats': sorted(conflicting_cid_stats),
                   'updated_cid_stats': sorted(updated_cid_stats),
                   'kept_empty_cid_stats': sorted(kept_empty_cid_stats),
                   'n_conflicting': n_conflicting,
                   'n_updated': n_updated,
                   'n_kept_empty': n_kept_empty,
                   }
        response = render(request, 'trs/worker-ids-filled-in.html', context,
                          context_instance=RequestContext(request))
        return response


    @login_required
    @user_passes_test(lambda u: u.is_staff)
    def collect_reports(request):
        # Allow a specific job to be specified as a GET parameter.
        if 'jobid' in request.GET:
            job_ids = [request.GET['jobid']]
        else:
            # If no specific job ID was specified, fire hooks for all jobs.
            job_ids = price_class_handler.get_job_ids()

        # Do the work, collect return statuses and messages.
        success = True
        price_classes_dict = {jobid: int(100 * dollars) for dollars, jobid in
                              price_class_handler.all_price_classes}
        response_tup = namedtuple('ReportItem', ['job_id', 'price', 'failed',
                                                 'msg'])
        response_data = list()

        for job_id in job_ids:
            success_part, msg = collect_judgments(job_id)
            success &= success_part
            response_data.append(
                response_tup(job_id,
                             price_classes_dict.get(job_id, '???'),
                             not success_part,
                             msg))

        # Render the response.
        context = {'success': success,
                   'response_data': response_data}
        return render(request, "trs/reports-collected.html", context)


    @login_required
    @user_passes_test(lambda u: u.is_staff)
    def create_job_view(request):
        # If the form has been submitted,
        if request.method == "POST":
            form = CreateJobForm(request.POST)
            if form.is_valid():
                prices = form.cleaned_data['cents_per_unit']

                # Copy and alter the form data dictionary.
                form_data = {key: val for key, val in
                             form.cleaned_data.iteritems()}
                del form_data['cents_per_unit']

                # Do the work, collect return statuses and messages.
                success = True
                response_tup = namedtuple('ReportItem',
                                          ['price', 'job_id', 'failed', 'msg'])
                response_data = list()
                n_successful = 0

                for price in prices:
                    success_part, msg = create_job(cents_per_unit=price,
                                                   **form_data)
                    # Remember whether job creation was successful for this job
                    # price.
                    success &= success_part
                    n_successful += success_part
                    job_id = msg['id'] if success_part else None
                    response_data.append(
                        response_tup(price,
                                     job_id,
                                     not success_part,
                                     'OK' if success_part else msg))
                    # Log the communication with Crowdflower from job creation.
                    log_path = get_log_path(settings.WORKLOGS_DIR)
                    with codecs.open(log_path, 'w',
                                     encoding='UTF-8') as log_file:
                        log_file.write(str(success_part) + '\n')
                        if success_part:
                            log_file.write(json.dumps(msg))
                        else:
                            log_file.write(msg)

                # Build and render the response.
                context = {'n_jobs': n_successful,
                           'success': success,
                           'response_data': response_data,
                           'form': form,
                           }
                return render(request, "trs/jobs-created.html", context)

            # If the form data were invalid,
            else:
                # Populate context with data from the previous form.
                context = {'form': form}
                response = render(
                    request, "trs/create-jobs.html", context,
                    context_instance=RequestContext(request))
                return response

        # If a new form is to be served,
        else:
            context = {'form': CreateJobForm()}
            response = render(
                request, "trs/create-jobs.html", context,
                context_instance=RequestContext(request))
            return response


    @csrf_exempt
    def log_work(request):
        try:
            signal = request.POST.get('signal', None)
            # Try: be robust
            # a.k.a. Pokemon exception handling: catch 'em all
            try:
                if signal in ('job_complete', 'unit_complete'):
                    # Save the request data to a log.
                    log_path = get_log_path(settings.WORKLOGS_DIR)
                    with open(log_path, 'w') as log_file:
                        log_file.write(repr(request.POST.dict())
                                       if hasattr(request, 'POST') else 'None')
            except Exception:
                pass
            # Record the request to a session XML file.
            if signal == 'unit_complete':
                record_worker(request.POST)
            elif signal == 'job_complete':
                job_id = request.POST['payload']['id']
                fire_gold_hooks(job_id)
                collect_judgments(job_id)
        finally:
            return HttpResponse(status=200)


    @login_required
    @user_passes_test(lambda u: u.is_staff)
    def delete_job_view(request):
        # If the form has been submitted,
        if request.method == "POST":
            form = DeleteJobForm(request.POST)
            if form.is_valid():
                # Process the form data.
                old_job_ids = form.cleaned_data['old_job_ids']
                active_job_ids = form.cleaned_data['active_job_ids']

                # Do the work, collect return statuses and messages.
                success = True
                price_classes_dict = {
                    jobid: int(100 * dollars) for dollars, jobid in
                    price_class_handler.all_price_classes}
                response_tup = namedtuple('ReportItem',
                                          ['job_id', 'price', 'failed', 'msg'])
                response_data = list()
                n_successful = 0

                for job_id in chain(old_job_ids, active_job_ids):
                    if not form.cleaned_data[job_id]:
                        continue
                    success_part, msg = delete_job(job_id)
                    # Remember whether this job was successfully deleted.
                    success &= success_part
                    n_successful += success_part
                    response_data.append(
                        response_tup(job_id,
                                     price_classes_dict[job_id],
                                     not success_part,
                                     'OK' if success_part else msg))
                    # Log the communication with Crowdflower from job deletion.
                    log_path = get_log_path(settings.WORKLOGS_DIR)
                    with codecs.open(log_path, 'w',
                                     encoding='UTF-8') as log_file:
                        log_file.write(str(success_part) + '\n')
                        if success_part:
                            log_file.write(json.dumps(msg))
                        else:
                            log_file.write(msg)

                # Build and render the response.
                context = {'n_jobs': n_successful,
                           'success': success,
                           'response_data': response_data,
                           'form': form,
                           }
                return render(request, "trs/jobs-deleted.html", context)

            # If the form data were invalid,
            else:
                # Populate context with data from the previous form.
                context = {'form': form}
                response = render(
                    request, "trs/delete-jobs.html", context,
                    context_instance=RequestContext(request))
                return response

        # If a new form is to be served,
        else:
            context = {'form': DeleteJobForm()}
            response = render(
                request, "trs/delete-jobs.html", context,
                context_instance=RequestContext(request))
            return response
