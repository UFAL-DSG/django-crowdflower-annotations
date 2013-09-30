#!/usr/bin/python
# -*- coding: UTF-8 -*-
#
# TODO: User.objects.get_or_create(dummy_user) where appropriate.

from __future__ import unicode_literals

import codecs
from collections import namedtuple
from datetime import datetime
import hashlib
from itertools import chain
import os
import os.path
import random
import re
from subprocess import check_output

from django import forms
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.db.models import Count
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.template import RequestContext
from django.utils.datastructures import SortedDict
from django.views.decorators.csrf import csrf_exempt

import crowdflower
from crowdflower import (collect_judgments, create_job, delete_job,
    default_job_cml_path, fire_gold_hooks, price_class_handler,
    process_worklog, JsonDialogueUpload, record_worker)
import dg_util
from session_xml import (FileNotFoundError, XMLSession, UserTurnAbs_nt,
    SystemTurnAbs_nt)
import settings
# XXX: Beware, this imports the settings from within the `transcription'
# directory. That means that PROJECT_DIR will be APP_ROOT + "/transcription",
# not just APP_ROOT.
from tr_normalisation import trss_match
from transcription.models import Transcription, DialogueAnnotation, \
    Dialogue, UserTurn, SystemTurn
from util import get_log_path, catch_locked_database


def group_by(objects, attrs):
    """Groups `objects' by the values of their attributes `attrs'.

    Returns a dictionary mapping from a tuple of attribute values to a list of
    objects with those attribute values.

    """
    groups = dict()
    for obj in objects:
        key = tuple(getattr(obj, attr) for attr in attrs)
        groups.setdefault(key, []).append(obj)
    return groups


def _hash(s):
    return hashlib.sha1(s).hexdigest()


class TranscriptionForm(forms.Form):
    if 'quality' in settings.EXTRA_QUESTIONS:
        quality = forms.CharField()
    if 'accent' in settings.EXTRA_QUESTIONS:
        accent = forms.CharField()
        accent_name = forms.CharField(required=False)
    if 'offensive' in settings.EXTRA_QUESTIONS:
        offensive = forms.BooleanField(required=False)
    notes = forms.CharField(required=False)

    def __init__(self, *args, **kwargs):
        uturn_ind = kwargs.pop('uturn_ind', None)
        if uturn_ind is None:
            uturn_ind = tuple()
        cid = kwargs.pop('cid', None)
        super(TranscriptionForm, self).__init__(*args, **kwargs)

        self.fields['cid'] = forms.CharField(widget=forms.HiddenInput(),
                                             initial=cid)

        for turn_num, has_rec in enumerate(uturn_ind, start=1):
            if not has_rec:
                continue
            self.fields['trs_{0}'.format(turn_num)] = forms.CharField(
                widget=forms.Textarea(
                    attrs={'style': 'width: 90%', 'rows': '3'}),
                label=turn_num)

    def __unicode__(self):
        import pprint
        return pprint.pformat(self.fields, depth=3)

    def __repr__(self):
        return self.__unicode__()

    def __str__(self):
        return self.__unicode__()


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
            return user_turns.get(turn_number=uturn_nt.turn_number)
        def _get_systurn(systurn_nt):
            return sys_turns.get(turn_number=systurn_nt.turn_number)
    else:
        def _get_uturn(uturn_nt):
            return UserTurn(dialogue=dg_data,
                            turn_number=turnnum,
                            turn_abs_number=uturn_nt.turn_abs_number,
                            wav_fname=wav_path)
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

                # Check whether this object has been imported already.
                if not DialogueAnnotation.objects.filter(**ann_props):
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
def _create_turn_dicts(dialogue):
    """An auxiliary function for gathering important data about dialogue turns
    for use in the transcription form."""
    uturns = UserTurn.objects.filter(dialogue=dialogue)
    systurns = SystemTurn.objects.filter(dialogue=dialogue)
    max_turn_num = max(max(uturn.turn_abs_number for uturn in uturns),
                       max(sturn.turn_abs_number for sturn in systurns))
    # Transform data from DialogueTurn objects into dicts.
    turns = [dict() for _ in xrange(max_turn_num)]
    for systurn in systurns:
        # Throw away empty system utterances.
        if systurn.text:
            turns[systurn.turn_abs_number - 1].update(prompt=systurn.text,
                                                      has_rec=False)
    for uturn in uturns:
        # Find the relevant part of the WAV file path.
        seclast_slash = uturn.wav_fname.rfind(
            os.sep, 0, uturn.wav_fname.rfind(os.sep))
        wav_fname_rest = uturn.wav_fname[seclast_slash:]
        # Update the last system turn unless it already contains data about the
        # user's utterance.
        prev_turn_idx = uturn.turn_abs_number - 1
        # ...The "-1" is for the different base for indexing.
        for turn_idx in xrange(prev_turn_idx, -1, -1):
            prev_turn = turns[turn_idx]
            if prev_turn:
                if prev_turn['has_rec']:
                    prev_turn_idx = uturn.turn_abs_number - 1
                else:
                    prev_turn_idx = turn_idx
                break
        turns[prev_turn_idx].update(rec=wav_fname_rest,
                                    has_rec=True)
    # Number the turns.
    turns = filter(None, turns)
    for turn_number, turn in enumerate(turns, start=1):
        turn['turn_number'] = turn_number
        turn['dbl_turn_num'] = 2 * turn_number
    # Return.
    return turns


