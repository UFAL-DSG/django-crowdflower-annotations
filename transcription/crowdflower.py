#!/usr/bin/python
# -*- coding: UTF-8 -*-
from collections import Sequence
import cStringIO as StringIO
import csv
import httplib
import json
from lru_cache import lru_cache
import os
import os.path
import re
import time
from urllib import urlencode
import urllib2
import zipfile

import settings

from dg_util import is_gold
if settings.USE_CF:
    from models import CrowdflowerJob
else:
    from models import PriceClass
from settings import SettingsException
from session_xml import XMLSession, record_judgments, update_worker_stats
from transcription.models import UserTurn
from util import get_log_path

CF_URL_START = "https://api.crowdflower.com"
HOOKNAMES2CSVNAMES = {
    "city": "_city",
    "region": "_region",
    "created_at": "_created_at",
    "unit_id": "_unit_id",
    "country": "_country",
    "tainted": "_tainted",
    "trust": "_trust",
    "id": "_id",
    "external_type": "_channel",
    "worker_id": "_worker_id",
    "missed": "_missed",
    "started_at": "_started_at",
    "golden": "_golden",
}

default_job_cml_path = os.path.join(settings.PROJECT_DIR, 'transcription',
                                    'templates', 'crowdflower',
                                    'job-linked.cml')
try:
    _LOG_CURL = settings.LOG_CURL
except AttributeError:
    _LOG_CURL = False


class CrowdflowerMessage(object):
    def __init__(self, status, obj=None, content_type='json'):
        """
        Arguments:
            status -- the HTTP response status
            obj -- parsed object returned by Crowdflower or None
            content_type -- either 'json' or 'csv'

        """
        self.status = status
        self.obj = obj
        self.content_type = content_type


class CrowdflowerException(Exception):
    def __init__(self, cf_msg, er_msgs=None):
        self.cf_msg = cf_msg  # an instance of CrowdflowerMessage
        if er_msgs is None:
            self.er_msgs = list()
        else:
            self.er_msgs = er_msgs


