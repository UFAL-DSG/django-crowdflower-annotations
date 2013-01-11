#!/usr/bin/python
# -*- coding: UTF-8 -*-
import os

import settings
from transcription.crowdflower import list_units, upload_units,\
    unit_pair_from_cid, update_unit
from transcription.models import Transcription, UserTurn


# Check whether dialogues should be split into several CF jobs based on their
# price.
if hasattr(settings, 'CF_JOB_IDS'):
    price_classes = settings.CF_JOB_IDS
else:
    assert (hasattr(settings, 'CF_JOB_ID'),
            'Either CF_JOB_ID or CF_JOB_IDS has to be set in '
            'settings.py')
    price_classes = None


def get_job_id(dg):
    if price_classes is None:
        return settings.CF_JOB_ID
    else:
        try:
            # This selects the nearest lower price step.
            price_cat = max(filter(lambda step: step <= dg.transcription_price,
                                   price_classes))
        except ValueError:
            # Or, in case no price step is lower, the lowest price step
            # absolute.
            price_cat = min(price_classes)
        return price_classes[price_cat]


def is_gold(dg):
    return Transcription.objects.filter(dialogue_annotation__dialogue=dg,
                                        is_gold=True).exists()


def update_gold(dg):
    job_id = get_job_id(dg)
    success, unit_pair = unit_pair_from_cid(job_id, dg.cid)
    if not success:
        msg = unit_pair
        return False, msg
    unit_id, unit = unit_pair
    params = 'unit[state]={gold}'.format(
        gold=('true' if is_gold(dg) else unit['state']))
    success, errors = update_unit(job_id, unit_id, params)
    if not success:
        return False, errors
    return True, None


def update_price(dg):
    """Computes the price of a dialogue transcription in USD."""
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


def create_dialogue_json(dg, check_gold=True):
    if check_gold and is_gold(dg):
        extra_str = ',"_golden":"True"'
    else:
        extra_str = ''
    json_str = ('{{"cid":"{cid}","code":"{code}","code_gold":"{gold}"{extra}}}'
                .format(cid=dg.cid,
                        code=dg.code,
                        gold=dg.get_code_gold(),
                        extra=extra_str))
    return json_str


class JsonDialogueUpload(object):
    # TODO: Implementing __len__ might be helpful...

    def __init__(self):
        """Creates a new JSON object to be uploaded to Crowdflower as job data
        for a dialogue.

        """
        self._uploaded = False
        self.data = dict()

    def add(self, dg):
        self.data.setdefault(get_job_id(dg), []).append(dg)

    def extend(self, dg_datas):
        for dg in dg_datas:
            self.add(dg)

    def upload(self, force=False, check_existing=True):
        if self._uploaded and not force:
            return False, 'Internal error: attempted to upload the data twice.'
            # FIXME: Make these strange return tuples into exceptions.

        error_msgs = list()
        for job_id in self.data:
            # Check what units are currently uploaded for the job.
            success, cur_units = list_units(job_id)
            if success:
                cur_cids = tuple(unit[u'cid'] for unit in cur_units.values())
            else:
                error_msgs.append('Could not retrieve existing units for job '
                                  'ID {jobid}.'.format(jobid=job_id))
                continue
            # Build the JSON string describing the units.
            json_str = ''.join(create_dialogue_json(dg)
                               for dg in self.data[job_id]
                               if dg.cid not in cur_cids)
            # Upload to CF.
            if not json_str:
                # If there are no dialogues to upload (all have already been
                # uploaded before), take it as a success.
                success = True
            else:
                success, msg = upload_units(job_id, json_str)
            if not success:
                error_msgs.append(msg)

        if error_msgs:
            return False, '\n'.join(error_msgs)
        else:
            self._uploaded = True
            return True, None
