#!/usr/bin/python
# -*- coding: UTF-8 -*-
import json
from subprocess import call
from tempfile import TemporaryFile

import settings

CF_URL_START = "https://api.crowdflower.com/v1/"


def contact_cf(cf_url, json_str=None, verb='POST'):
    # Create a file for the response from CF.
    try:
        upload_outfile = TemporaryFile()
    except:
        error_msgs = ["Output from `curl' could not be obtained.\n"]
        upload_outfile = None
    else:
        error_msgs = list()
    # Build the curl command line.
    if json_str is None:
        curl_args = ['curl', '-X', verb, cf_url]
    else:
        curl_args = ['curl', '-X', verb, '-d', json_str, '-H',
                     'Content-Type: application/json', cf_url]
    # Call the command.
    cf_retcode = call(curl_args, stdout=upload_outfile, stderr=None)
    # Check for errors.
    cf_outobj = None
    if upload_outfile is not None:
        upload_outfile.seek(0)
        cf_outobj = json.load(upload_outfile)
        upload_outfile.close()
    if cf_retcode != 0:
        if cf_outobj is not None:
            try:
                error_msgs.append(cf_outobj['error']['message'])
            except KeyError:
                error_msgs.append('(no message)')
        else:
            error_msgs.append('(no message)')
        # In case of lack of success, return also the error messages.
        return False, cf_outobj, error_msgs
    # Return the returned object in case of success.
    return True, cf_outobj, tuple()


def list_units(job_id):
    # Check what units are currently uploaded for the job.
    cf_url = '{start}jobs/{jobid}/units.json?key={key}'.format(
        start=CF_URL_START,
        jobid=job_id,
        key=settings.CF_KEY)
    success, cf_outobj, errors = contact_cf(cf_url, verb='GET')
    if success:
        # The `cf_outobj' is expected to be a dictionary of the following
        # format:
        # { unit_id -> { u'cid' -> cid,
        #                u'code' -> code,
        #                u'code_gold' -> code_gold },
        #   ... }
        return True, cf_outobj
    else:
        return False, errors


def upload_units(job_id, json_str):
    # Communicate the new data to CrowdFlower via the CF API.
    cf_url = '{start}jobs/{jobid}/upload.json?key={key}'.format(
        start=CF_URL_START,
        jobid=job_id,
        key=settings.CF_KEY)
    success, msg, error_msgs = contact_cf(cf_url, json_str=json_str)
    if success:
        return True, None
    else:
        lead = 'job {jobid}: '.format(jobid=job_id)
        error_msg = '\n'.join((lead + msg) for msg in error_msgs)
        return False, error_msg