@catch_locked_database
def transcribe(request):

    success = None  # whether annotation data have been successfully stored

    # If the form has been submitted,
    if request.method == "POST":
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
            uturns_list = [None] * max(uturn.turn_number
                                       for uturn in uturns)
            for uturn in uturns:
                uturns_list[uturn.turn_number - 1] = uturn
            turn_dicts = _create_turn_dicts(dg_data)
            uturn_ind = [turn['has_rec'] for turn in turn_dicts]
            paired_nums = [paired_num for paired_num, has_rec
                           in enumerate(uturn_ind, start=1)
                           if has_rec]
        else:
            uturn_ind = None
        form = TranscriptionForm(request.POST, cid=cid, uturn_ind=uturn_ind)

        if form.is_valid():
            dummy_user = None

            # Create the DialogueAnnotation object and save it into DB.
            dg_ann = None
            if request.user.is_authenticated():
                open_dg_ann = DialogueAnnotation.objects.filter(
                    user=request.user, dialogue=dg_data, finished=False)
                if open_dg_ann.exists():
                    dg_ann = open_dg_ann[0]
                    dg_ann.finished = True

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
            if request.user.is_authenticated():
                dg_ann.user = request.user
            else:
                # A dummy user.
                dg_ann.user = dummy_user
            dg_ann.save()

            # Read the XML session file.
            with XMLSession(cid) as session:

                if not uturns:
                    mismatch = False
                else:
                    # Insert dialogue annotations into the XML.
                    session.add_annotation(dg_ann)
                    # Create Transcription objects and save them into DB.
                    trss = [None] * len(paired_nums)
                    for turn_num, paired_num in enumerate(paired_nums,
                                                          start=1):
                        turn_dict = turn_dicts[paired_num - 1]
                        if not turn_dict['has_rec']:
                            continue
                        trs = Transcription()
                        trss[turn_num - 1] = trs
                        trs.text = form.cleaned_data[
                            'trs_{0}'.format(paired_num)]
                        trs.turn = uturns_list[turn_num - 1]
                        trs.dialogue_annotation = dg_ann

                    # Check the form against any gold items.  If all are OK,
                    # return one code; if not, return another.
                    gold_trss = Transcription.objects.filter(
                        dialogue_annotation__dialogue=dg_data,
                        is_gold=True)
                    gold_trss = group_by(gold_trss, ('turn', ))
                    mismatch = False
                    for turn, turn_gold_trss in gold_trss.iteritems():
                        submismatch = True
                        trs = trss[turn.turn_number - 1]
                        for gold_trs in turn_gold_trss:
                            if trss_match(trs, gold_trs,
                                          max_char_er=settings.MAX_CHAR_ER):
                                submismatch = False
                                break
                        if submismatch:
                            mismatch = True
                            trs.breaks_gold = True

                    # Update transcriptions in the light of their comparison to
                    # gold transcriptions, and save them both into the
                    # database, and to the XML.
                    for turn_num, paired_num in enumerate(paired_nums,
                                                          start=1):
                        turn_dict = turn_dicts[paired_num - 1]
                        if not turn_dict['has_rec']:
                            continue
                        trs = trss[turn_num - 1]
                        trs.some_breaks_gold = mismatch
                        trs.save()
                        # Reflect the transcription in the XML.
                        session.add_transcription(trs)

            context = dict()

            # If working with Crowdflower,
            if settings.USE_CF:
                # Render a page showing the dialogue code.
                context['code'] = dg_codes[0] + (dg_codes[2] if mismatch else
                                                 dg_codes[1])
                return render(request,
                              "trs/code.html",
                              context,
                              context_instance=RequestContext(request))
            # Else, if working locally, continue to serving a blank form.
            else:
                success = True
        # If the form is not valid,
        else:
            # Touch the current DialogueAnnotation.
            DialogueAnnotation.objects.filter(
                user=request.user, dialogue=dg_data).update(finished=False)

            # Populate the context with data from the previous dialogue (form).
            context = settings.TRANSCRIBE_EXTRA_CONTEXT
            context['app_url'] = settings.APP_URL
            for key, value in request.POST.iteritems():
                context[key] = value
            context['form'] = form
            response = render(request,
                              "trs/transcribe.html",
                              context,
                              context_instance=RequestContext(request))
            if settings.USE_CF:
                # NOTE Perhaps not needed after all...
                response['X-Frame-Options'] = 'ALLOWALL'
            return response

    # If a blank form is to be served:
    open_annions = None

    # Find the dialogue to transcribe.
    dg_data = None
    cid = None if request.method == 'POST' else request.GET.get("cid", None)
    # If the request did not specify the `cid' as a GET parameter,
    if cid is None:
        # Anonymous user cannot be helped.
        if request.user.is_anonymous():
            return HttpResponseRedirect("finished")

        # For a user who is logged in, find a suitable dialogue to transcribe.
        # Try using the last started annotation of this user.
        open_annions = DialogueAnnotation.objects.filter(user=request.user,
                                                         finished=False)
        if open_annions.exists():
            assert len(open_annions) == 1
            dg_data = open_annions[0].dialogue
            cid = dg_data.cid

        # If there is no open annotation for this user, find a dialogue that is
        # free to annotate.
        else:
            # Start by deleting old open transcriptions.
            sessions_earliest_start = datetime.now() - settings.SESSION_EXPIRED
            (DialogueAnnotation.objects.filter(
                finished=False, date_saved__lte=sessions_earliest_start)
                .delete())

            # Count which dialogues have not the full required number of
            # transcriptions.
            if settings.MAX_ANNOTATIONS_PER_INPUT is None:
                cids_done = set()
            else:
                _max_annions = settings.MAX_ANNOTATIONS_PER_INPUT  # shorthand
                dg_ann_counts = DialogueAnnotation.objects.annotate(
                    Count('dialogue')).filter(
                        dialogue__count__gte=_max_annions)
                cids_done = set(ann.dialogue.cid for ann in dg_ann_counts)

            # If being annotated by this user does not imply the dialogue was
            # already included in the above query results,
            if (settings.MAX_ANNOTATIONS_PER_INPUT is None
                    or settings.MAX_ANNOTATIONS_PER_INPUT > 1):
                # Exclude dialogues annotated by this user explicitly.
                trss_done = Transcription.objects.filter(
                    dialogue_annotation__user=request.user)
                cids_done.update(trs.dialogue_annotation.dialogue.cid
                                 for trs in trss_done)
            cids_todo = (set(dg.cid for dg in Dialogue.objects.all())
                         - cids_done)

            # Serve him/her the next free dialogue if there is one, else tell
            # him he is finished.
            try:
                cid = cids_todo.pop()
            except KeyError:
                return HttpResponseRedirect("finished")
            dg_data = Dialogue.objects.get(cid=cid)

    # If `cid' was specified as a GET parameter,
    if dg_data is None:
        # Find the corresponding Dialogue object in the DB.
        try:
            dg_data = Dialogue.objects.get(cid=cid)
        except Dialogue.DoesNotExist:
            response = render(request, "trs/nosuchcid.html")
            if settings.USE_CF:
                # NOTE Perhaps not needed after all...
                response['X-Frame-Options'] = 'ALLOWALL'
            return response

    # Store a new DialogueAnnotation, unless the user is anonymous.
    if open_annions is not None and open_annions.exists():
        open_annions.update(finished=False)
    elif not request.user.is_anonymous():
        DialogueAnnotation(user=request.user,
                           dialogue=dg_data,
                           finished=False).save()

    # Prepare the data about turns into a form suitable for the template.
    turns = _create_turn_dicts(dg_data)
    uturn_ind = [turn['has_rec'] for turn in turns]

    context = settings.TRANSCRIBE_EXTRA_CONTEXT
    context['app_url'] = settings.APP_URL
    context['success'] = str(success)
    context['turns'] = turns
    context['dbl_num_turns'] = 2 * len(turns)
    context['codes'] = dg_data.get_codes()
    context['form'] = TranscriptionForm(cid=cid, uturn_ind=uturn_ind)
    response = render(request,
                      "trs/transcribe.html",
                      context,
                      context_instance=RequestContext(request))
    if settings.USE_CF:
        # NOTE Perhaps not needed after all...
        response['X-Frame-Options'] = 'ALLOWALL'

    return response