def _contact_cf(cf_url_part, data=None, type_ours='data', type_theirs='json',
                verb=None, log=_LOG_CURL, headers=None, out_zipped=False,
                out_enc='UTF-8'):
    """

    Arguments:
        data -- data to send
        type_ours -- type of content we send out; one of 'json', 'csv' or
            'data'
        type_theirs -- type of the content asked for from Crowdflower; either
            'json' or 'csv'.  This also determines the "extension" of the file
            path part of the URL.
        verb -- one of the REST verbs; if none is specified, GET or POST will
            be used, depending on whether any data were supplied
        log -- should a log file be written?
        headers -- a mapping specifying any extra HTTP headers to use
        out_zipped -- is the expected output a single zipped file?
            (default: False)
        out_enc -- name of the encoding the output object is assumed to have;
            default: None (no decoding is attempted, the string is returned
            verbatim)

    """

    # Default the verb to GET or POST, depending on the presence of data.
    if verb is None:
        verb = 'GET' if data is None else 'POST'
    use_urllib2 = (verb in ('GET', 'POST') and type_ours == 'data'
                   and headers is None)

    # Initialisation.
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

    # Build the HTTP data.
    if type_ours == 'csv':
        headers_final = {'Content-Type': 'text/csv; charset=UTF-8'}
        data_str = data
    elif type_ours == 'json':
        headers_final = {'Content-Type': 'application/json; charset=UTF-8'}
        data_str = data
    elif type_ours == 'data':
        headers_final = {'Content-Type': 'application/x-www-form-urlencoded'}
        if data is not None:
            data_str = urlencode(data)
        else:
            data_str = ''
    else:
        raise Exception('Cannot handle our specified content type: "{typ}".'
                        .format(typ=type_ours))

    # Update with the extra headers supplied.
    if headers is not None:
        headers_final.update(headers)
    cf_url = '/v1/{start}.{ext}?key={key}'.format(start=cf_url_part,
                                                  ext=type_theirs,
                                                  key=settings.CF_KEY)

    # Make the connection, retrieve results.
    # Special case: use urllib2 when possible.
    cf_out = None
    cf_res = None
    if use_urllib2:
        try:
            cf_url_whole = CF_URL_START + cf_url
            cf_res = urllib2.urlopen(cf_url_whole, data_str or None)
        except urllib2.HTTPError as er:
            status = er.code
            reason = er.msg
        else:
            status = 200
            reason = 'OK'
        try:
            cf_out = cf_res.read()
        except Exception as ex:
            error_msgs.append(unicode(ex))
            serious_errors = True
    # General case: use httplib.
    else:
        try:
            cf_conn = httplib.HTTPSConnection('api.crowdflower.com')
        except:
            cf_conn = httplib.HTTPConnection('api.crowdflower.com')
        try:
            cf_conn.request(verb, cf_url, data_str, headers_final)
            cf_res = cf_conn.getresponse()
            status = cf_res.status
            reason = cf_res.reason
            cf_out = cf_res.read()
        except Exception as ex:
            error_msgs.append(unicode(ex))
            serious_errors = True
        finally:
            cf_conn.close()

    # Run through character decoding if asked to.
    if out_enc is not None and cf_out is not None:
        try:
            cf_out = cf_out.decode(out_enc)
        except Exception as ex:
            error_msgs.append(unicode(ex))

    # Log.
    if log and logfile:
        headers_str = '; '.join('{key}: {val}'.format(key=key, val=val)
                                for key, val in headers_final.iteritems())
        msg = ("Call \"request('{verb}', '{url}', '{params}', '{headers}')\"\n"
               "----\n"
               "Response: {status} {reason}\n"
               "----\n"
               "Returned:\n").format(verb=verb, url=cf_url, params=data_str,
                                     headers=headers_str, status=status,
                                     reason=reason)
        try:
            msg += cf_out + '\n'
        except UnicodeEncodeError:
            try:
                msg = str(msg) + cf_out + '\n'
            except:
                pass
        try:
            msg = msg.encode('UTF-8')
        except:
            pass
        logfile.write(msg)

    # Process the Crowdflower response.
    try:
        # Unzip if asked to.
        if out_zipped:
            try:
                zip_contents = zipfile.ZipFile(StringIO.StringIO(cf_out))
                with zip_contents.open(zip_contents.infolist()[0]) as zip_file:
                    cf_out = zip_file.read()
            except Exception as ex:
                error_msgs.append(unicode(ex))
                serious_errors = True
                raise ValueError()  # To be caught just below.

        if type_theirs == 'json':
            cf_outobj = json.loads(cf_out) if cf_out else None
        elif type_theirs == 'csv':
            if cf_out:
                cf_out_sio = StringIO.StringIO(cf_out)
                cf_outobj = list(csv.reader(cf_out_sio))
            else:
                cf_outobj = None
        else:
            cf_outobj = cf_out or None
            serious_errors = True
            error_msgs.append('Unknown content type for the Crowdflower '
                              'returned object specified: "{ct}".'
                              .format(ct=type_theirs))
    except ValueError:
        cf_outobj = None
        error_msgs.append('Unexpected reply from CF: """{cf_out}"""\n'
                          .format(cf_out=cf_out))
        serious_errors = True
    # Check whether `status' did not indicate failure.
    serious_errors |= (not str(status).startswith('2'))

    # Raise or return.
    if serious_errors:
        if cf_outobj is not None:
            try:
                error_msgs.append(cf_outobj['error']['message'])
            except KeyError:
                error_msgs.append('(no message)')
        msg = ('Complete message from Crowdflower:\n'
               'Response {code} ({reason})\n'
               '{msg}').format(code=status, reason=reason, msg=cf_out or '')
        error_msgs.append(msg)
        # In case of lack of success, raise an informative exception.
        cf_msg = CrowdflowerMessage(status=status, obj=cf_outobj)
        raise CrowdflowerException(cf_msg=cf_msg, er_msgs=error_msgs)

    # Return the returned object in case of success.
    cf_msg = CrowdflowerMessage(status=status, obj=cf_outobj)
    return cf_msg


def _wait_for_cf(*args, **kwargs):
    """Calls _contact_cf as long as the response is not 200 OK.

    Keyword arguments:
        max_waits -- maximum number of tries to contact Crowdflower (and get
            the 200 OK response)
        wait_secs -- number of seconds between subsequent tries
        other arguments -- will be passed on to _contact_cf

    """

    # Interpret the arguments.
    max_waits = kwargs.get('max_waits', settings.CF_MAX_WAITS)
    wait_secs = kwargs.get('wait_secs', settings.CF_WAIT_SECS)

    # Wait for an OK response from CF.
    for _ in xrange(max_waits):
        try:
            cf_msg = _contact_cf(*args, **kwargs)
        except CrowdflowerException as cex:
            return False, '\n'.join(cex.er_msgs)
        else:
            if str(cf_msg.status) != '200':
                time.sleep(wait_secs)
                continue
            else:
                return True, cf_msg
    else:
        msg = 'Timed out when waiting for Crowdflower.'
        return False, msg


def _get_job_report(job_id):
    cf_url = 'jobs/{jobid}'.format(jobid=job_id)

    # Wait for an OK response from CF.
    success, msg = _wait_for_cf(cf_url, type_theirs='csv', out_zipped=True,
                                out_enc=None)
    # Process the response -- exceptions.
    if not success:
        return False, msg
    if msg.obj is None:
        msg = 'No judgments reported by Crowdflower.'
        return False, msg

    # In case of success, return the message.
    return True, msg


