#!/usr/bin/python
# -*- coding: UTF-8 -*-
import json
from subprocess import call
from tempfile import TemporaryFile

import settings

CF_URL_START = "https://api.crowdflower.com/v1/"


def contact_cf(cf_url_part, data=None, json_str=None, verb='POST'):
    """Note that specifying both `data' and `json_str' is not supported and
    the `data' argument will be silently ignored in such a case.

    """
    # Create a file for the response from CF.
    try:
        upload_outfile = TemporaryFile()
    except:
        error_msgs = ["Output from `curl' could not be obtained.\n"]
        upload_outfile = None
    else:
        error_msgs = list()
    # Build the curl command line.
    cf_url = '{start}{arg}.json?key={key}'.format(start=CF_URL_START,
                                                  arg=cf_url_part,
                                                  key=settings.CF_KEY)
    if json_str is None:
        if data is not None:
            curl_args = ['curl', '-X', verb, '-d', data, cf_url]
        else:
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
        try:
            cf_outobj = json.load(upload_outfile)
        except ValueError:
            cf_outobj = None
            # DEBUG
            upload_outfile.seek(0)
            raise ValueError('Unexpected reply from CF: {file}'.format(
                file=upload_outfile.read()))
        finally:
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
    cf_url = 'jobs/{jobid}/units'.format(jobid=job_id)
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
    cf_url = 'jobs/{jobid}/upload'.format(jobid=job_id)
    success, msg, error_msgs = contact_cf(cf_url, json_str=json_str)
    if success:
        return True, None
    else:
        lead = 'job {jobid}: '.format(jobid=job_id)
        error_msg = '\n'.join((lead + msg) for msg in error_msgs)
        return False, error_msg


def unit_pair_from_cid(job_id, cid):
    success, unit_id = unit_id_from_cid(job_id, cid)
    if not success:
        return False, unit_id
    else:
        cf_url = 'jobs/{jobid}/units/{unitid}'.format(jobid=job_id,
                                                      unitid=unit_id)
        success, msg, error_msgs = contact_cf(cf_url, verb='GET')
        if success:
            return True, (unit_id, msg)
        else:
            return False, ('Detailed unit information could not be retrieved '
                           'from the CrowdFlower job {jobid} for the '
                           'dialogue CID {cid}.').format(cid=cid, jobid=job_id)


def unit_id_from_cid(job_id, cid):
    success, msg = list_units(job_id)
    if not success:
        return False, msg
    else:
        ret = None
        for unit_id, unit in msg.iteritems():
            if unit[u'cid'] == cid:
                ret = unit_id
                break
        if ret is None:
            return False, ('No unit found for the dialogue CID {cid} in the '
                           'CrowdFlower job {jobid}.').format(cid=cid,
                                                              jobid=job_id)
        else:
            return True, ret


def update_unit(job_id, unit_id, params):
    cf_url = 'jobs/{jobid}/units/{unitid}'.format(jobid=job_id, unitid=unit_id)
    success, msg, error_msgs = contact_cf(cf_url, verb='PUT', data=params)
    if success:
        return True, None
    else:
        lead = 'job {jobid}, unit {unitid}: '.format(jobid=job_id,
                                                     unitit=unit_id)
        return False, (lead + error_msgs)
