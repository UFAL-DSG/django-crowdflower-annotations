#!/usr/bin/python
# -*- coding: UTF-8 -*-
#
# TODO: User.objects.get_or_create(dummy_user) where appropriate.
from datetime import datetime
import hashlib
import os
import random
from subprocess import check_output
from django import forms
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.db.models import Count
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.template import RequestContext
from django.views.decorators.csrf import csrf_exempt

import dg_util
from session_xml import FileNotFoundError, XMLSession
import settings
from util import get_log_path
# XXX: Beware, this imports the settings from within the `transcription'
# directory. That means that PROJECT_DIR will be
# /webapps/cf_transcription/transcription, not just /webapps/cf_transcription.
from tr_normalisation import trss_match
from transcription.models import Transcription, DialogueAnnotation, \
    Dialogue, UserTurn, SystemTurn


def group_by(objects, attrs):
    """Groups `objects' by the values of their attributes `attrs'.

    Returns a dictionary mapping from a tuple of attribute values to a list of
    objects with those attribute values.

    """
    groups = dict()
    for obj in objects:
        key = tuple(obj.__getattribute__(attr) for attr in attrs)
        groups.setdefault(key, []).append(obj)
    return groups


def _hash(s):
    return hashlib.sha1(s).hexdigest()


class TranscriptionForm(forms.Form):
    quality = forms.CharField()
    accent = forms.CharField()
    accent_name = forms.CharField(required=False)
    offensive = forms.BooleanField()
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