def _cf_json_getitem(cf_json, key, deser=True):
    """Wrapper for getitem that additionally deserializes JSON values.

    Arguments:
        cf_json -- object originally received as JSON from Crowdflower
        key -- key to use to index `cf_json'
        deser -- whether to deserialize the value of `key' if it looks like
            a JSON-serialized object

    Returns value for the key or raises KeyError if the key was not found. If
    asked to deserialize, the cf_json object's value for key is altered as
    a side effect.

    """

    try:
        val = cf_json[key]
    except IndexError:
        raise KeyError()
    if isinstance(val, basestring):
        try:
            val = json.loads(val)
        except:
            pass
        else:
            cf_json[key] = val
    return val


def _get_keys_iterator(collection):
    if isinstance(collection, basestring):
        return None
    elif isinstance(collection, Sequence):
        keys = xrange(len(collection))
    else:
        if hasattr(collection, '__iter__'):
            keys = collection
        else:
            return None
    return iter(keys)


def _find_in_cf_json(cf_json, key, preferred_path=None):
    """
    Finds the value of a given key anywhere somewhere in JSON structure
    returned by CF.

    This function may be given a preferred path, specifying where the key
    should be found in the JSON. If it is not there, the JSON is searched for
    all dictionaries and their keys checked for match with `key'. JSON
    structures serialized into strings may be deserialized on the fly.

    Arguments:
        cf_json -- the JSON structure (i.e., an object originally received as
            JSON from Crowdflower)
        key -- dictionary key for which to look up the value
        preferred_path -- an iterable of indices leading to the dictionary
            where `key' would normally be found. If it is there, its value is
            returned. If not, it is looked for everywhere else in the JSON.

    Returns a tuple (found on preferred path, values) for the key or raises
    KeyError if that key was not found. In the former case, a list of values
    for all occurrences of `key' is returned.

    """

    # Try to find the key at the preferred path.
    if preferred_path is not None:
        cur_json = cf_json
        for cur_key in preferred_path:
            try:
                cur_json = _cf_json_getitem(cur_json, cur_key)
            except KeyError:
                break
            except TypeError:
                break
        else:
            try:
                return (True, [_cf_json_getitem(cur_json, key)])
            except:
                pass

    # If it was not found there, go through the whole structure.
    levels = [cf_json]
    # :: [embedding level-> current object to iterate at that level]
    next_iter = _get_keys_iterator(cf_json)
    if next_iter is None:
        raise KeyError()
    level_keys = [next_iter]
    # :: [embedding level-> iterator for keys on that level]
    values = list()  # the eventual return value (second item of)

    # Traverse the structure and record all values found.
    while levels:
        last_level = levels[-1]
        last_keys = level_keys[-1]

        # Go deeper if possible.
        try:
            last_key = next(last_keys)
        except StopIteration:
            # If no more keys are available to this object, go back.
            del levels[-1]
            del level_keys[-1]
        else:
            next_level = _cf_json_getitem(last_level, last_key)
            if last_key == key:
                values.append(next_level)

            next_iter = _get_keys_iterator(next_level)
            if next_iter is not None:
                levels.append(next_level)
                level_keys.append(_get_keys_iterator(next_level))

    # Return.
    if values:
        return (preferred_path is None, values)
    else:
        raise KeyError()


def _find_unique_in_cf_json(cf_json, key, preferred_paths=None):
    if preferred_paths is None:
        preferred_paths = [None]

    for path in preferred_paths:
        using_known_path, values = _find_in_cf_json(cf_json, key, path)
        if using_known_path or len(values) == 1:
            return values[0]
        if all(lambda otherval: otherval == values[0], values[1:]):
            return values[0]

    msg = ('Structure of JSONs from Crowdflower has changed. Cannot '
           'find the "{key}" key reliably.'.format(key=key))
    raise CrowdflowerException(msg)


@lru_cache(maxsize=10)
def list_units(job_id):
    # Check what units are currently uploaded for the job.
    cf_url = 'jobs/{jobid}/units'.format(jobid=job_id)
    try:
        cf_msg = _contact_cf(cf_url)
    except CrowdflowerException as cex:
        return False, cex.er_msgs
    else:
        # The `cf_msg.obj' is expected to be a dictionary of the following
        # format:
        # { unit_id -> { u'cid' -> cid,
        #                u'code' -> code,
        #                u'code_gold' -> code_gold },
        #   ... }
        unit_dict = cf_msg.obj or dict()
        return True, unit_dict


