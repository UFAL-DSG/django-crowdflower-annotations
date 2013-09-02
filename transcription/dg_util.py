#!/usr/bin/python
# -*- coding: UTF-8 -*-
import os

import settings
from transcription.models import Transcription, UserTurn


def is_gold(dg):
    """Returns True iff any turn of `dg' has a gold transcription."""
    return Transcription.objects.filter(dialogue_annotation__dialogue=dg,
                                        is_gold=True).exists()


def update_price(dg):
    """Computes the price of a dialogue transcription (in USD)."""
    uturns = UserTurn.objects.filter(dialogue=dg)
    # Compute the length of the audio.
    wavsize = 0
    for turn in uturns:
        wavsize += os.path.getsize(os.path.join(
            settings.CONVERSATION_DIR,
            turn.wav_fname))
    sec = wavsize / float(16000 * 2)
    minutes = sec / 60.

    price = (settings.PRICE_CONST + settings.PRICE_PER_MIN * minutes
             + settings.PRICE_PER_TURN * len(uturns))
    dg.transcription_price = price


# Following applies only when working with Crowdflower.
if settings.USE_CF:
    import json
    from lxml import etree
    from transcription.crowdflower import list_units, upload_units,\
        unit_pair_from_cid, update_unit

    # Check whether dialogues should be split into several CF jobs based on
    # their price.
    if hasattr(settings, 'CF_JOB_IDS'):
        price_classes = settings.CF_JOB_IDS
    else:
        assert hasattr(settings, 'CF_JOB_ID'), ('Either CF_JOB_ID or '
                                                'CF_JOB_IDS has to be set.')
        price_classes = None


    def get_job_id(dg):
        if price_classes is None:
            return settings.CF_JOB_ID
        else:
            try:
                # This selects the nearest lower price step.
                price_cat = max(filter(
                    lambda step: step <= dg.transcription_price,
                    price_classes))
            except ValueError:
                # Or, in case no price step is lower, the lowest price step
                # absolute.
                price_cat = min(price_classes)
            return price_classes[price_cat]


    def update_gold(dg):
        """Updates the gold status of `dg' on Crowdflower."""
        job_id = get_job_id(dg)
        success, unit_pair = unit_pair_from_cid(job_id, dg.cid)
        if not success:
            msg = unit_pair
            return False, msg
        unit_id, unit = unit_pair
        dg_is_gold = is_gold(dg)
        if dg_is_gold != (unit['state'] == 'golden'):
            success, errors = update_unit(
                job_id, unit_id, 'unit[state]={state}'.format(
                    state='golden' if dg_is_gold else 'new'))
            if not success:
                return False, errors
        return True, None


    def record_worker(request):
        """
        Records worker information to the corresponding session XML file based
        on POST data from CrowdFlower.

        """
        cf_data = json.loads(request.POST[u'payload'])
        judgment_data = cf_data["results"]["judgments"][0]
        cid = judgment_data["unit_data"]["cid"]
        # Read the XML session file.
        dg_dir = os.path.join(settings.CONVERSATION_DIR, cid)
        sess_fname = os.path.join(dg_dir, settings.SESSION_FNAME)
        with open(sess_fname, 'r+') as sess_file:
            sess_xml = etree.parse(sess_file)
            # Find the relevant dialogue annotation element.
            anns_above = sess_xml.find(settings.XML_ANNOTATIONS_ABOVE)
            anns_after = anns_above.find(settings.XML_ANNOTATIONS_AFTER)
            anns_after_idx = (anns_above.index(anns_after)
                              if anns_after is not None
                              else len(anns_above))
            found_anns = False
            if anns_after_idx > 0:
                anns_el = anns_above[anns_after_idx - 1]
                if anns_el.tag == settings.XML_ANNOTATIONS_ELEM:
                    found_anns = True
            if not found_anns:
                raise ValueError()
            anns_from_dummy = anns_el.findall(
                "./{ann_el}[@user='testres']".format(
                    ann_el=settings.XML_ANNOTATION_ELEM))
            anns_unlabeled = filter(lambda el: 'worker_id' not in el.attrib,
                                    anns_from_dummy)
            if not anns_unlabeled:
                raise ValueError()
            # Heuristic: take the last one of the potential dialogue annotation
            # XML elements.
            dg_ann_el = anns_unlabeled[-1]
            dg_ann_el.set('worker_id', str(judgment_data["worker_id"]))
            country = judgment_data.get('country', None)
            if country is not None:
                dg_ann_el.set('country', country)
            channel = judgment_data.get('external_type', None)
            if channel is not None:
                dg_ann_el.set('channel', channel)
        # Write the XML session file.
        with open(sess_fname, 'w') as sess_file:
            sess_file.write(etree.tostring(sess_xml,
                                           pretty_print=True,
                                           xml_declaration=True,
                                           encoding='UTF-8'))


    def create_dialogue_json(dg):
        json_str = ('{{"cid":"{cid}","code":"{code}","code_gold":"{gold}"}}'
                    .format(cid=dg.cid,
                            code=dg.code,
                            gold=dg.get_code_gold()))
        return json_str


    class JsonDialogueUpload(object):
        """
        A container for dialogues to be uploaded to CrowdFlower. The container
        is single-use only -- once uploaded, it can be disposed of.

        """
        # TODO: Implementing __len__ might be helpful...

        def __init__(self, dg_datas=None):
            """
            Creates a new JSON object to be uploaded to Crowdflower as job data
            for a dialogue.

            """
            self._uploaded = False
            self.data = dict()
            if dg_datas is not None:
                self.extend(dg_datas)

        def add(self, dg):
            uturns = UserTurn.objects.filter(dialogue=dg)
            if len(uturns) >= settings.MIN_TURNS:
                self.data.setdefault(get_job_id(dg), []).append(dg)

        def extend(self, dg_datas):
            for dg in dg_datas:
                self.add(dg)

        def upload(self, force=False, check_existing=True):
            if self._uploaded and not force:
                msg = 'Internal error: attempted to upload the data twice.'
                return False, msg
                # FIXME: Make these strange return tuples into exceptions.

            error_msgs = list()
            for job_id in self.data:
                # Check what units are currently uploaded for the job.
                success, cur_units = list_units(job_id)
                if success:
                    cur_cids = tuple(unit[u'cid']
                                     for unit in cur_units.values())
                else:
                    error_msgs.append('Could not retrieve existing units for '
                                      'job ID {jobid}.'.format(jobid=job_id))
                    continue
                # Build the JSON string describing the units.
                json_str = ''.join(create_dialogue_json(dg)
                                for dg in self.data[job_id]
                                if dg.cid not in cur_cids)
                # Upload to CF.
                if not json_str:
                    # If there are no dialogues to upload (all have already
                    # been uploaded before), take it as a success.
                    success = True
                else:
                    success, msg = upload_units(job_id, json_str)
                    if success:
                        for dg in self.data[job_id]:
                            success, msg = update_gold(dg)
                            if not success:
                                error_msgs.append(msg)
                if not success:
                    error_msgs.append(msg)

            if error_msgs:
                return False, '\n'.join(error_msgs)
            else:
                self._uploaded = True
                return True, None