def _read_dialogue_turns(dg_data, dirname, with_trss=False):
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

    """

    with XMLSession(dg_data.cid) as session:
        # Process user turns.
        uturns = list()
        for uturn_nt in session.iter_uturns():
            if uturn_nt.wav_fname is not None:
                turnnum = uturn_nt.turn_number
                # Do not override turns saved earlier.
                if turnnum < len(uturns) and uturns[turnnum] is not None:
                    continue

                # Create the user turn object.
                uturn = UserTurn(
                    dialogue=dg_data,
                    turn_number=turnnum,
                    wav_fname=os.path.join(dirname, uturn_nt.wav_fname))

                # Prepare the `uturns' list for storing the new user turn.
                while turnnum > len(uturns):
                    uturns.append(None)

                # Save the user turn object.
                uturns.append(uturn)
                assert (uturns[turnnum] == uturn)
                uturn.save()

        # Process system turns.
        for systurn in session.iter_systurns():
            SystemTurn(dialogue=dg_data,
                       turn_number=systurn.turn_number,
                       text=systurn.text).save()

        # If transcriptions should be read and saved as well,
        if with_trss:
            dummy_user = User.objects.get(username='testres')

            # Iterate over all dialogue annotations.
            for ann_el in session.iter_annotations():
                # Retrieve all properties of the dialogue annotation object.
                accent_str = ann_el.get('accent')
                accent = ("" if accent_str == 'native' else accent_str)
                notes = ('' if ann_el.text is None else ann_el.text.strip())
                offensive = (ann_el.get("offensive") == "True")
                program_version = ann_el.get('program_version')
                quality = (DialogueAnnotation.QUALITY_CLEAR
                           if ann_el.get('quality') == 'clear'
                           else DialogueAnnotation.QUALITY_NOISY)
                ann_users = User.objects.filter(username=ann_el.get('user'))
                if ann_users.exists():
                    ann_user = ann_users[0]
                else:
                    ann_user = dummy_user
                # Check whether this object has been imported already.
                ann_props = {'accent': accent,
                             'dialogue': dg_data,
                             'notes': notes,
                             'offensive': offensive,
                             'quality': quality,
                             'user': ann_user,
                             'program_version': program_version}
                if not DialogueAnnotation.objects.filter(**ann_props):
                    # Save the dialogue annotation.
                    dg_ann = DialogueAnnotation(**ann_props)
                    dg_ann.save()

                    # Find all transcriptions that belong to this dialogue
                    # annotation and save them as database objects.
                    for turnnum, trs_el in session.iter_transcriptions(ann_el):
                        Transcription(
                            text=trs_el.text,
                            turn=uturns[turnnum],
                            dialogue_annotation=dg_ann,
                            is_gold=(trs_el.get('is_gold') != '0'),
                            breaks_gold=(trs_el.get('breaks_gold') != '0'),
                            some_breaks_gold=(
                                trs_el.get('some_breaks_gold') != '0')).save()


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
            uturn_nums = [uturn.turn_number for uturn in uturns]
            uturn_ind = [None] * max(uturn_nums)  # (turn_num - 1) -> uturn
            for uturn in uturns:
                uturn_ind[uturn.turn_number - 1] = uturn
        else:
            uturn_ind = None
        form = TranscriptionForm(request.POST, cid=cid, uturn_ind=uturn_ind)

        if form.is_valid():
            dummy_user = User.objects.get(username='testres')

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
            dg_ann.quality = (DialogueAnnotation.QUALITY_CLEAR if
                              request.POST['quality'] == 'clear'
                              else DialogueAnnotation.QUALITY_NOISY)
            dg_ann.accent = ("" if request.POST['accent'] == 'native'
                             else form.cleaned_data['accent_name'])
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
                    trss = dict()
                    for turn_num, uturn in enumerate(uturn_ind, start=1):
                        if not uturn:
                            continue
                        trs = Transcription()
                        trss[turn_num - 1] = trs
                        trs.text = form.cleaned_data[
                            'trs_{0}'.format(turn_num)]
                        trs.turn = uturn
                        trs.dialogue_annotation = dg_ann

                    # Check the form against any gold items.  If all are OK,
                    # return one code; if not, return another.
                    gold_trss = Transcription.objects.filter(
                        dialogue_annotation__dialogue=dg_data,
                        is_gold=True)
                    gold_trss = group_by(gold_trss, ('turn', ))
                    mismatch = False
                    for turn_gold_trss in gold_trss.itervalues():
                        submismatch = True
                        for gold_trs in turn_gold_trss:
                            if trss_match(trss[gold_trs.turn.turn_number - 1],
                                          gold_trs,
                                          max_char_er=settings.MAX_CHAR_ER):
                                submismatch = False
                                break
                        if submismatch:
                            mismatch = True
                            (trss[gold_trs.turn.turn_number - 1]
                                .breaks_gold) = True

                    # Update transcriptions in the light of their comparison to
                    # gold transcriptions, and save them both into the
                    # database, and to the XML.
                    for turn_num, uturn in enumerate(uturn_ind, start=1):
                        if not uturn:
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

            # Populate context with data from the previous dialogue (form).
            context = settings.TRANSCRIBE_EXTRA_CONTEXT
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
        else:
            # If there is no open annotation for this user, find a dialogue
            # that is free to annotate.

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
                # XXX Not sure whether the following line does what it should
                # do.  However, for MAX_ANNOTATIONS_PER_INPUT=1, it definitely
                # works.
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
    uturns = UserTurn.objects.filter(dialogue=dg_data)
    systurns = SystemTurn.objects.filter(dialogue=dg_data)
    max_turn_num = max(max(uturn.turn_number for uturn in uturns),
                       max(sturn.turn_number for sturn in systurns))
    turns = [dict() for _ in xrange(max_turn_num)]
    for uturn in uturns:
        seclast_slash = uturn.wav_fname.rfind(
            os.sep, 0, uturn.wav_fname.rfind(os.sep))
        wav_fname_rest = uturn.wav_fname[seclast_slash:]
        turns[uturn.turn_number - 1].update(turn_number=uturn.turn_number,
                                            rec=wav_fname_rest,
                                            has_rec=True)
    for systurn in systurns:
        turns[systurn.turn_number - 1].update(turn_number=systurn.turn_number,
                                              prompt=systurn.text)
    dbl_turn_num = 0
    for turn in turns:
        turn['dbl_turn_num'] = dbl_turn_num
        if not 'has_rec' in turn:
            turn['has_rec'] = False
        dbl_turn_num += 2

    uturn_ind = map(lambda turn: turn['has_rec'], turns)

    context = settings.TRANSCRIBE_EXTRA_CONTEXT
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
    return render(request, "trs/home.html")


@login_required
@user_passes_test(lambda u: u.is_staff)
def import_dialogues(request):
    import shutil

    # Check whether the form is yet to be served.
    if not request.GET:
        context = {'use_cf': settings.USE_CF}
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
        if os.path.isabs(csv_fname):
            csv_fname = os.path.abspath(csv_fname)
        else:
            csv_fname = os.path.join(settings.CONVERSATION_DIR, csv_fname)
    dirlist_fname = request.GET['list_fname']
    with_trss = request.GET.get('with_trss', False) == 'on'
    ignore_exdirs = request.GET.get('ignore_exdirs', False) == 'on'
    upload_to_cf = settings.USE_CF and request.GET.get('upload', False) == 'on'

    # Do the import.
    with open(dirlist_fname, 'r') as dirlist_file, \
            open(csv_fname, 'w') as csv_file:
        # Prepare the JSON upload data, and the CSV header.
        if upload_to_cf:
            json_data = dg_util.JsonDialogueUpload()
        csv_file.write('cid, code, code_gold\n')
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
            # Check that there are any user turns in the session.
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
            _read_dialogue_turns(dg_data, tgt_fname, with_trss)
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
            csv_file.write('{cid}, {code}, {gold}\n'
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


if settings.USE_CF:
    @csrf_exempt
    def log_work(request):
        try:
            # Try: be robust
            # a.k.a. Pokemon exception handling: catch 'em all
            try:
                if request.POST.get(u'signal', None) == u'unit_complete':
                    # Save the request data to a log.
                    log_path = get_log_path(settings.WORKLOGS_DIR)
                    with open(log_path, 'w') as log_file:
                        log_file.write(repr(request.POST)
                                       if hasattr(request, 'POST') else 'None')
            except Exception:
                pass
            # Record the request to a session XML file.
            dg_util.record_worker(request)
        finally:
            from django.http import HttpResponse
            return HttpResponse(status=200)
