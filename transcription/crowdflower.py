#!/usr/bin/python
# -*- coding: UTF-8 -*-
from __future__ import unicode_literals

import httplib
import json
from lru_cache import lru_cache
from lxml import etree
import os
import os.path
import re
from urllib import urlencode

from dg_util import is_gold
import settings
from settings import SettingsException
from transcription.models import UserTurn
from util import get_log_path

CF_URL_START = "https://api.crowdflower.com/v1/"

default_job_cml_path = os.path.join(settings.PROJECT_DIR, 'transcription',
                                    'crowdflower', 'job-linked.cml')


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

    # Check for errors.
    try:
        cf_outobj = json.loads(cf_out) if cf_out else ''
    except ValueError:
        cf_outobj = None
        error_msgs += ['Unexpected reply from CF: """{cf_out}"""\n'
                       .format(cf_out=cf_out)]
        serious_errors = True
    # Check whether `cf_res.status' did not indicate failure.
    serious_errors |= (str(cf_res.status) != '200')
    if serious_errors:
        if cf_outobj is not None:
            try:
                error_msgs.append(cf_outobj['error']['message'])
            except KeyError:
                error_msgs.append('(no message)')
        msg = ('Complete message from Crowdflower:\n'
               'Response {code} ({reason})\n'
               '<pre>\n'
               '{msg}\n'
               '</pre>').format(code=cf_res.status,
                                reason=cf_res.reason,
                                msg=cf_out or '')
        error_msgs.append(msg)
        # In case of lack of success, return also the error messages.
        return False, cf_outobj, error_msgs

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
    job_price = (units_per_assignment * cents_per_unit) / units_per_assignment
    if title is None:
        title = 'Dialogue transcription – {price}c'.format(price=job_price)
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
    job_params['title'] = title
    job_params['judgments_per_unit'] = judgments_per_unit
    job_params['units_per_assignment'] = units_per_assignment
    job_params['pages_per_assignment'] = pages_per_assignment
    job_params['language'] = 'en'
    # FIXME The following needs to be less than units_per_assignment. Check it,
    # potentially complaining about wrong arguments.
    job_params['gold_per_assignment'] = gold_per_assignment
    job_params['instructions'] = instructions
    # webhook
    job_params['webhook_uri'] = '{domain}{site}log-work'.format(
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
    success, cf_out, error_msgs = _contact_cf(cf_url, verb='POST',
                                              json_str=json.dumps(params))

    # If the job was successfully created,
    if success:
        job_id = cf_out['id']

        # Modify some more parameters. This has not been done above as it seems
        # to not work with Content-Type: application/json, whereas some of the
        # above, on the contrary, seemed to require exactly that format.
        #
        # Set up the workers' countries included.
        params = [('job[included_countries][]', country)
                  for country in ("AU", "CA", "GB", "IE", "IM", "NZ", "US")]
        # Set up the gold field.
        params.append(('check', 'code'))
        # Make the request and check the response.
        cf_url = 'jobs/{jobid}'.format(jobid=job_id)
        update_success, update_out, update_msgs = _contact_cf(
            cf_url, verb='PUT', params=params)
        if not update_success:
            lead = ('Error when updating parameters of the new job (job ID: '
                    '{jobid}: ').format(jobid=job_id)
            return False, (lead + ' ||| '.join(update_msgs))

        # If everything has gone alright and the new job's ID should be stored,
        if store_job_id:
            price_class_handler.store_job_id(job_id, job_price)

        return True, update_out

    # If the creation of the job itself was unsuccessful,
    else:
        lead = 'Error when creating new job: '
        return False, (lead + ' ||| '.join(error_msgs))


############################
# ORIGINALLY IN dg_util.py #
############################
def update_gold(dg):
    """Updates the gold status of `dg' on Crowdflower."""
    job_id = price_class_handler.get_job_id(dg)
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
        anns_above = sess_xml.find(
            settings.XML_COMMON['ANNOTATIONS_ABOVE'])
        anns_after = anns_above.find(
            settings.XML_COMMON['ANNOTATIONS_AFTER'])
        anns_after_idx = (anns_above.index(anns_after)
                          if anns_after is not None
                          else len(anns_above))
        found_anns = False
        if anns_after_idx > 0:
            anns_el = anns_above[anns_after_idx - 1]
            if anns_el.tag == settings.XML_COMMON['ANNOTATIONS_ELEM']:
                found_anns = True
        if not found_anns:
            raise ValueError()
        anns_from_dummy = anns_el.findall(
            "./{ann_el}[@user='testres']".format(
                ann_el=settings.XML_COMMON['ANNOTATION_ELEM']))
        anns_unlabeled = filter(lambda el: 'worker_id' not in el.attrib,
                                anns_from_dummy)
        if not anns_unlabeled:
            raise ValueError()
        # Heuristic: take the last one of the potential dialogue annotation
        # XML elements.
        dg_ann_el = anns_unlabeled[-1]
        # Set all the desired attributes.
        if 'worker_id' not in settings.LOGGED_JOB_DATA:
            dg_ann_el.set('worker_id', str(judgment_data["worker_id"]))
        for json_key, att_name in settings.LOGGED_JOB_DATA:
            att_val = judgment_data.get(json_key, None)
            if att_val is not None:
                dg_ann_el.set(att_name, unicode(att_val))
    # Write the XML session file.
    with open(sess_fname, 'w') as sess_file:
        sess_file.write(etree.tostring(sess_xml,
                                       pretty_print=True,
                                       xml_declaration=True,
                                       encoding='UTF-8'))


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
            self.data.setdefault(price_class_handler.get_job_id(dg),
                                 []).append(dg)

    def extend(self, dg_datas):
        for dg in dg_datas:
            self.add(dg)

    def upload(self, force=False, check_existing=True):
        # TODO Change the interface such that the return value implies also
        # how many dialogues have been successfully uploaded.
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


class _PriceClassHandler(object):
    """The only object of this class tracks the job price classes defined."""
    _inst = None  # the singleton instance

    @staticmethod
    def __new__(cls, settings):
        if cls._inst is not None:
            raise ValueError('This singleton has already been created.')
        cls._inst = super(_PriceClassHandler, cls).__new__(cls)
        return cls._inst

    def __init__(self, settings):
        # Store the settings.
        self._settings = settings
        # Check whether dialogues should be split into several CF jobs based on
        # their price.
        self._last_read = 0.  # timestamp when we last read the jobs file
        self.load_price_classes()

    @property
    def price_classes(self):
        # Read again the jobs file if it was updated without us reading it.
        if (hasattr(self._settings, 'CF_JOBS_FNAME') and
            self._last_read < os.stat(
                self._settings.CF_JOBS_FNAME).st_mtime):
            self.load_price_classes()

        if self._price_classes_valid:
            return self._price_classes
        else:
            msg = ('Price classes should be read from a file '
                   '(settings.CF_JOBS_FNAME="{fname}") but it contains no '
                   'valid records.').format(fname=self._settings.CF_JOBS_FNAME)
            raise Exception(msg)

    @property
    def price_ranges(self):
        """Returns a list of tuples (price range floor, price range ceiling).

        The first price range's floor is -float('inf'), the last one's ceiling
        is float('inf').
        """
        inner_steps = sorted(self.price_classes.viewkeys()) or list()
        all_steps = [-float('inf')] + inner_steps + [float('inf')]
        return zip(all_steps[:-1], all_steps[1:])

    def load_price_classes(self):
        self._price_classes_valid = True
        # If the price classes are to be stored in a file,
        if hasattr(self._settings, 'CF_JOBS_FNAME'):
            jobs_fname = self._settings.CF_JOBS_FNAME
            if os.path.exists(jobs_fname):
                job_ids = dict()
                with open(jobs_fname) as jobs_file:
                    for line in jobs_file:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            price_str, job_id_str = line.strip().split('\t')
                            job_ids[int(price_str)] = job_id_str
                        except:
                            raise Exception(
                                'Wrong format of the job IDs file {fname}.'
                                .format(fname=jobs_fname))
                self._last_read = os.stat(jobs_fname).st_mtime
                self._price_classes = job_ids
            else:
                # If the job IDs file has not been created yet, trust that it
                # will be created yet in time.  Do not complain.
                self._price_classes = None
                self._price_classes_valid = False
        elif hasattr(self._settings, 'CF_JOB_IDS'):
            self._price_classes = self._settings.CF_JOB_IDS
        else:
            if not hasattr(self._settings, 'CF_JOB_ID'):
                msg = ('At least one of CF_JOB_ID, CF_JOB_IDS or '
                       'CF_JOBS_FNAME has to be set.')
                raise SettingsException(msg)
            self._price_classes = None

    def store_job_id(self, job_id, price, outfname=None):
        """Stores the ID of a Crowdflower job with the given price.

        Arguments:
            job_id -- the ID of the job used by Crowdflower
            price -- price of this job in cents
            outfname -- path towards the file where the job ID should be stored
                (default: settings.CF_JOBS_FNAME)

        """

        # Figure out the `outfname'.
        jobs_fname = None
        if outfname is None:
            try:
                outfname = jobs_fname = self._settings.CF_JOBS_FNAME
                default_out = True
            except AttributeError:
                msg = ('Cannot store job ID to a file: "CF_JOBS_FNAME" has '
                       'not been configured.')
                raise SettingsException(msg)
        else:
            default_out = (os.path.abspath(outfname)
                           == os.path.abspath(jobs_fname))

        # Create the file's parent dirs if they did not exist.
        out_dirname = os.path.dirname(os.path.abspath(outfname))
        if not os.path.exists(out_dirname):
            try:
                os.makedirs(outfname)
            except os.error:
                msg = ('Cannot store job ID to the file "{fname}": the '
                       'directories in the path could not be created.'
                       ).format(fname=outfname)
                raise Exception(msg)

        # If writing to the default jobs file,
        if default_out:
            # Remember when this was last modified.
            last_modified = os.stat(outfname).st_mtime

        # Write the job ID.
        with open(outfname, 'a+') as outfile:
            outfile.write('{price}\t{id_}\n'.format(price=price, id_=job_id))

        # Update the dict of price classes.
        if default_out:
            # If we saw the file after it was last modified (before the current
            # method was called),
            if self._last_read >= last_modified:
                # Just enter the new price class to the dictionary.
                self._price_classes[price] = job_id
                # Remember we know the jobs file contents as of now.
                self._last_read = os.stat(jobs_fname).st_mtime
            # If the file was modified in the meantime,
            else:
                # Read the whole file.
                self.load_price_classes()

    def get_job_id(self, dg):
        """
        Returns the Crowdflower job ID (a string) for the job where a given
        dialogue would fit.

        Arguments:
            dg -- a Django dialogue object

        """

        # Get the price classes defined. This can throw an exception, in which
        # case we let it propagate.
        price_classes = self.price_classes

        # If no price classes are distinguished,
        if price_classes is None:
            # This means that all dialogues go to a single job.
            return self._settings.CF_JOB_ID
        # If several price classes are distinguished,
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

        if price_classes is None:
            return [settings.CF_JOB_ID]
        else:
            return price_classes.viewvalues()


# Create the singleton instance of _PriceClassHandler.
price_class_handler = _PriceClassHandler(settings)
