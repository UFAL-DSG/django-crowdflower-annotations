#!/usr/bin/python
# -*- coding: UTF-8 -*-
# TODO: Reimplement without backing off to using the external program curl.
from __future__ import unicode_literals

import httplib
import json
from lru_cache import lru_cache
import os.path
# import shutil
# from subprocess import call
# from tempfile import TemporaryFile
from urllib import urlencode

import settings
from util import get_log_path

CF_URL_START = "https://api.crowdflower.com/v1/"


def _contact_cf(cf_url_part, params=None, json_str=None, verb='POST',
                log=settings.LOG_CURL):
    """
    Note that specifying both `data' and `json_str' is not supported and the
    `data' argument will be silently ignored in such a case.

    """

    error_msgs = list()
    serious_errors = False

    # Create a log file.
    try:
        if log:
            logfile = open(get_log_path(settings.CURLLOGS_DIR), 'w')
        else:
            logfile = None
    except Exception as er:
        error_msg = "Output from `curl' could not be logged.\n"
        error_msg += 'The original exception said: "{er}".\n'.format(er=er)
        error_msgs += [error_msg]
        logfile = None

    # # Create a file for the response from CF.
    # try:
    #     upload_outfile = TemporaryFile()
    # except Exception as er:
    #     error_msg = "Output from `curl' could not be obtained.\n"
    #     error_msg += 'The original exception said: "{er}".\n'.format(er=er)
    #     error_msgs += [error_msg]
    #     upload_outfile = None
    #     serious_errors = True

    # Build the HTTP params.
    if json_str is None:
        headers = dict()
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        if params is not None:
            params_str = urlencode(params)
        else:
            params_str = ''
    else:
        headers = {'Content-Type': 'application/json; charset=UTF-8'}
        params_str = json_str
    cf_url = '/v1/{start}.json?key={key}'.format(start=cf_url_part,
                                                 key=settings.CF_KEY)
    # # Build the curl command line.
    # cf_url = '{start}{arg}.json?key={key}'.format(start=CF_URL_START,
    #                                               arg=cf_url_part,
    #                                               key=settings.CF_KEY)
    # if json_str is None:
    #     if data is not None:
    #         curl_args = ['curl', '-X', verb, '-d', data, cf_url]
    #     else:
    #         curl_args = ['curl', '-X', verb, cf_url]
    # else:
    #     curl_args = ['curl', '-X', verb, '-d', json_str, '-H',
    #                  'Content-Type: application/json', cf_url]

    # Make the connection, retrieve results.
    try:
        cf_conn = httplib.HTTPSConnection('api.crowdflower.com')
    except:
        cf_conn = httplib.HTTPConnection('api.crowdflower.com')
    try:
        cf_conn.request(verb, cf_url, params_str, headers)
        cf_res = cf_conn.getresponse()
        try:
            cf_out = cf_res.read().decode('UTF-8')
        except:
            cf_out = None
    finally:
        cf_conn.close()

    # Log.
    if log and logfile:
        headers_str = '; '.join('{key}: {val}'.format(key=key, val=val)
                                for key, val in headers.iteritems())
        logfile.write(("Call \"request('{verb}', '{url}', '{params}', "
                       "'{headers}')\"\n----\nResponse: {status} {reason}\n"
                       "----\nReturned:\n{data}\n").format(
                      verb=verb, url=cf_url, params=params_str,
                      headers=headers_str, status=cf_res.status,
                      reason=cf_res.reason,
                      data=cf_out).encode('UTF-8'))

    # # Call the command.
    # if log and logfile:
    #     logfile.write('Command: {cmd}\n----\nReturned: \n'
    #                   .format(cmd=' '.join(
    #                       map(lambda arg: arg if ' ' not in arg else
    #                           "'{arg}'".format(arg=arg), curl_args))))
    # cf_retcode = call(curl_args, stdout=upload_outfile, stderr=None)
    # if log and logfile:
    #     if upload_outfile:
    #         upload_outfile.seek(0)
    #         logfile.write(upload_outfile.read())
    #     logfile.write('\n----\nReturn code: {code}\n'.format(
    #         code=cf_retcode))

    # Check for errors.
    try:
        cf_outobj = json.loads(cf_out) if cf_out else ''
    except ValueError:
        cf_outobj = None
        error_msgs += ['Unexpected reply from CF: """{cf_out}"""\n'
                       .format(cf_out=cf_out)]
        serious_errors = True
    # TODO Check whether `cf_res.status' did not indicate failure.
    if serious_errors:
        if cf_outobj is not None:
            try:
                error_msgs.append(cf_outobj['error']['message'])
            except KeyError:
                error_msgs.append('(no message)')
        else:
            error_msgs.append('(no message)')
        # In case of lack of success, return also the error messages.
        return False, cf_outobj, error_msgs

    # # Check for errors.
    # cf_outobj = None
    # if upload_outfile is not None:
    #     upload_outfile.seek(0)
    #     try:
    #         cf_outobj = json.load(upload_outfile)
    #     except ValueError:
    #         cf_outobj = None
    #         upload_outfile.seek(0)
    #         error_msgs += ['Unexpected reply from CF: """{body}"""\n'.format(
    #                        body=upload_outfile.read())]
    #         serious_errors = True
    #     finally:
    #         upload_outfile.close()
    # if cf_retcode != 0 or serious_errors:
    #     if cf_outobj is not None:
    #         try:
    #             error_msgs.append(cf_outobj['error']['message'])
    #         except KeyError:
    #             error_msgs.append('(no message)')
    #     else:
    #         error_msgs.append('(no message)')
    #     # In case of lack of success, return also the error messages.
    #     return False, cf_outobj, error_msgs

    # Return the returned object in case of success.
    return True, cf_outobj, error_msgs