def fire_gold_hooks(job_id):
    cf_url = 'jobs/{job_id}/golds/fire_webhooks'.format(job_id=job_id)
    try:
        cf_msg = _contact_cf(cf_url)
    except CrowdflowerException as cex:
        return False, cex.er_msgs
    else:
        return True, cf_msg.obj


def upload_units(job_id, data, content_type='json'):
    """Uploads new units to Crowdflower to the job specified.

    Arguments:
        job_id -- ID of the Crowdflower job
        data -- string representation of the data (of the type corresponding to
            `content_type')
        content_type -- content type of the data, either 'json' or 'csv'
            (default: 'json')

    """

    # Check the arguments.
    if content_type == 'json':
        extra_headers = {'Content-Type': 'text/json'}
    elif content_type == 'csv':
        extra_headers = {'Content-Type': 'text/csv'}
    else:
        raise ValueError('The `content_type\' argument must be one of '
                         '("json", "csv").')

    # Communicate the new data to CrowdFlower via the CF API.
    cf_url = 'jobs/{jobid}/upload'.format(jobid=job_id)
    try:
        cf_msg = _contact_cf(cf_url, type_ours=content_type, data=data,
                             headers=extra_headers)
    except CrowdflowerException as cex:
        lead = 'job {jobid}: '.format(jobid=job_id)
        error_msg = '\n'.join((lead + msg) for msg in cex.er_msgs)
        return False, error_msg
    else:
        list_units.cache_clear()
        unit_id_from_cid.cache_clear()
        return True, None


def unit_pair_from_cid(job_id, cid):
    success, unit_id = unit_id_from_cid(job_id, cid)
    if not success:
        return False, unit_id
    else:
        cf_url = 'jobs/{jobid}/units/{unitid}'.format(jobid=job_id,
                                                      unitid=unit_id)
        er_msg_tpt = ('Detailed unit information could not be retrieved '
                      'from the CrowdFlower job {jobid} for the '
                      'dialogue CID {cid}.')
        try:
            cf_msg = _contact_cf(cf_url, verb='GET')
        except CrowdflowerException as cex:
            return False, er_msg_tpt.format(cid=cid, jobid=job_id)
        else:
            if cf_msg.obj is None:
                return False, er_msg_tpt.format(cid=cid, jobid=job_id)
            return True, (unit_id, cf_msg.obj)


@lru_cache(maxsize=2000)
def unit_id_from_cid(job_id, cid):
    success, msg = list_units(job_id)
    if not success:
        return False, msg
    else:
        ret = None
        for unit_id, unit in msg.iteritems():
            if unit['cid'] == cid:
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
    try:
        cf_msg = _contact_cf(cf_url, verb='PUT', data=params)
    except CrowdflowerException as cex:
        lead = 'job {jobid}, unit {unitid}: '.format(jobid=job_id,
                                                     unitit=unit_id)
        return False, (lead + cex.er_msgs)
    else:
        return True, None


