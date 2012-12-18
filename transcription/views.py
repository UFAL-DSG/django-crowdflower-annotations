#!/usr/bin/python
# -*- coding: UTF-8 -*-
#
# TODO: User.objects.get_or_create(dummy_user) where appropriate.
import hashlib
import json
import os
import random
from subprocess import check_output, call
from tr_normalisation import trss_match

import lxml.etree as etree
import settings
from transcription.models import Transcription, DialogueAnnotation, Dialogue, \
    UserTurn, SystemTurn
from django import forms
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.template import RequestContext
from tempfile import TemporaryFile


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
    def __init__(self, *args, **kwargs):
        uturn_ind = kwargs.pop('uturn_ind')
        cid = kwargs.pop('cid', None)
        super(TranscriptionForm, self).__init__(*args, **kwargs)

        self.fields['cid'] = forms.CharField(widget=forms.HiddenInput(),
                                             initial=cid)
        self.fields['quality'] = forms.CharField()
        self.fields['accent'] = forms.CharField()
        self.fields['offensive'] = forms.BooleanField()
        self.fields['notes'] = forms.CharField()

        for turn_num, has_rec in enumerate(uturn_ind):
            if not has_rec:
                continue
            self.fields['trs_{0}'.format(turn_num)] = \
                forms.CharField(widget=forms.Textarea(
                    attrs={'style': 'width: 90%', 'rows': '3'}),
                    label=turn_num)


def finished(request):
    return render(request, "er/finished.html")


def _gen_codes():
    """Generates a random code for a dialogue, to be used in validation of CF
    workers' input."""
    code = ''.join([random.choice('0123456789')
                    for _ in xrange(settings.CODE_LENGTH)])
    code_corr = ''.join([random.choice('0123456789')
                         for _ in xrange(settings.CODE_LENGTH_EXT)])
    code_incorr = ''.join([random.choice('0123456789')
                           for _ in xrange(settings.CODE_LENGTH_EXT)])
    return (code, code_corr, code_incorr)


def _read_dialogue_turns(dg_data):
    sess_xml = etree.parse(os.path.join(dg_data.dirname,
                                        settings.SESSION_FNAME))
    # num_recs = 0 # number of recs seen so far
    for uturn_xml in sess_xml.iterfind(settings.XML_USERTURN_PATH):
        turn = UserTurn(
            dialogue=dg_data,
            turn_number=uturn_xml.attrib[settings.XML_TURNNUMBER_ATTR],
            wav_fname=os.path.join(
                settings.CONVERSATION_DIR,
                uturn_xml.find(settings.XML_REC_SUBPATH).attrib[
                    settings.XML_REC_FNAME_ATTR]))
        turn.save()
    for systurn_xml in sess_xml.iterfind(settings.XML_SYSTURN_PATH):
        text = systurn_xml.findtext(settings.XML_SYSTEXT_SUBPATH)
        # Throw away some distracting pieces of system prompts.
        if text == "Thank you for using the system.":
            continue
        text = text.replace("Thank you for calling the Cambridge Information "
                            "system. Your call will be recorded for research "
                            "purposes.",
                            "").strip()
        turn = SystemTurn(
            dialogue=dg_data,
            turn_number=uturn_xml.attrib[settings.XML_TURNNUMBER_ATTR],
            text=text)
        turn.save()


def update_price(dg_data):
    """Computes the price of a dialogue transcription in USD."""
    uturns = UserTurn.objects.filter(dialogue=dg_data)
    # Compute the length of the audio.
    wavsize = 0
    for turn in uturns:
        wavsize += os.path.getsize(turn.wav_fname)
    sec = wavsize / float(16000 * 2)
    minutes = sec / 60.

    price = (settings.PRICE_CONST + settings.PRICE_PER_MIN * minutes
             + settings.PRICE_PER_TURN * len(uturns))
    dg_data.price = price