@lru_cache(maxsize=10)
def list_units(job_id):
    # Check what units are currently uploaded for the job.
    cf_url = 'jobs/{jobid}/units'.format(jobid=job_id)
    success, cf_outobj, errors = _contact_cf(cf_url, verb='GET')
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


def fire_gold_hooks(job_id):
    cf_url = 'jobs/{job_id}/golds/fire_webhooks'.format(job_id=job_id)
    success, cf_outobj, errors = _contact_cf(cf_url, verb='GET')
    if success:
        return True, cf_outobj
    else:
        return False, errors


def upload_units(job_id, json_str):
    # Communicate the new data to CrowdFlower via the CF API.
    cf_url = 'jobs/{jobid}/upload'.format(jobid=job_id)
    success, msg, error_msgs = _contact_cf(cf_url, json_str=json_str)
    if success:
        list_units.cache_clear()
        unit_id_from_cid.cache_clear()
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
        success, msg, error_msgs = _contact_cf(cf_url, verb='GET')
        if success:
            return True, (unit_id, msg)
        else:
            return False, ('Detailed unit information could not be retrieved '
                           'from the CrowdFlower job {jobid} for the '
                           'dialogue CID {cid}.').format(cid=cid, jobid=job_id)


@lru_cache(maxsize=2000)
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
    success, msg, error_msgs = _contact_cf(cf_url, verb='PUT', params=params)
    if success:
        return True, None
    else:
        lead = 'job {jobid}, unit {unitid}: '.format(jobid=job_id,
                                                     unitit=unit_id)
        return False, (lead + error_msgs)


def create_job(cents_per_unit,
               judgments_per_unit=1,
               units_per_assignment=4,
               pages_per_assignment=4,
               gold_per_assignment=1,
               job_cml_path=None, **kwargs):
    # Interpret arguments.
    if job_cml_path is None:
        job_cml_path = os.path.join(settings.PROJECT_DIR, 'transcription',
                                    'crowdflower', 'job.cml')
    # Build all the params.
    job_params = dict()
    params = {'job': job_params}
    with open(job_cml_path) as job_file:
        job_params['cml'] = job_file.read()
    job_params['confidence_fields'] = ["code"]
    job_params['title'] = 'Dialogue transcription – {price}c'.format(
        price=((units_per_assignment * cents_per_unit) / units_per_assignment))
    job_params['judgments_per_unit'] = judgments_per_unit
    job_params['units_per_assignment'] = units_per_assignment
    job_params['pages_per_assignment'] = pages_per_assignment
    job_params['language'] = 'en'
    # FIXME The following needs to be less than units_per_assignment. Check it,
    # potentially complaining about wrong arguments.
    job_params['gold_per_assignment'] = gold_per_assignment
    # XXX This does not seem to work with Crowdflower.
#     job_params['included_countries'] = ('[{"code":"AU", "name":"Australia"},'
#                                     '{"code":"CA", "name":"Canada"},'
#                                     '{"code":"GB", "name":"United Kingdom"},'
#                                     '{"code":"IE", "name":"Ireland"},'
#                                     '{"code":"IM", "name":"Isle of Man"},'
#                                     '{"code":"NZ", "name":"New Zealand"},'
#                                     '{"code":"US", "name":"United States"}]')
    job_params['instructions'] = """\
        Please, write down what is said in the provided recordings. The
        recordings capture a dialogue between a human and a computer. The
        computer utterances are known, so only the human's utterances need to
        be transcribed."""
    # webhook
    job_params['webhook_uri'] = '{domain}{site}log-work'.format(
        domain=settings.DOMAIN_URL,
        site=settings.SUB_SITE)
    # skills
    job_params['minimum_requirements'] = {"priority": 1,
                                          "skill_scores":
                                            {"bronze_v1": 1},
                                          "min_score": 1}
    job_params.update(kwargs)

    # Create the job.
    cf_url = 'jobs'
    success, msg, error_msgs = _contact_cf(cf_url, verb='POST',
                                           json_str=json.dumps(params))
    if success:
        job_id = msg['id']
        # Set up the workers' countries included.
        params = [('job[included_countries][]', country)
                  for country in ("AU", "CA", "GB", "IE", "IM", "NZ", "US")]
        # Set up the gold field.
        params.append(('check', 'code'))
        cf_url = 'jobs/{jobid}'.format(jobid=job_id)
        update_success, update_out, update_msgs = _contact_cf(
            cf_url, verb='PUT', params=params)
        if not update_success:
            lead = ('Error when updating parameters of the new job (job ID: '
                    '{jobid}: ').format(jobid=job_id)
            return False, (lead + ' ||| '.join(update_msgs))
        return True, msg
    else:
        lead = 'Error when creating new job: '
        return False, (lead + ' ||| '.join(error_msgs))