def create_job(cents_per_unit,
               store_job_id=True,
               judgments_per_unit=1,
               units_per_assignment=4,
               pages_per_assignment=4,
               gold_per_assignment=1,
               job_cml_path=None,
               title=None,
               instructions=None,
               bronze=True,
               included_countries=None,
               **kwargs):
    # Interpret arguments.
    if job_cml_path is None:
        job_cml_path = default_job_cml_path
    # It seems to make more sense to call the job by the price per assignment,
    # not per unit.
    # job_price = (units_per_assignment * cents_per_unit)
    #   / units_per_assignment
    job_price = units_per_assignment * cents_per_unit
    if title is None:
        title = 'Dialogue transcription – {price}c'
    if instructions is None:
        instructions = re.sub(' +', ' ', """\
            Please, write down what is said in the provided recordings. The
            recordings capture a dialogue between a human and a computer. The
            computer utterances are known, so only the human's utterances need
            to be transcribed.""").strip().replace('\n ', '\n')
    if included_countries is None:
        included_countries = ("AU", "CA", "GB", "IE", "IM", "NZ", "US")

    # Build all the params.
    job_params = dict()
    params = {'job': job_params}
    with open(job_cml_path) as job_file:
        job_params['cml'] = job_file.read()
    job_params['confidence_fields'] = ["code"]
    job_params['title'] = title.format(price=job_price)
    job_params['judgments_per_unit'] = judgments_per_unit
    job_params['units_per_assignment'] = units_per_assignment
    job_params['pages_per_assignment'] = pages_per_assignment
    job_params['language'] = 'en'
    # FIXME The following needs to be less than units_per_assignment. Check it,
    # potentially complaining about wrong arguments.
    job_params['gold_per_assignment'] = gold_per_assignment
    job_params['instructions'] = instructions
    # webhook
    if settings.USE_WEBHOOKS:
        job_params['webhook_uri'] = '{domain}{site}/log-work'.format(
            domain=settings.DOMAIN_URL,
            site=settings.SUB_SITE)
    # skills
    # (copied from a JSON retrieved from Crowdflower for a manually set up job)
    if bronze:
        job_params['minimum_requirements'] = {"priority": 1,
                                              "skill_scores": {"bronze_v1": 1},
                                              "min_score": 1}
    job_params.update(kwargs)

    # Create the job.
    cf_url = 'jobs'
    er_msg_lead = 'Error when creating new job: '
    try:
        cf_msg = _contact_cf(cf_url, type_ours='json', data=json.dumps(params),
                             out_enc=None)

    # If the creation of the job itself was unsuccessful,
    except CrowdflowerException as cex:
        return False, (er_msg_lead + ' ||| '.join(cex.er_msgs))
    if cf_msg.obj is None:
        return False, er_msg_lead + 'empty response from Crowdflower'

    # If the job was successfully created,
    else:
        job_id = cf_msg.obj['id']

        # Modify some more parameters. This has not been done above as it seems
        # to not work with Content-Type: application/json, whereas some of the
        # above, on the contrary, seemed to require exactly that format.
        #
        # Set up the gold field.
        params = (('check', 'code'), )
        # Make the request and check the response.
        cf_url = 'jobs/{jobid}/gold'.format(jobid=job_id)
        try:
            cf_msg = _contact_cf(cf_url, verb='PUT', data=params)
        except CrowdflowerException as cex:
            lead = ('Error when setting the gold field of the new job (job '
                    'ID: {jobid}: ').format(jobid=job_id)
            return False, (lead + ' ||| '.join(cex.er_msgs))

        # Set up the workers' countries included.
        params = [('job[included_countries][]', country)
                  for country in ("AU", "CA", "GB", "IE", "IM", "NZ", "US")]
        # Make the request and check the response.
        cf_url = 'jobs/{jobid}'.format(jobid=job_id)
        er_msg_lead_tpt = ('Error when updating allowed countries of the new '
                           'job (job ID: {jobid}: ')
        try:
            cf_msg = _contact_cf(cf_url, verb='PUT', data=params)
        except CrowdflowerException as cex:
            lead = er_msg_lead_tpt.format(jobid=job_id)
            return False, (lead + ' ||| '.join(cex.er_msgs))
        if cf_msg.obj is None:
            lead = er_msg_lead_tpt.format(jobid=job_id)
            return False, (lead + 'empty response from Crowdflower')

        # If everything has gone alright and the new job's ID should be stored,
        if store_job_id:
            price_class_handler.store_job_id(job_id, cents_per_unit)

        return True, cf_msg.obj


def cancel_job(jobid):
    cf_url = 'jobs/{jobid}/cancel'.format(jobid=jobid)
    try:
        _contact_cf(cf_url)
    except CrowdflowerException as cex:
        return False, '\n'.join(cex.er_msgs)
    else:
        return True, ''


def delete_job(jobid, force_delete_from_db=True):
    # Try to cancel the job in case it is running.
    success, msgs = cancel_job(jobid)
    if success:
        time.sleep(settings.CF_WAIT_SECS)

    # Delete the job from Crowdflower.
    cf_url = 'jobs/{jobid}'.format(jobid=jobid)
    try:
        cf_msg = _contact_cf(cf_url, verb='DELETE')
    except CrowdflowerException as cex:
        success = False
        ret_msg = '\n'.join(cex.er_msgs)
    else:
        success = True
        ret_msg = cf_msg.obj or ''

    # Delete job from the job IDs file.
    if success or force_delete_from_db:
        try:
            price_class_handler.remove_price_class(jobid)
        except SettingsException as sex:
            success = False
            msgs.append(unicode(sex))

    # Return.
    return success, ret_msg


def update_gold(dg, job_id=None):
    """Updates the gold status of `dg' on Crowdflower.

    Arguments:
        dg -- the Dialogue object for the dialogue
        job_id -- if another job ID than the one computed for `dg' by the price
            class handler should be used, specify it here

    """
    job_id = job_id or price_class_handler.get_job_id(dg)
    success, unit_pair = unit_pair_from_cid(job_id, dg.cid)
    if not success:
        msg = unit_pair
        return False, msg
    unit_id, unit = unit_pair
    dg_is_gold = is_gold(dg)
    if dg_is_gold != (unit['state'] == 'golden'):
        success, errors = update_unit(
            job_id, unit_id,
            (('unit[state]', 'golden' if dg_is_gold else 'new'), ))
        if not success:
            return False, errors
    return True, None