def transcribe(request):

    # If the form has been submitted,
    if request.method == "POST":
        cid = request.POST['cid']
        dg_data = Dialogue.objects.get(cid=cid)
        uturns = UserTurn.objects.filter(dialogue=dg_data)
        uturn_nums = [uturn.turn_number for uturn in uturns]
        uturn_ind = [False] * (max(uturn_nums) + 1)
        for uturn_num in uturn_nums:
            uturn_ind[uturn_num] = True
        dg_codes = dg_data.get_codes()
        form = TranscriptionForm(request.POST, cid=cid, turn_inds=uturn_ind)

        if form.is_valid():
            # Read the XML session file.
            dg_dir = os.path.join(settings.CONVERSATION_DIR, cid)
            sess_fname = os.path.join(dg_dir, settings.SESSION_FNAME)
            xml_parser = etree.XMLParser(remove_blank_text=True)
            with open(sess_fname, 'r+') as sess_file:
                sess_xml = etree.parse(sess_file, xml_parser)
            user_turns = sess_xml.findall(settings.XML_USERTURN_PATH)
            # Create the DialogueAnnotation object and save it into DB.
            dg_ann = DialogueAnnotation()
            dg_ann.dialogue = dg_data
            dg_ann.program_version = unicode(check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=settings.PROJECT_DIR).rstrip('\n'))
            dg_ann.quality = (DialogueAnnotation.QUALITY_CLEAR if
                              form.cleaned_data['quality_clear']
                              else DialogueAnnotation.QUALITY_NOISY)
            dg_ann.accent = (None if
                             form.cleaned_data['accent_native']
                             else form.cleaned_data['accent_name'])
            dg_ann.offensive = bool(form.cleaned_data['offensive_yes'])
            dg_ann.notes = form.cleaned_data['notes']
            dg_ann.save()
            # Create Transcription objects and save them into DB.
            trss = dict()
            for turn_num, has_rec in enumerate(uturn_ind):
                if not has_rec:
                    continue
                if request.user.is_authenticated():
                    trs = Transcription(user=request.user)
                else:
                    # A dummy user.
                    dummy_user = User.objects.get(username='testres')
                    trs = Transcription(user=dummy_user)
                trss[turn_num] = trs
                trs.text = form.cleaned_data['trs_{0}'.format(turn_num)]
                trs.turn_id = turn_num
                trs.dialogue_annotation = dg_ann

            # Check the form against any gold items.  If all are OK, return one
            # code; if not, return another.
            gold_trss = Transcription.objects.filter(dialogue=dg_data,
                                                     is_gold=True)
            gold_trss = group_by(gold_trss, ('dialogue', 'turn_id'))
            mismatch = False
            for turn_gold_trss in gold_trss.itervalues():
                submismatch = True
                for gold_trs in turn_gold_trss:
                    if trss_match(trss[gold_trs.turn_id], gold_trs):
                        submismatch = False
                        break
                if submismatch:
                    mismatch = True
                    trss[gold_trs.turn_id].breaks_gold = True

            # Update transcriptions in the light of their comparison to gold
            # transcriptions, and save them.
            for turn_num, has_rec in enumerate(uturn_ind):
                if not has_rec:
                    continue
                trs = trss[turn_num]
                trs.some_breaks_gold = mismatch
                trs.save()
                # Reflect the transcription in the XML.
                turn_xml = filter(
                    lambda turn_xml: \
                        int(turn_xml.get(settings.XML_TURNNUMBER_ATTR)) \
                            == turn_num,
                    user_turns)[0]
                if settings.XML_TRANSCRIPTIONS_ELEM is not None:
                    trss_xml = turn_xml.find(settings.XML_TRANSCRIPTIONS_ELEM)
                    if trss_xml is None:
                        trss_left_sib = \
                            turn_xml.find(settings.XML_TRANSCRIPTIONS_BEFORE)
                        if trss_left_sib is None:
                            insert_idx = len(turn_xml)
                        else:
                            insert_idx = turn_xml.index(trss_left_sib) + 1
                        trss_xml = \
                            etree.Element(settings.XML_TRANSCRIPTIONS_ELEM)
                        turn_xml.insert(insert_idx, trss_xml)
                else:
                    trss_xml = turn_xml
                trs_xml = etree.Element(
                    settings.XML_TRANSCRIPTION_ELEM,
                    author=trs.user.username,
                    is_gold="0",
                    breaks_gold="1" if trs.breaks_gold else "0",
                    some_breaks_gold="1" if mismatch else "0",
                    date_saved=(
                        trs.date_updated.strptime(settings.XML_DATE_FORMAT)\
                            .rstrip() if settings.XML_DATE_FORMAT else
                        unicode(trs.date_updated)),
                    program_version=trs.program_version)
                trs_xml.text = trs.text
                if settings.XML_TRANSCRIPTION_BEFORE:
                    trs_left_sib = \
                        trss_xml.find(settings.XML_TRANSCRIPTION_BEFORE)
                else:
                    trs_left_sib = None
                if trs_left_sib is None:
                    insert_idx = len(trss_xml)
                else:
                    insert_idx = trss_xml.index(trs_left_sib) + 1
                trss_xml.insert(insert_idx, trs_xml)
            # Write the XML session file.
            with open(sess_fname, 'w') as sess_file:
                sess_file.write(etree.tostring(sess_xml,
                                               pretty_print=True,
                                               xml_declaration=True,
                                               encoding='UTF-8'))

            context = dict()
            context['code'] = dg_codes[0] + (dg_codes[2] if mismatch else
                                             dg_codes[1])
            return render(request,
                          "er/code.html",
                          context,
                          context_instance=RequestContext(request))
        # If the form is not valid,
        else:
            # Populate context with data from the previous dialogue (form).
            context = dict()
            for key, value in request.POST.iteritems():
                context[key] = value
            response = render(request,
                              "er/transcribe.html",
                              context,
                              context_instance=RequestContext(request))
            # NOTE Perhaps not needed after all...
            response['X-Frame-Options'] = 'ALLOWALL'
            return response
    # Else, if a blank form is to be served,
    else:
        # Find the dialogue to transcribe.
        dg_data = None
        cid = request.GET.get("cid", None)
        # If the request did not specify the `cid' as a GET parameter,
        if cid is None:
            # Anonymous user cannot be helped.
            if request.user.is_anonymous():
                return HttpResponseRedirect("finished")
            # For a user, who is logged in, find a suitable dialogue to
            # transcribe.
            trss_done = Transcription.objects.filter(user=request.user)
            cids_done = set(trs.dialogue_annotation.dialogue.cid
                            for trs in trss_done)
            cids_todo = set(dg.cid for dg in Dialogue.objects.all()) - \
                        cids_done
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
            dg_data = Dialogue.objects.get(cid=cid)
        # Prepare the data about turns into a form suitable for the template.
        uturns = UserTurn.objects.filter(dialogue=dg_data)
        systurns = SystemTurn.objects.filter(dialogue=dg_data)
        turns = [dict()] * max(len(uturns), len(systurns))
        for uturn in uturns:
            turns[uturn.turn_number].update(turn_number=uturn.turn_number,
                                            rec=uturn.wav_fname,
                                            has_rec=True)
        for systurn in systurns:
            turns[systurn.turn_number].update(turn_number=systurn.turn_number,
                                              prompt=systurn.text)
        dbl_rec_num = 0
        for turn in turns:
            turn['dbl_rec_num'] = dbl_rec_num
            if 'has_rec' in turn:
                dbl_rec_num += 2
            else:
                turn['has_rec'] = False

        uturn_ind = map(lambda turn: turn.has_rec, turns)

        context = dict()
        context['cid'] = cid
        context['turns'] = turns
        context['dbl_num_recs'] = 2 * len(turns)
        context['codes'] = dg_data.get_codes()
        context['form'] = TranscriptionForm(cid=cid, turn_inds=uturn_ind)
    response = render(request,
                      "er/transcribe.html",
                      context,
                      context_instance=RequestContext(request))
    # NOTE Perhaps not needed after all...
    response['X-Frame-Options'] = 'ALLOWALL'
    return response