@login_required
def home(request):
    context = {'USE_CF': settings.USE_CF}
#                'USE_JOBFILE': price_class_handler.uses_jobfile}
    return render(request, "trs/home.html", context)


@login_required
@user_passes_test(lambda u: u.is_staff)
def import_dialogues(request):
    import shutil

    # Check whether the form is yet to be served.
    if not request.GET:
        context = {'use_cf': settings.USE_CF,
                   'app_url': settings.APP_URL}
        return render(request, "trs/import.html", context,
                      context_instance=RequestContext(request))

    # Initialisation.
    session_missing = []
    session_empty = []
    copy_failed = []
    save_failed = []
    save_price_failed = []
    dg_existed = []
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
            with XMLSession(fname=sess_fname, mode='r') as session:
                try:
                    for uturn_idx in xrange(settings.MIN_TURNS):
                        next(session.iter_uturns())
                except StopIteration:
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
                salt += 0
                cid = _hash(dirname + str(salt))
                same_cid_dgs = Dialogue.objects.filter(cid=cid)

            # Copy the dialogue files.
            tgt_fname = os.path.join(settings.CONVERSATION_DIR, cid)
            try:
                shutil.copytree(src_fname, tgt_fname)
            except:
                if not ignore_exdirs:
                    copy_failed.append(src_fname)
                    continue

            # Create an object for the dialogue and save it in the DB, unless
            # it has been there already.
            if same_cid_dgs:
                dg_existed.append(dirname)

                # XXX If only updating the absolute turn numbers,
                if only_order:
                    # Do update the order.
                    dg_data = Dialogue.objects.get(cid=cid)
                    _read_dialogue_turns(dg_data, tgt_fname, with_trss,
                                         only_order=True)

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
    context['SUB_SITE'] = settings.SUB_SITE
    context['session_missing'] = session_missing
    context['session_empty'] = session_empty
    context['copy_failed'] = copy_failed
    context['save_failed'] = save_failed
    context['save_price_failed'] = save_price_failed
    context['dg_existed'] = dg_existed
    if upload_to_cf:
        context['cf_upload'] = True
        context['cf_error'] = cf_error
    else:
        context['cf_upload'] = False
    context['csv_fname'] = csv_fname
    context['count'] = count
    context['n_failed'] = (len(session_missing) + len(session_empty)
                           + len(copy_failed) + len(save_failed)
                           + len(save_price_failed) + len(dg_existed))
    return render(request, "trs/imported.html", context)


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


    class WorkLogsForm(forms.Form):
        logs_list_path = forms.FilePathField(
            path=settings.LISTS_DIR,
            label="Path to the worklogs list file",
            help_text=('Select the file that lists paths towards worklog '
                       'files that should be reused.'))


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


    # TODO Move forms to their own module.
    class ListField(forms.Field):
        def to_python(self, value):
            "Normalize data to a list of strings."
            # Return None if no input was given.
            if not value:
                return list()
            return sorted(set(map(unicode.strip, value.split(','))))


    # TODO Move forms to their own module.
    class CustomFieldsForm(forms.Form):
        def __init__(self, fields, data=None):
            super(CustomFieldsForm, self).__init__(data)
            self.fields.update(fields)


    # TODO Move forms to their own module.
    class CreateJobForm(forms.Form):
        """A form for creating Crowdflower jobs."""

        class CountriesField(ListField):
            """Form field for entering country codes."""
            def validate(self, value):
                "Check if value consists only of two-letter codes."
                # Use the parent's handling of required fields, etc.
                super(CreateJobForm.CountriesField, self).validate(value)
                wrong_codes = set()
                for code in value:
                    if len(code) != 2 or not code.isupper():
                        wrong_codes.add(code)
                if wrong_codes:
                    codes_list = ', '.join('"{code}"'.format(code=code)
                                           for code in sorted(wrong_codes))
                    msg = ('Following are definitely not valid country codes: '
                           '{codes}.').format(codes=codes_list)
                    raise forms.ValidationError(msg)

        class PricesField(forms.Field):
            """Form field for entering a list of integers."""
            def to_python(self, value):
                "Normalize data to a list of integers."
                # Return None if no input was given.
                if not value:
                    return list()

                # Otherwise, check all input values whether they can be coerced
                # to ints.
                string_list = set(map(unicode.strip, value.split(',')))
                wrong_ints = set()
                good_ints = set()
                for int_str in string_list:
                    try:
                        good_ints.add(int(int_str))
                    except ValueError:
                        wrong_ints.add(int_str)
                if wrong_ints:
                    ints_list = ', '.join('"{int_}"'.format(int_=int_)
                                          for int_ in wrong_ints)
                    msg = ('Following are not valid integers: {ints}.'
                           .format(ints=ints_list))
                    raise forms.ValidationError(msg)
                else:
                    return list(sorted(good_ints))

        # Constants.
        default_countries = ",".join(("AU", "CA", "GB", "IE", "IM", "NZ",
                                      "US"))
        default_title = 'Dialogue transcription – {price}c'
        default_instructions = re.sub(' +', ' ', """\
            Please, write down what is said in the provided recordings. The
            recordings capture a dialogue between a human and a computer. The
            computer utterances are known, so only the human's utterances need
            to be transcribed.""").strip().replace('\n ', '\n')
        inputWidth = len(default_title)
        fixedWidthTextInput = forms.TextInput(attrs={'size': inputWidth})

        # Fields.
        cents_per_unit = PricesField(
            initial='5, 10, 15, 20, 25, 30, 35, 40',
            widget=fixedWidthTextInput,
            help_text=('Specify desired price per dialogue in cents. This can '
                       'be a comma-separated list of integers. A job will be '
                       'created for each price specified here.'))
        store_job_id = forms.BooleanField(
            initial=True,
            label='Store job ID',
            help_text=('Should job IDs be written to a job ID list file? '
                       '(Leave this checked if you want to upload dialogues '
                       'for this job.)'),
            required=False)
        job_cml_path = forms.FilePathField(
            path=os.path.dirname(default_job_cml_path),
            match='\.cml$',
            initial=default_job_cml_path,
            label="Path to the job CML file",
            help_text=('Select the file that defines the body of the '
                       'Crowdflower unit.\n'
                       'If you see no choices here, you might need to run '
                       'the scripts/setup_script.py script yet.'))
        judgments_per_unit = forms.IntegerField(
            initial=1,
            widget=fixedWidthTextInput,
            help_text='How many times do you want each dialogue transcribed?')
        units_per_assignment = forms.IntegerField(
            initial=2,
            widget=fixedWidthTextInput,
            help_text='How many dialogues in a HIT?')
        pages_per_assignment = forms.IntegerField(
            initial=1,
            widget=fixedWidthTextInput,
            help_text='How many visual pages to split each HIT into?')
        gold_per_assignment = forms.IntegerField(
            initial=1,
            widget=fixedWidthTextInput,
            help_text='How many gold dialogues per HIT?')
        title = forms.CharField(
            initial=default_title, widget=fixedWidthTextInput,
            help_text=('Title for the job. "{price}" will be substituted '
                       'with the HIT price in cents.'))
        instructions = forms.CharField(
            initial=default_instructions,
            widget=forms.Textarea(attrs={'rows': 3, 'cols': 64}),
            help_text='Specify instructions for the Crowdflower job in HTML.')
        bronze = forms.BooleanField(
            initial=True,
            help_text=('Require bronze classification from workers to work on '
                       'this job?'),
            required=False)
        included_countries = CountriesField(
            initial=default_countries, widget=fixedWidthTextInput,
            help_text=('Specify countries which workers have to reside in '
                       'in order to qualify for working on this job. '
                       'Use two-letter country codes.'))


    # TODO Move forms to their own module.
    class DeleteJobForm(forms.Form):
        """A form for deleting Crowdflower jobs."""

        def __init__(self, data=None):
            """Creates the form.

            Arguments:
                data -- request.POST if the form is bound

            """

            super(DeleteJobForm, self).__init__(data)

            # If creating a bound form,
            if data is not None:
                # Create hidden fields.
                fields = dict()
                # Collect job IDs of the old jobs.
                if data['old_job_ids']:
                    old_job_ids = data['old_job_ids'].split(',')
                else:
                    old_job_ids = list()
                self.has_old_job_ids = bool(old_job_ids)
                fields['old_job_ids'] = ListField(widget=forms.HiddenInput(),
                                                  required=False)
                # Collect job IDs of the active jobs.
                if data['active_job_ids']:
                    active_job_ids = data['active_job_ids'].split(',')
                else:
                    active_job_ids = list()
                self.has_active_job_ids = bool(active_job_ids)
                fields['active_job_ids'] = ListField(
                    widget=forms.HiddenInput(), required=False)
                # Store the hidden fields and their data.
                self._hidden_fields = fields
                self._hidden_data = {key: data[key] for key in fields}
                self.fields.update(fields)

                # Re-create old job fields.
                field_items, self._old_data = self._populate_bound_fields(
                    data, old_job_ids)
                fields = SortedDict(field_items)
                self._old_job_fields = fields
                self.fields.update(fields)
                # Re-create active job fields.
                field_items, self._active_data = self._populate_bound_fields(
                    data, active_job_ids)
                fields = SortedDict(field_items)
                self._active_job_fields = fields
                self.fields.update(fields)

            # If creating a new form,
            else:
                fields = dict()
                # Collect job IDs of the old jobs.
                old_price_classes = price_class_handler.old_price_classes
                old_job_ids = [job_id for price, job_id in old_price_classes]
                old_job_ids_str = ','.join(sorted(old_job_ids))
                # Remember what all old job IDs we have.
                self.has_old_job_ids = bool(old_job_ids)
                fields['old_job_ids'] = ListField(
                    widget=forms.HiddenInput(),
                    initial=old_job_ids_str,
                    required=False)

                # Collect job IDs of the active jobs.
                price_classes = price_class_handler.price_classes.viewitems()
                active_job_ids = [job_id for price, job_id in price_classes]
                active_job_ids_str = ','.join(sorted(active_job_ids))
                # Remember what all active job IDs we have.
                self.has_active_job_ids = bool(active_job_ids)
                fields['active_job_ids'] = ListField(
                    widget=forms.HiddenInput(),
                    initial=active_job_ids_str,
                    required=False)

                # Store the hidden fields.
                self._hidden_fields = fields
                self._hidden_data = {'old_job_ids': old_job_ids_str,
                                     'active_job_ids': active_job_ids_str}
                self.fields.update(fields)

                # Create old job fields.
                field_items = self._populate_unbound_fields(old_price_classes)
                fields = SortedDict(field_items)
                self._old_data = None
                self._old_job_fields = fields
                self.fields.update(fields)
                # Create active job fields.
                field_items = self._populate_unbound_fields(price_classes)
                fields = SortedDict(field_items)
                self._active_data = None
                self._active_job_fields = fields
                self.fields.update(fields)

        def _populate_bound_fields(self, data, job_ids):
            field_items = list()
            my_data = dict()
            for job_id in job_ids:
                # Find the field's label.
                label_field_name = '{job_id}-label'.format(job_id=job_id)
                label = data[label_field_name]
                # Create the field itself and its label field.
                field = forms.BooleanField(label=label, required=False)
                field_items.append((job_id, field))
                field = forms.CharField(widget=forms.HiddenInput())
                field_items.append((label_field_name, field))
                # Copy the data items used.
                my_data[label_field_name] = data[label_field_name]
                my_data[job_id] = job_id in data
            return field_items, my_data

        def _populate_unbound_fields(self, price_classes):
            field_items = list()
            for price, job_id in sorted(price_classes):
                # Create the field itself.
                label = '{job_id} ({cents}c)'.format(
                    cents=int(100 * price), job_id=job_id)
                field = forms.BooleanField(initial=True, label=label,
                                           required=False)
                field_items.append((job_id, field))
                # Remember the label for the field.
                label_field = forms.CharField(widget=forms.HiddenInput(),
                                              initial=label)
                label_field_name = '{job_id}-label'.format(job_id=job_id)
                field_items.append((label_field_name, label_field))
            return field_items

        def gen_html_parts(self):
            # Generate the hidden HTML.
            hidden_form = CustomFieldsForm(self._hidden_fields,
                                           self._hidden_data)
            self.hidden_html = hidden_form.as_table()

            # Generate HTML for the old jobs part.
            old_jobs_form = CustomFieldsForm(self._old_job_fields,
                                             self._old_data)
            old_jobs_form.is_valid()
            self.old_jobs_html = old_jobs_form.as_table()

            # Generate HTML for the active jobs part.
            active_jobs_form = CustomFieldsForm(self._active_job_fields,
                                                self._active_data)
            active_jobs_form.is_valid()
            self.active_jobs_html = active_jobs_form.as_table()

            # Return an empty string, so that this method can be called from
            # within a template.
            return ''

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
            signal = request.POST.get('signal', [None])[0]
            # Try: be robust
            # a.k.a. Pokemon exception handling: catch 'em all
            try:
                if signal in ('job_complete', 'unit_complete'):
                    # Save the request data to a log.
                    log_path = get_log_path(settings.WORKLOGS_DIR)
                    with open(log_path, 'w') as log_file:
                        log_file.write(repr(request.POST)
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

                job_deletion_failed = dict()  # :: {jobid -> ?deletion_failed}
                msgs = dict()  # :: {jobid -> message}
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
