#!/usr/bin/python
# -*- coding: UTF-8 -*-

from collections import defaultdict, namedtuple
from datetime import datetime, timedelta
from lxml import etree
import os
import os.path

import settings


UserTurn_nt = namedtuple('UserTurn_nt', ['turn_number', 'wav_fname'])
SystemTurn_nt = namedtuple('SystemTurn_nt', ['turn_number', 'text'])
UserTurnAbs_nt = namedtuple('UserTurnAbs_nt', ['turn_abs_number',
                                               'turn_number', 'wav_fname'])
SystemTurnAbs_nt = namedtuple('SystemTurnAbs_nt', ['turn_abs_number',
                                                   'turn_number', 'text'])

WorkerIDStats = namedtuple('WorkerIDStats',
                           ['cid', 'n_kept_full', 'n_conflicting', 'n_updated',
                            'n_kept_empty'])

CF_DT_FORMAT = "%m/%d/%Y %H:%M:%S"
DT_MATCH_TOL = timedelta(minutes=9999)
CF_TD_SHIFT = timedelta(hours=-2)


def is_dialogue_dirname(fname):
    """Checks whether `fname' is a name of a known dialogue dir."""
    return os.path.isdir(os.path.join(settings.CONVERSATION_DIR, fname))


def update_worker_stats(gold_stats):
    """Updates the gold hit statistic in all available session files.

    Arguments:
        gold_stats -- a mapping {worker_id -> gold_ratio}

    Returns a tuple (number of files affected, number of XML elements affected)
    where an XML element corresponds to one dialogue annotation (by one
    worker).

    """

    dg_dirs = filter(is_dialogue_dirname,
                     os.listdir(settings.CONVERSATION_DIR))
    n_files = 0
    n_els = 0
    for dg_dir in dg_dirs:
        with XMLSession(cid=dg_dir) as session:
            n_els += session.update_worker_stats(gold_stats)
            n_files += (n_els > 0)
    return n_files, n_els


def update_worker_cers(ann2w_cer):
    """Updates the gold hit statistic in all available session files.

    Arguments:
        ann2w_cer -- a mapping {annotation ID -> [transcription char er]}

    Returns a tuple (number of files affected,
                     number of workers affected,
                     number of XML elements affected)
    where an XML element corresponds to one dialogue annotation (by one
    worker).

    """

    dg_dirs = filter(is_dialogue_dirname,
                     os.listdir(settings.CONVERSATION_DIR))

    # Build the mapping worker_id -> char_er.
    wid2cers = dict()  # :: {worker_id -> [character error rate]}
    dir2wids = dict()  # :: {dir -> [worker ID]}
    for dg_dir in dg_dirs:
        dir_wids = list()
        with XMLSession(cid=dg_dir) as session:
            for ann_el in session.iter_annotations():
                ann_id = int(ann_el.get('id'))
                worker_id = ann_el.get('worker_id', None)
                if worker_id is not None:
                    dir_wids.append(worker_id)
                    if ann_id in ann2w_cer:
                        ann_cers = ann2w_cer[ann_id]
                        wid2cers.setdefault(worker_id, list()).extend(ann_cers)
        dir2wids[dg_dir] = dir_wids

    # Compute the average character error rate over all error rates for each
    # worker.
    wid2cer_str = {wid: '{0:.3f}'.format(sum(cers) / len(cers))
                   for wid, cers in wid2cers.iteritems()}

    # Determine which directories we need to visit again.
    affected_dirs = [dg_dir for dg_dir in dir2wids
                     if any((wid in wid2cer_str) for wid in dir2wids[dg_dir])]

    # Update the average error rates in the logs.
    n_files = len(affected_dirs)
    n_els = 0
    n_workers = len(wid2cer_str)
    for dg_dir in affected_dirs:
        with XMLSession(cid=dg_dir) as session:
            for ann_el in session.iter_annotations():
                worker_id = ann_el.get('worker_id', None)
                if worker_id in wid2cer_str:
                    ann_el.set('avg_char_er', wid2cer_str[worker_id])
                    n_els += 1

    # Return.
    return n_files, n_workers, n_els