def record_worker(post_dict):
    """
    Records worker information to the corresponding session XML file based
    on POST data from CrowdFlower.

    Arguments:
        post_dict -- a mapping of attributes to values, as given by
            Crowdflower's HTTP request

    """

    # If we got a Django QueryDict in the argument, adjust it from
    # a multi-value dictionary to an ordinary dictionary.
    if hasattr(post_dict, 'dict'):
        post_dict = post_dict.dict()

    cf_data = json.loads(post_dict['payload'])

    # There are two known paths towards the 'judgments' value.
    judgments_paths = [('results', ),
                       (0, 'results')]
    judgments_data = _find_unique_in_cf_json(cf_data, 'judgments',
                                             judgments_paths)
    # Find the CID.
    judgment_data = _cf_json_getitem(judgments_data, 0)
    cid = _find_unique_in_cf_json(judgment_data, 'cid', ('unit_data', ))

    # Update the XML session file.
    with XMLSession(cid=cid) as session:
        session.record_judgment(judgment_data)


# Return codes for `process_worklog'.
CF_LOG_OK = 0
CF_LOG_EXISTED = 1
CF_LOG_NO_FREE_ANN = 2
CF_LOG_NOT_APPLICABLE = 3


def process_worklog(log_fname):
    """
    Reads a work log (a CF webhook serialized in a file) and tries to record
    the worker ID to the corresponding XML session log.

    Returns:
        CF_LOG_OK             ... if the worker ID was recorded
        CF_LOG_EXISTED        ... if the worker ID had been recorded for an
                                  annotation already before
        CF_LOG_NO_FREE_ANN    ... if no new annotation was found
        CF_LOG_NOT_APPLICABLE ... if this work log does not speak about a unit
                                  being completed

    """

    # Read contents of the log file.
    with open(log_fname) as log_file:
        contents = log_file.read()
    # Deserialize the dict.
    try:
        post_dict = eval(contents)
        post_dict['payload'] = json.dumps(post_dict['payload'])
    except:
        return CF_LOG_NOT_APPLICABLE
    # Check that this log describes unit completion.
    if post_dict.get('signal', None) != 'unit_complete':
        return CF_LOG_NOT_APPLICABLE
    # Record worker based on this reconstructed POST dict.
    try:
        recorded = record_worker(post_dict)
    except ValueError:
        return CF_LOG_NO_FREE_ANN
    return CF_LOG_OK if recorded else CF_LOG_EXISTED


def create_dialogue_json(dg):
    """Creates a JSON describing a dialogue for purposes of Crowdflower.

    Arguments:
        dg -- a Django dialogue object

    """
    json_str = ('{{"cid":"{cid}","code":"{code}","code_gold":"{gold}"}}'
                .format(cid=dg.cid,
                        code=dg.code,
                        gold=dg.get_code_gold()))
    return json_str


def create_csv_header():
    """Creates a CSV header row for dialogue upload to Crowdflower.

    Arguments:
        dg -- a Django dialogue object

    """
    return 'cid,code,code_gold'


def create_dialogue_csv(dg):
    """Creates a CSV row describing a dialogue for purposes of Crowdflower.

    Arguments:
        dg -- a Django dialogue object

    """
    return '{cid},{code},{gold}'.format(cid=dg.cid, code=dg.code,
                                        gold=dg.get_code_gold())


def collect_judgments(job_id):
    """Downloads a CSV of all judgments for a job from Crowdflower.

    Downloads a CSV of all judgments for a job from Crowdflower and updates
    workers' gold ratio statistics in session XML files.

    Arguments:
        job_id -- Crowdflower job ID for the job in question

    Returns a tuple (success?, reason).

    """

    success, msg = _get_job_report(job_id)
    if not success:
        return False, msg

    # Divide the first row as a CSV header.
    header = msg.obj[0]
    recs = msg.obj[1:]

    # Prepare for counting gold/missed items.
    gold_stats = dict()  # :: {worker_id -> [n_missed, n_gold]}
    header_dic = {name: idx for idx, name in enumerate(header)}
    worker_idx = header_dic['_worker_id']
    golden_idx = header_dic['_golden']
    missed_idx = header_dic['_missed']

    # Count gold/missed items per worker.
    for rec in recs:
        worker = rec[worker_idx]
        worker_stats = gold_stats.setdefault(worker, [0, 0])
        if rec[golden_idx] == 'true':
            worker_stats[1] += 1
            worker_stats[0] += int(rec[missed_idx] == 'true')

    # Compute workers' scores.
    # Gold score shall be the ratio of golden items the worker got right to all
    # gold items he/she attempted. If the worker attempted no gold items, it is
    # set to -1.0.
    # (Redefining gold_stats :: {worker_id -> [n_missed, n_gold, gold_score]}.)
    for worker_id, worker_stats in gold_stats.iteritems():
        n_missed, n_gold = worker_stats
        if n_missed == n_gold == 0:
            gold_score = -1.
        else:
            gold_score = 1. - float(n_missed) / n_gold
        worker_stats.append(gold_score)

    # Record the gold statistics in XML session files.
    # (Redefining gold_stats :: {worker_id -> gold_score}.)
    gold_stats = {worker_id: stats[2]
                  for worker_id, stats in gold_stats.iteritems()}
    n_files, n_anns = update_worker_stats(gold_stats)

    # Return a success message.
    msg = ('Gold ratios for {n_workers} workers have been updated.  {n_files} '
           'session logs and {n_anns} individual annotations were updated.'
           ).format(n_workers=len(gold_stats), n_files=n_files, n_anns=n_anns)
    return True, msg