@login_required
def home(request):
    return render(request, "er/home.html")


@login_required
@user_passes_test(lambda u: u.is_staff)
def import_dialogues(request):
    # Check whether the form is yet to be served.
    if not request.GET:
        return render(request, "er/import.html", {})
    import os
    import os.path
    import shutil
    copy_failed = []
    save_failed = []
    save_price_failed = []
    dg_existed = []
    count = 0   # number of successfully imported dialogues
    csv_fname = request.GET.get('csv_fname', '')
    if not csv_fname:
        csv_fname = os.path.join(settings.CONVERSATION_DIR, 'new_tasks.csv')
    else:
        if os.path.isabs(csv_fname):
            csv_fname = os.path.abspath(csv_fname)
        else:
            csv_fname = os.path.join(settings.CONVERSATION_DIR, csv_fname)
    dirlist_fname = request.GET['list_fname']
    ignore_exdirs = request.GET.get('ignore_exdirs', False)
    upload_to_cf = request.GET.get('upload', True)
    # # DIRTY
    # shutil.copy('/tmp/db.db', '/webapps/cf_transcription/db')
    # import subprocess
    # subprocess.call(['chgrp', 'korvas',
    # '/webapps/cf_transcription/db/db.db'])
    # subprocess.call(['chmod', 'g+w', '/webapps/cf_transcription/db/db.db'])
    # return render(request, "er/import.html", {})

    with open(dirlist_fname, 'r') as dirlist_file, \
         open(csv_fname, 'w') as csv_file:
        # Prepare the JSON output string.
        json_str = ''
        # Write the CSV header.
        csv_file.write('cid, code, gold\n')
        # Process the dialogue files.
        for line in dirlist_file:
            src_fname = line.rstrip()
            dirname = os.path.basename(src_fname.rstrip(os.sep))
            # Generate CID.
            cid = _hash(dirname)
            # Check that this CID does not collide with a hash for another
            # dirname.
            # This is a crude implementation of hashing with replacement.
            same_cid_dgs = Dialogue.objects.filter(cid=cid)
            salt = -1
            while same_cid_dgs and same_cid_dgs[0].dirname != dirname:
                salt += 1
                cid = _hash(dirname + str(salt))
                same_cid_dgs = Dialogue.objects.filter(cid=cid)
            # Copy the dialogue files.
            try:
                shutil.copytree(src_fname,
                                os.path.join(settings.CONVERSATION_DIR, cid))
            except:
                if not ignore_exdirs:
                    copy_failed.append(src_fname)
                    continue
            # Create an object for the dialogue and save it in the DB, unless
            # it has been there already.
            if same_cid_dgs:
                # This should actually never happen.
                dg_existed.append(dirname)
                continue
            # Generate codes and other defining attributes of the dialogue.
            dg_codes = _gen_codes()
            dg_data = Dialogue(cid=cid,
                               code=dg_codes[0],
                               code_corr=dg_codes[1],
                               code_incorr=dg_codes[2],
                               dirname=dirname)
            try:
                dg_data.save()
            except:
                save_failed.append((dirname, cid))
                continue
            # Read the dialogue turns.
            _read_dialogue_turns(dg_data)
            # Compute the dialogue price.
            update_price(dg_data)
            # Update the dialogue in the DB.
            try:
                dg_data.save()
            except:
                save_price_failed.append((dirname, cid))
                continue
            # Add a record to the CSV for CrowdFlower. (kept for extra safety)
            code_gold = dg_codes[0] + dg_codes[1]
            csv_file.write('{cid}, {code}, {gold}\n'.format(cid=cid,
                                                            code=dg_codes[0],
                                                            gold=code_gold))
            # Add a record to the JSON for CrowdFlower.
            json_str += ('{{"cid":"{cid}","code":"{code}",'
                         '"code_gold":"{gold}"}}').format(cid=cid,
                                                          code=dg_codes[0],
                                                          gold=code_gold)
            count += 1
    if upload_to_cf:
        # Communicate the new data to CrowdFlower via the CF API.
        cf_url = '{start}jobs/{jobid}/upload.json?key={key}'.format(
            start=settings.CF_URL_START,
            jobid=settings.CF_JOB_ID,
            key=settings.CF_KEY)
        try:
            # Create a file for the response from CF.
            upload_outfile = TemporaryFile()
        except:
            cf_error = "Output from `curl' could not be obtained."
            upload_outfile = None
        # The following would send the data in the CSV format.
        #     cf_retcode = call(['curl', '-T', csv_fname, '-H', 'Content-Type:
        #     text/csv', cf_url], stdout=upload_outfile)
        cf_retcode = call(['curl', '-d', json_str, '-H',
                           'Content-Type: application/json', cf_url],
                          stdout=upload_outfile)
        cf_outobj = None
        if upload_outfile is not None:
            upload_outfile.seek(0)
            cf_outobj = json.load(upload_outfile)
            upload_outfile.close()
        if cf_retcode == 0:
            cf_error = None
        else:
            if cf_outobj is not None:
                cf_error = cf_outobj['error']['message'] \
                    if 'error' in cf_outobj else '(no message)'
    # Render the response.
    context = dict()
    context['copy_failed'] = copy_failed
    context['save_failed'] = save_failed
    context['save_price_failed'] = save_price_failed
    context['dg_existed'] = dg_existed
    if upload_to_cf:
        context['cf_upload'] = True
        context['cf_url'] = cf_url
        context['cf_error'] = cf_error
    else:
        context['cf_upload'] = False
    context['csv_fname'] = csv_fname
    context['count'] = count
    context['n_failed'] = (len(copy_failed) + len(save_failed)
                           + len(save_price_failed) + len(dg_existed))
    return render(request, "er/imported.html", context)