def fill_in_worker_ids(force=False):
    """
    Uses cookie IDs stored with annotations to fill in worker IDs to
    annotations that don't have them but have the cookie ID.

    Keyword arguments:
        force -- if True, existing worker IDs are overwritten with those we
            think should be there based (default: False)

    Returns a tuple (ambig_cookies, resolved_cookies, cid_stats), where:
        ambig_cookies is a set of cookie values that were seen with different
            worker IDs and could not be disambiguated;
        resolved_cookies is a set of cookie values that were seen with
            different worker IDs and were disambiguated (non-empty only if
            force=True); and
        cid_stats is a list of WorkerIDStats, describing how many annotation
            elements had seen their worker IDs updated, not updated, or
            conflicting.

    """

    dg_dirs = filter(is_dialogue_dirname,
                     os.listdir(settings.CONVERSATION_DIR))
    cookie2ids = defaultdict(lambda: defaultdict(int))
    cids_to_fill = list()
    ambig_cookies = set()
    resolved_cookies = set()
    cid_stats = list()  # :: (cid, n_kept_full, n_conflicting, n_updated,
                        #     n_kept_empty)

    # First pass: collect the mapping cookie -> worker_id.
    for dg_dir in dg_dirs:
        needs_be_filled = False
        with XMLSession(cid=dg_dir) as session:
            for ann in session.iter_annotations():
                cookie = ann.get(settings.TRANSCRIBER_ID_ATTR, None)
                if cookie is not None:
                    wid = ann.get('worker_id', None)
                    needs_be_filled |= (wid is None)
                    cookie2ids[cookie][wid] += 1
        if needs_be_filled:
            cids_to_fill.append(dg_dir)

    # Determine a single worker ID for each cookie.
    cookie2id = dict()
    for cookie, ids in cookie2ids.iteritems():
        needs_be_filled = None in ids
        n_known_ids = len(ids) - int(needs_be_filled)
        if needs_be_filled and n_known_ids == 1:
            # Take another worker ID than None.
            cookie2id[cookie] = filter(None, ids)[0]
        # If this cookie was seen with several worker IDs,
        elif n_known_ids > 1:
            if force:
                # Try to determine which worker ID is the correct one.
                # The criterion we use is: when there is a single worker ID
                # that appeared with this cookie at least thrice, and all other
                # worker IDs appeared with this cookie at most once, we take
                # the thrice-and-more occurring worker ID for the correct one.
                likely_ids = [wid
                              for wid, n_occs in cookie2ids[cookie].iteritems()
                              if wid is not None and n_occs >= 3]
                possible_ids = [wid for wid, n_occs
                                in cookie2ids[cookie].iteritems()
                                if wid is not None and n_occs >= 2]
                if len(possible_ids) == 1 == len(likely_ids):
                    cookie2id[cookie] = likely_ids[0]
                    resolved_cookies.add(cookie)
                    continue
            ambig_cookies.add(cookie)

    # Second pass: fill in worker_ids which we can deduce.
    for cid in cids_to_fill:
        n_kept_full = n_conflicting = n_updated = n_kept_empty = 0
        with XMLSession(cid=cid) as session:
            for ann in session.iter_annotations():
                cookie = ann.get(settings.TRANSCRIBER_ID_ATTR, None)
                wid = ann.get('worker_id', None)
                # If a worker ID has been assigned to this annotation,
                if wid is not None:
                    # Check whether it is not in contrary to what we would put
                    # there based on the cookie.
                    conflicts = (cookie2id.get(cookie, wid) != wid)
                    if conflicts:
                        n_conflicting += 1
                        if force:
                            ann.set('worker_id', cookie2id[cookie])
                    else:
                        n_kept_full += 1
                # If no worker ID has been assigned to this annotation,
                else:
                    # If we know the worker ID that should be here,
                    if cookie in cookie2id:
                        ann.set('worker_id', cookie2id[cookie])
                        n_updated += 1
                    else:
                        n_kept_empty += 1
        cid_stats.append(WorkerIDStats(cid, n_kept_full, n_conflicting,
                                       n_updated, n_kept_empty))

    return ambig_cookies, resolved_cookies, cid_stats


def record_judgments(dgs_anns):
    dg_dirs = set(filter(is_dialogue_dirname,
                         os.listdir(settings.CONVERSATION_DIR)))
    for cid, dg_anns in dgs_anns.iteritems():
        if cid in dg_dirs:
            with XMLSession(cid=cid) as session:
                for judgment in dg_anns:
                    try:
                        session.record_judgment(judgment, match_date=True)
                    except Exception as ex:
                        print '{fname}: {ex}'.format(fname=session.sess_path,
                                                     ex=ex)