def reconstruct_worker_ids(job_id):
    """
    Tries to fill in the worker_id attribute of annotations in XML logs based
    on an overall job report retrieved from Crowdflower.

    Arguments:
        job_id -- ID of the Crowdflower job

    """
    # Get the job report.
    success, msg = _get_job_report(job_id)
    if not success:
        return False, msg

    # Divide the first row as a CSV header, read the column names.
    header = msg.obj[0]
    recs = msg.obj[1:]
    header_dic = {name: idx for idx, name in enumerate(header)}
    cid_idx = header_dic['cid']
    field_idxs = {hook_name: header_dic[HOOKNAMES2CSVNAMES[hook_name]]
                  for hook_name in settings.LOGGED_JOB_DATA
                  if hook_name in HOOKNAMES2CSVNAMES}
    field_idxs['created_at'] = header_dic['_created_at']
    field_idxs['worker_id'] = header_dic['_worker_id']

    # Transform the information into a suitable form.
    dgs_anns = dict()  # :: {cid -> [annotation data]}
    for rec in recs:
        cid = rec[cid_idx]
        dg_ann = {hook_name: rec[field_idxs[hook_name]]
                  for hook_name in field_idxs}
        dgs_anns.setdefault(cid, list()).append(dg_ann)

    record_judgments(dgs_anns)


class JsonDialogueUpload(object):
    """
    A container for dialogues to be uploaded to CrowdFlower. The container
    is single-use only -- once uploaded, it can be disposed of.

    """
    # TODO: Implementing __len__ might be helpful...

    def __init__(self, dg_datas=None, to_higher=False):
        """
        Creates a new JSON object to be uploaded to Crowdflower as job data
        for a dialogue.

        """
        self._uploaded = False
        self.data = dict()
        if dg_datas is not None:
            self.extend(dg_datas, to_higher)

    def add(self, dg, to_higher=False):
        uturns = UserTurn.objects.filter(dialogue=dg)
        if len(uturns) >= settings.MIN_TURNS:
            job_id = price_class_handler.get_job_id(dg, one_higher=to_higher)
            self.data.setdefault(job_id, []).append(dg)

    def extend(self, dg_datas, to_higher=False):
        for dg in dg_datas:
            self.add(dg, to_higher)

    def upload(self, force=False, check_existing=True):
        """
        In case of success returns the number of dialogues that have been
        successfully uploaded (although there is a small chance more dialogues
        were uploaded if only some for one job ID were successful).
        """

        if self._uploaded and not force:
            msg = 'Internal error: attempted to upload the data twice.'
            return False, msg
            # FIXME: Make these strange return tuples into exceptions.

        error_msgs = list()
        num_dgs_successful = 0
        for job_id in self.data:
            # Check what units are currently uploaded for the job.
            success, cur_units = list_units(job_id)
            if success:
                cur_cids = tuple(unit['cid']
                                 for unit in cur_units.itervalues())
            else:
                error_msgs.append('Could not retrieve existing units for '
                                  'job ID {jobid}.'.format(jobid=job_id))
                continue
            # Collect the dialogues that need to be uploaded.
            dgs_to_upload = [dg for dg in self.data[job_id]
                             if dg.cid not in cur_cids]
            # JSON ceased to function, although it is still the recommended
            # method according to Crowdflower's API docs.
            # # Build the JSON string describing the units.
            # json_str = ''.join(create_dialogue_json(dg)
            #                    for dg in dgs_to_upload)
            # Build the CSV string describing the units.
            csv_str = (create_csv_header() + '\n' +
                       '\n'.join(create_dialogue_csv(dg)
                                 for dg in dgs_to_upload))
            # Upload to CF.
            if not csv_str:
                # If there are no dialogues to upload (all have already
                # been uploaded before), take it as a success.
                success = True
            else:
                success, msg = upload_units(job_id, data=csv_str,
                                            content_type='csv')
                if success:
                    num_dgs_successful += len(dgs_to_upload)

                    # Update gold status for the new golden dialogues if there
                    # are any.
                    gold_dgs = filter(is_gold, self.data[job_id])
                    if gold_dgs:
                        # Wait for CF to update its records.
                        time.sleep(settings.CF_WAIT_SECS)

                        for dg in gold_dgs:
                            success, msg = update_gold(dg, job_id)
                            if not success:
                                error_msgs.append(msg)
            if not success:
                error_msgs.append(msg)

        if error_msgs:
            return False, '\n'.join(error_msgs)
        else:
            self._uploaded = True
            return True, num_dgs_successful


