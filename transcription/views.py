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
from transcription.models import Transcription, Dialogue
from transcription.parser import DialogParser
from django import forms
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.template import RequestContext
from tempfile import TemporaryFile


# Constants.
TRS_FNAME = "user-transcription.xml"


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
        turns = kwargs.pop('turns')
        cid = kwargs.pop('cid', None)
        super(TranscriptionForm, self).__init__(*args, **kwargs)

        self.fields['cid'] = forms.CharField(widget=forms.HiddenInput(),
                                             initial=cid)

        for turn in turns:
            if not turn.has_rec:
                continue
            self.fields['trs_{0}'.format(turn.id)] = \
                forms.CharField(widget=forms.Textarea(
                    attrs={'style': 'width: 90%', 'rows': '3'}),
                    label=turn.id)


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


def _read_dialogue(dirname, cdir=settings.CONVERSATION_DIR, xmlname=TRS_FNAME):
    dialogue = DialogParser.parse(os.path.join(cdir, dirname, xmlname))
    dialogue.delete_from("Thank you for using the system.")
    # TODO Delete also the long, repeating introduction.
    dialogue.path = "/apps/transcription/data/recs/" + dirname
    return dialogue


def transcribe(request):

    # If the form has been submitted,
    if request.method == "POST":
        cid = request.POST['cid']
        dg_data = Dialogue.objects.get(cid=cid)
        dialogue = _read_dialogue(cid)
        dg_codes = dg_data.get_codes()
        form = TranscriptionForm(request.POST, cid=cid, turns=dialogue.turns)

        if form.is_valid():
            # Read the XML session file.
            dg_dir = os.path.join(settings.CONVERSATION_DIR, cid)
            sess_fname = os.path.join(dg_dir, settings.SESSION_FNAME)
            xml_parser = etree.XMLParser(remove_blank_text=True)
            with open(sess_fname, 'r+') as sess_file:
                sess_xml = etree.parse(sess_file, xml_parser)
            # user_turns = sess_xml.findall(".//userturn")
            user_turns = sess_xml.findall(settings.XMl_USERTURN_PATH)
            # Create Transcription objects and save them into DB.
            trss = dict()
            for turn in dialogue.turns:
                if not turn.has_rec:
                    continue
                if request.user.is_authenticated():
                    trs = Transcription(user=request.user)
                else:
                    # A dummy user.
                    dummy_user = User.objects.get(username='testres')
                    trs = Transcription(user=dummy_user)
                trss[turn.id] = trs
                trs.text = form.cleaned_data['trs_{0}'.format(turn.id)]
                trs.turn_id = turn.id
                trs.dg_cid = dg_data
                trs.program_version = unicode(check_output(
                    ["git", "rev-parse", "HEAD"],
                    cwd=settings.PROJECT_DIR).rstrip('\n'))

            # Check the form against any gold items.  If all are OK, return one
            # code; if not, return another.
            gold_trss = Transcription.objects.filter(dg_cid=dg_data,
                                                     is_gold=True)
            gold_trss = group_by(gold_trss, ('dg_cid', 'turn_id'))
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
            for turn in dialogue.turns:
                if not turn.has_rec:
                    continue
                trs = trss[turn.id]
                trs.some_breaks_gold = mismatch
                trs.save()
                # Reflect the transcription in the XML.
                turn_xml = filter(
                    lambda turn_xml: \
                    int(turn_xml.get(settings.XML_TURNNUMBER_ATTR)) == turn.id,
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
                trs_left_sib = \
                    trss_xml.find(settings.XML_TRANSCRIPTION_BEFORE)
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
        try:
            cid = request.GET["cid"]
        except:
            if request.user.is_anonymous():
                return HttpResponseRedirect("finished")
            trss_done = Transcription.objects.filter(user=request.user)
            cids_done = set(trs.dg_cid.cid for trs in trss_done)
            cids_todo = set(dg.cid for dg in Dialogue.objects.all()) - \
                        cids_done
            try:
                cid = cids_todo.pop()
            except KeyError:
                return HttpResponseRedirect("finished")
            dg_data = Dialogue.objects.get(cid=cid)
        if dg_data is None:
            # Find the corresponding Dialogue object in the DB.
            dg_data = Dialogue.objects.get(cid=cid)
        dialogue = _read_dialogue(dg_data.cid)

        context = dict()
        context['cid'] = cid
        context['dialogue'] = dialogue
        context['codes'] = dg_data.get_codes()

        form = context['form'] = \
            TranscriptionForm(cid=cid,
                              turns=dialogue.turns)
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
        csv_file.write('cid, code\n')
        # Process dg_data files.
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
            # Copy the dg_data files.
            try:
                shutil.copytree(src_fname,
                                os.path.join(settings.CONVERSATION_DIR, cid))
            except:
                if not ignore_exdirs:
                    copy_failed.append(src_fname)
                    continue
            # Generate codes.
            dg_codes = _gen_codes()
            dg_data = Dialogue(cid=cid,
                               code=dg_codes[0],
                               code_corr=dg_codes[1],
                               code_incorr=dg_codes[2],
                               dirname=dirname)
            # Save the dg_data in the DB, unless it has been there already.
            if same_cid_dgs:
                # This should actually never happen.
                dg_existed.append(dirname)
                continue
            else:
                try:
                    dg_data.save()
                except:
                    save_failed.append((dirname, cid))
                    continue
            # Add a record to the CSV for CrowdFlower. (left for extra safety)
            csv_file.write('{cid}, {code}\n'.format(cid=cid, code=dg_codes[0]))
            # Add a record to the JSON for CrowdFlower.
            json_str += '{{"cid":"{cid}","code":"{code}"}}'.format(\
                cid=cid, code=dg_codes[0])
            count += 1
    if upload_to_cf:
        # Communicate the new data to CrowdFlower via the CF API.
        cf_url = '{start}jobs/{jobid}/upload.json?key={key}'.format(
            start=settings.CF_URL_START,
            jobid=settings.CF_JOB_ID,
            key=settings.CF_KEY)
        try:
            upload_outfile = TemporaryFile()
        except:
            cf_error = "Output from `curl' could not be obtained."
            upload_outfile = None
        #     cf_retcode = call(['curl', '-T', csv_fname, '-H', 'Content-Type:
        #     text/csv',
        #                        cf_url],
        #                       stdout=upload_outfile)
        cf_retcode = call(['curl', '-d', json_str, '-H',
                           'Content-Type: application/json',
                           cf_url],
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
    context['dg_existed'] = dg_existed
    if upload_to_cf:
        context['cf_upload'] = True
        context['cf_url'] = cf_url
        context['cf_error'] = cf_error
    else:
        context['cf_upload'] = False
    context['csv_fname'] = csv_fname
    context['count'] = count
    context['n_failed'] = len(copy_failed) + len(save_failed) + len(dg_existed)
    return render(request, "er/imported.html", context)