class FileNotFoundError(Exception):
    pass


class XMLSession(object):
    """
    A context manager for handling XML files capturing dialogue sessions.
    These objects handle different versions of the XML scheme of sessions XML
    files.

    """
    xml_parser = etree.XMLParser(remove_blank_text=True)

    @classmethod
    def find_session_fname(cls, dirname):
        """Finds the right session file and returns its path."""
        try:
            sess_fnames = settings.SESSION_FNAMES
        except AttributeError:
            sess_fnames = (settings.SESSION_FNAME, )
        for sess_fname in sess_fnames:
            sess_path = os.path.join(dirname, sess_fname)
            if os.path.isfile(sess_path):
                break
        else:
            raise FileNotFoundError('No session XML file was found in {dir}.'
                                    .format(dir=dirname))
        return sess_path

    def __init__(self, cid=None, fname=None, mode='r+'):
        if cid is None and fname is None:
            raise ValueError('Either `cid\' or `fname\' have to be specified.')

        if cid is not None:
            self.dirname = os.path.join(settings.CONVERSATION_DIR, cid)
            self.sess_path = self.find_session_fname(self.dirname)
        else:
            self.sess_path = os.path.abspath(fname)
            self.dirname = os.path.dirname(self.sess_path)
        self.mode = mode
        self.sess_xml = None

    def __enter__(self):
        with open(self.sess_path, self.mode) as sess_file:
            self.sess_xml = etree.parse(sess_file, self.xml_parser)

        # Check the version of the session XML scheme and set all the XML
        # orientation variables.
        # TODO Implement a more comprehensive scheme for determining the XML
        # scheme.
        root_tag = self.sess_xml.getroot().tag
        try:
            setup = settings.XML_SCHEMES[root_tag]
        except:
            raise ValueError(('The session XML file {fname} does not conform '
                              'to any XML schemes configured.').format(
                             fname=self.sess_path))

        # Set all the specific XML configuration options here.
        for key, val in setup.iteritems():
            self.__setattr__(key, val)
        # Set all the common XML configuration options here.
        if hasattr(settings, 'XML_COMMON'):
            for key, val in settings.XML_COMMON.iteritems():
                self.__setattr__(key, val)

        self.SLASH_TRANSCRIPTIONS_ELEM = (("/" + self.TRANSCRIPTIONS_ELEM)
                                          if self.TRANSCRIPTIONS_ELEM else "")
        if hasattr(self, 'DATE_FORMAT') and self.DATE_FORMAT is not None:
            def format_datetime(dt):
                return dt.strftime(self.DATE_FORMAT)
            def parse_datetime(dt_str):
                return datetime.strptime(dt_str, self.DATE_FORMAT)
        else:
            iso_format = '%Y-%m-%d %H:%M:%S.%f'
            iso_format0 = '%Y-%m-%d %H:%M:%S'  # in case microsecond == 0
            def format_datetime(dt):
                return unicode(dt)
            def parse_datetime(dt_str):
                try:
                    return datetime.strptime(dt_str, iso_format)
                except ValueError:
                    return datetime.strptime(dt_str, iso_format0)
        self.format_datetime = format_datetime
        self.parse_datetime = parse_datetime

        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        # Check whether an exception occurred.
        if exc_type is not None:
            # Simple behaviour: just reraise the exception.
            return False

        if any(ltr in self.mode for ltr in 'aw+'):
            with open(self.sess_path, 'w') as sess_file:
                sess_file.write(etree.tostring(self.sess_xml,
                                               pretty_print=True,
                                               xml_declaration=True,
                                               encoding='UTF-8'))

        return True

    def find_transcription(self, trs):
        """
        Finds the transcription element in the XML for a given transcription.
        If the element is not there, returns None.

        Keyword arguments:
            - trs -- the transcription.models.Transcription object whose
                     XML representation is to be found

        """
        dg_ann = trs.dialogue_annotation
        if dg_ann.user is not None:
            username = dg_ann.user.username
        else:
            username = ''
        trs_path = ("{uturn}[@{turn_attr}='{turn}']{trss}/{trs}"
                    "[@{auth_attr}='{author}'][@{ann_attr}='{ann}']").format(
                        uturn=self.USERTURN_PATH,
                        turn_attr=self.TURNNUMBER_ATTR,
                        turn=str(trs.turn.turn_number),
                        trss=self.SLASH_TRANSCRIPTIONS_ELEM,
                        trs=self.TRANSCRIPTION_ELEM,
                        auth_attr=self.AUTHOR_ATTR,
                        author=username,
                        ann_attr="annotation",  # hard-wired in views.py, too
                        ann=str(dg_ann.pk))
        return self.sess_xml.find(trs_path)

    def add_transcription(self, trs):

        # Find the appropriate place for the transcription in the XML tree.
        dg_ann = trs.dialogue_annotation
        user_turns = self.sess_xml.findall(self.USERTURN_PATH)
        turn_xml = filter(
            lambda turn_xml: \
                int(turn_xml.get(self.TURNNUMBER_ATTR, -1)) \
                    == trs.turn.turn_number,
            user_turns)[0]
        if self.TRANSCRIPTIONS_ELEM is not None:
            trss_xml = turn_xml.find(self.TRANSCRIPTIONS_ELEM)
            if trss_xml is None:
                trss_left_sib = turn_xml.find(self.TRANSCRIPTIONS_BEFORE)
                if trss_left_sib is None:
                    insert_idx = len(turn_xml)
                else:
                    insert_idx = turn_xml.index(trss_left_sib) + 1
                trss_xml = etree.Element(self.TRANSCRIPTIONS_ELEM)
                turn_xml.insert(insert_idx, trss_xml)
        else:
            trss_xml = turn_xml

        # Create the XML element for the transcription.
        trs_xml = etree.Element(
            self.TRANSCRIPTION_ELEM,
            annotation=str(dg_ann.pk),
            is_gold="0",
            breaks_gold="1" if trs.breaks_gold else "0",
            some_breaks_gold="1" if trs.some_breaks_gold else "0",
            program_version=dg_ann.program_version)
        if dg_ann.user is not None:
            username = dg_ann.user.username
        else:
            username = ''
        trs_xml.set(self.AUTHOR_ATTR, username)
        trs_xml.set(self.DATE_ATTR,
                    self.format_datetime(dg_ann.date_saved))
        trs_xml.text = trs.text

        # Insert the new XML element at its place, and return it.
        if self.TRANSCRIPTION_BEFORE:
            trs_left_sib = trss_xml.find(self.TRANSCRIPTION_BEFORE)
        else:
            trs_left_sib = None
        if trs_left_sib is None:
            insert_idx = len(trss_xml)
        else:
            insert_idx = trss_xml.index(trs_left_sib) + 1
        trss_xml.insert(insert_idx, trs_xml)
        return trs_xml

    def find_or_create_transcription(self, trs):
        trs_xml = self.find_transcription(trs)
        if trs_xml is None:
            return self.add_transcription(trs)
        else:
            return trs_xml

    def find_annotations(self):
        anns_above = self.sess_xml.find(self.ANNOTATIONS_ABOVE)
        anns_after = anns_above.find(self.ANNOTATIONS_AFTER)
        anns_after_idx = (anns_above.index(anns_after)
                          if anns_after is not None
                          else len(anns_above))
        if anns_after_idx > 0:
            anns_el = anns_above[anns_after_idx - 1]
            if anns_el.tag == self.ANNOTATIONS_ELEM:
                return anns_above, anns_after_idx, anns_el
        return anns_above, anns_after_idx, None

    def find_or_create_annotations(self):
        anns_above, anns_after_idx, anns_el = self.find_annotations()
        if anns_el is None:
            anns_el = etree.Element(self.ANNOTATIONS_ELEM)
            anns_above.insert(anns_after_idx, anns_el)
        return anns_el

    def iter_annotations(self, **kwargs):
        anns_above, anns_after_idx, anns_el = self.find_annotations()
        if anns_el is not None:
            def matches_kwargs(el):
                for name, val in kwargs.iteritems():
                    if el.get(name, (val, None)) != val:
                        return False
                return True

            for ann_el in anns_el:
                if matches_kwargs(ann_el):
                    yield ann_el

    def iter_transcriptions(self, annotation):
        """
        Iterates `transcription' elements that belong to the given dialogue
        annotation.

        Arguments:
            annotation -- the annotation XML element

        Yields: tuples (turn_number, transcription) where turn_number is an
        integer and transcription an XML element.

        """

        # Prepare for iteration.
        ann_id = annotation.get('id')
        trs_subpath = ".{trss}/{trs}[@{ann_attr}='{ann}']".format(
            trss=self.SLASH_TRANSCRIPTIONS_ELEM,
            trs=self.TRANSCRIPTION_ELEM,
            ann_attr="annotation",  # hard-wired in views.py, too
            ann=ann_id)

        # Iterate user turns and yield their respective transcriptions.
        for uturn_el in self.sess_xml.iterfind(self.USERTURN_PATH):
            try:
                turn_number = int(uturn_el.get(self.TURNNUMBER_ATTR, -1))
            except TypeError:
                # Some turns in the XML logs don't have the turn number
                # attribute, which leads to a TypeError. Skip such turns.
                continue
            # Find transcriptions in this turn (assumably, there will be
            # one, but there may be none).
            for trs in uturn_el.iterfind(trs_subpath):
                yield turn_number, trs

    def add_annotation(self, dg_ann, **more_attrs):
        """Adds an annotation element to the XML log.

        Arguments:
            dg_ann -- the Django Annotation object to be serialized in the XML
            more_attrs -- dictionary of any additional attributes to be stored
                with the annotation element

        """
        # First, get the embedding element for all annotations.
        anns_el = self.find_or_create_annotations()
        # Second, create an appropriate element for the new annotation.
        if dg_ann.user is not None:
            username = dg_ann.user.username
        else:
            username = ''
        ann_el = etree.SubElement(
            anns_el,
            self.ANNOTATION_ELEM,
            id=str(dg_ann.pk),
            program_version=dg_ann.program_version,
            date_saved=self.format_datetime(dg_ann.date_saved),
            user=username)
        for name, val in more_attrs.iteritems():
            ann_el.set(name, val)
        if 'offensive' in settings.EXTRA_QUESTIONS:
            ann_el.set('offensive', str(dg_ann.offensive))
        if 'accent' in settings.EXTRA_QUESTIONS:
            ann_el.set('accent', dg_ann.accent or "native")
        if 'quality' in settings.EXTRA_QUESTIONS:
            ann_el.set('quality',
                       ('clear' if dg_ann.quality == 1 else 'noisy'))
        if dg_ann.notes:
            ann_el.text = dg_ann.notes

    @classmethod
    def _turn_is_userturn(cls, turn_el):
        return (turn_el.tag == 'userturn' or
                turn_el.get('speaker', None) == 'user')

    def iter_turns(self):

        # XXX This method was build in an ugly way, by putting together the
        # bodies of iter_uturns and iter_systurns.
        turns = self.sess_xml.xpath(
            '|'.join((self.USERTURN_PATH, self.SYSTURN_PATH)))
        uturnnums_seen = set()
        for turn_abs_num, turn_xml in enumerate(turns, start=1):
            if self._turn_is_userturn(turn_xml):
                rec = turn_xml.find(self.REC_SUBPATH)
                if rec is not None:
                    rec = rec.attrib[self.REC_FNAME_ATTR]
                try:
                    turn_number = int(turn_xml.attrib[self.TURNNUMBER_ATTR])
                except KeyError as er:  # There may be a turn with no turn
                                        # number.
                    pass
                else:
                    if turn_number not in uturnnums_seen:
                        yield UserTurnAbs_nt(turn_abs_num, turn_number, rec)
                        uturnnums_seen.add(turn_number)
            else:
                turn_number = int(turn_xml.attrib[self.TURNNUMBER_ATTR])
                try:
                    text = turn_xml.findtext(self.SYSTEXT_SUBPATH).strip()
                except AttributeError:
                    # Some turns might not have the text subelement.
                    yield SystemTurnAbs_nt(turn_abs_num, turn_number, "")
                    continue
                # Throw away some distracting pieces of system prompts.
                text = self._clean_systurn_text(text)
                if text is None:
                    continue
                yield SystemTurnAbs_nt(turn_abs_num, turn_number, text)

    def iter_uturns(self):
        turnnums_seen = set()
        for uturn_xml in self.sess_xml.iterfind(self.USERTURN_PATH):
            rec = uturn_xml.find(self.REC_SUBPATH)
            if rec is not None:
                rec = rec.attrib[self.REC_FNAME_ATTR]
            try:
                turn_number = int(uturn_xml.attrib[self.TURNNUMBER_ATTR])
            except KeyError as er:  # There may be a turn with no turn number.
                pass
            else:
                if turn_number not in turnnums_seen:
                    yield UserTurn_nt(turn_number, rec)
                    turnnums_seen.add(turn_number)

    @classmethod
    def _clean_systurn_text(cls, text):
        if (text.startswith("Thank you for using")
                or text.startswith("Thank you goodbye")):
            return None
        return text.replace(
            "Thank you for calling the Cambridge Information system. "
            "Your call will be recorded for research purposes.",
            "").strip()

    def iter_systurns(self):
        for systurn_xml in self.sess_xml.iterfind(self.SYSTURN_PATH):
            turn_number = int(systurn_xml.attrib[self.TURNNUMBER_ATTR])
            try:
                text = systurn_xml.findtext(self.SYSTEXT_SUBPATH).strip()
            except AttributeError:
                # Some turns might not have the text subelement.
                yield SystemTurn_nt(turn_number, "")
                continue
            # Throw away some distracting pieces of system prompts.
            text = self._clean_systurn_text(text)
            if text is None:
                continue
            yield SystemTurn_nt(turn_number, text)

    def record_judgment(self, judgment, match_date=False):
        """Records data about a judgment to this XML session log.

        It can be configured what all kinds of information is recorded, using
        the LOGGED_JOB_DATA configuration variable.  However, Crowdflower
        worker ID is recorded in any case.

        Arguments:
            judgment -- an object describing one judgment, as created by
                Crowdflower
            match_date -- if True, the judgment will be recorded only if an
                unassigned annotation element is present that matches the date
                noted in the judgment (default: False)

        Returns True if the corresponding annotation element was found and
        updated, False otherwise (namely if an existing annotation element from
        this worker ID was found).

        """

        # Get this worker's ID.
        worker_id = str(judgment["worker_id"])
        # Get the desired date to match.
        if match_date:
            date = (datetime.strptime(judgment['created_at'], CF_DT_FORMAT)
                    - CF_TD_SHIFT)

        # Find the relevant dialogue annotation element.
        # XXX Heuristic: take the first one of the potential dialogue
        # annotation XML elements.
        unassigned_el = None
        for ann_el in self.iter_annotations(user=''):
            cur_worker_id = ann_el.get('worker_id', None)
            if match_date:
                if cur_worker_id is None or cur_worker_id == worker_id:
                    date_saved = self.parse_datetime(ann_el.get('date_saved'))
                    if abs(date - date_saved) < DT_MATCH_TOL:
                        if unassigned_el is None:
                            unassigned_el = ann_el
                        else:
                            # Cancel the operation if it seems we would record
                            # the worker for the second time.
                            return False
                    # DEBUG
                    else:
                        dt_format = '%m. %d. %H:%M:%S'
                        print '{created: >15} {saved: >15} {td: >4}'.format(
                            created=date.strftime(dt_format),
                            saved=date_saved.strftime(dt_format),
                            td=abs(date - date_saved).seconds)
            else:
                if cur_worker_id is None and unassigned_el is None:
                    unassigned_el = ann_el
                elif cur_worker_id == worker_id:
                    # Cancel the operation if it seems we would record the
                    # worker for the second time.
                    return False

        # Check that there is an element for the judgment we are about to
        # assign.
        if unassigned_el is None:
            raise ValueError('Trying to record a judgment for which there is '
                             'no unassigned XML element in place.')

        # Set all the desired attributes.
        if 'worker_id' not in settings.LOGGED_JOB_DATA:
            ann_el.set('worker_id', worker_id)
        for json_key, att_name in settings.LOGGED_JOB_DATA:
            att_val = judgment.get(json_key, None)
            if att_val is not None:
                ann_el.set(att_name, unicode(att_val))
        return True

    def update_worker_stats(self, gold_stats):
        """Updates the gold hit statistic.

        Arguments:
            gold_stats -- a mapping {worker_id -> gold_ratio}

        Returns the number of XML elements affected) where an XML element
        corresponds to one dialogue annotation (by one worker).

        """

        n_updated = 0
        for ann_el in self.iter_annotations(user=''):
            worker_id = ann_el.get('worker_id', None)
            if worker_id in gold_stats:
                ratio_str = '{0:.2f}'.format(gold_stats[worker_id])
                ann_el.set('gold_ratio', ratio_str)
                n_updated += 1
        return n_updated