class _PriceClassHandler(object):
    """The only object of this class tracks the job price classes defined."""
    _inst = None  # the singleton instance
    if settings.USE_CF:
        _model = CrowdflowerJob
        _id_attr = 'job_id'
    else:
        _model = PriceClass
        _id_attr = 'pk'

    @staticmethod
    def __new__(cls):
        if cls._inst is not None:
            raise ValueError('This singleton has already been created.')
        cls._inst = super(_PriceClassHandler, cls).__new__(cls)
        return cls._inst

    @property
    def price_classes(self):
        """Returns job IDs for price classes configured.

        In case there is just one job, configured using CF_JOB_ID, this returns
        None.  Otherwise, the return value is a mapping {price_usd: job_id}.

        """

        if settings.USE_CF:
            active_jobs = CrowdflowerJob.objects.filter(active=True)
        else:
            active_jobs = PriceClass.objects.all()
        job_prices = set(active_jobs.values_list('cents', flat=True))
        return {self._model.cents2dollars(price):
                getattr(active_jobs.filter(cents=price).latest(),
                        self._id_attr)
                for price in job_prices}

    @property
    def old_price_classes(self):
        """Returns a list of (price_usd, job_id) for jobs not used anymore."""
        prices_ids = self._model.objects.values_list('cents', self._id_attr)
        return [(self._model.cents2dollars(price), id_)
                for price, id_ in prices_ids
                if id_ not in self.price_classes.values()]

    @property
    def all_price_classes(self):
        """Returns a list of (price_usd, job_id) for jobs not used anymore."""
        prices_ids = self._model.objects.values_list('cents', self._id_attr)
        return [(self._model.cents2dollars(price), id_)
                for price, id_ in prices_ids]

    @property
    def price_ranges(self):
        """Returns a list of tuples (price range floor, price range ceiling).

        The first price range's floor is -float('inf'), the last one's ceiling
        is float('inf').  Prices are in dollars.
        """
        inner_steps = sorted(self.price_classes.viewkeys()) or list()
        all_steps = [-float('inf')] + inner_steps + [float('inf')]
        return zip(all_steps[:-1], all_steps[1:])

    def remove_price_class(self, id_):
        filter_kwargs = {self._id_attr: str(id_)}
        self._model.objects.filter(**filter_kwargs).delete()

    if settings.USE_CF:
        def store_job_id(self, job_id, cents):
            """Stores the ID of a Crowdflower job with the given price.

            Arguments:
                job_id -- the ID of the job used by Crowdflower
                cents -- price of each dialogue in this job in cents

            """

            CrowdflowerJob.objects.create(cents=cents, job_id=str(job_id))

    def get_job_id(self, dg, one_higher=False):
        """
        Returns the Crowdflower job ID (a string) for the job where a given
        dialogue would fit.

        Arguments:
            dg -- a Django dialogue object
            one_higher -- if True, the job ID for the next higher price
                class will be returned instead (default: False)

        """

        # Get the price classes defined. This can throw an exception, in which
        # case we let it propagate.
        price_classes = self.price_classes

        # If no price classes are distinguished,
        if not price_classes:
            raise ValueError('No active Crowdflower jobs are defined.')
        # If several price classes are distinguished,
        else:
            if one_higher:
                try:
                    # This selects the nearest higher price step.
                    price_cat = min(filter(
                        lambda step: step > dg.transcription_price,
                        price_classes))
                except ValueError:
                    # Or, in case no price step is higher, the highest price
                    # step absolute.
                    price_cat = max(price_classes)
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

    def get_job_ids(self):
        """Returns IDs of all Crowdflower jobs configured."""

        # Get the price classes defined. This can throw an exception, in which
        # case we let it propagate.
        price_classes = self.price_classes

        if not price_classes:
            raise ValueError('No active Crowdflower jobs are defined.')
        else:
            return price_classes.viewvalues()


# Create the singleton instance of _PriceClassHandler.
price_class_handler = _PriceClassHandler()
