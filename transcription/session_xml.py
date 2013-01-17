#!/usr/bin/python
# -*- coding: UTF-8 -*-

from collections import namedtuple
from lxml import etree
import os.path

import settings


UserTurn_nt = namedtuple('UserTurn_nt', ['turn_number', 'wav_fname'])
SystemTurn_nt = namedtuple('SystemTurn_nt', ['turn_number', 'text'])


class FileNotFoundError(Exception):
    pass


class XMLSession(object):
    """A context manager for handling XML files capturing dialogue sessions.
    These objects account for different versions of the XML scheme of sessions
    XML files.

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

    def __init__(self, cid):
        self.dirname = os.path.join(settings.CONVERSATION_DIR, cid)
        self.sess_path = self.find_session_fname(self.dirname)
        self.sess_xml = None

    def __enter__(self):
        with open(self.sess_path, 'r+') as sess_file:
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
        else:
            def format_datetime(dt):
                return unicode(dt)
        self.format_datetime = format_datetime

        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        # Check whether an exception occurred.
        if exc_type is not None:
            # Simple behaviour: just reraise the exception.
            return False

        with open(self.sess_path, 'w') as sess_file:
            sess_file.write(etree.tostring(self.sess_xml,
                                           pretty_print=True,
                                           xml_declaration=True,
                                           encoding='UTF-8'))

        return True

    def find_transcription(self, trs):
        """Finds the transcription element in the XML for a given
        transcription.  If the element is not there, returns None.

        Keyword arguments:
            - trs -- the transcription.models.Transcription object whose
                     XML representation is to be found

        """
        dg_ann = trs.dialogue_annotation
        trs_path = ("{uturn}[@{turn_attr}='{turn}']{trss}/{trs}"
                    "[@{auth_attr}='{author}'][@{ann_attr}='{ann}']").format(
                        uturn=self.USERTURN_PATH,
                        turn_attr=self.TURNNUMBER_ATTR,
                        turn=str(trs.turn.turn_number),
                        trss=self.SLASH_TRANSCRIPTIONS_ELEM,
                        trs=self.TRANSCRIPTION_ELEM,
                        auth_attr=self.AUTHOR_ATTR,
                        author=dg_ann.user.username,
                        ann_attr="annotation",  # hard-wired in views.py, too
                        ann=str(dg_ann.pk))
        return self.sess_xml.find(trs_path)

    def add_transcription(self, trs):
        dg_ann = trs.dialogue_annotation
        user_turns = self.sess_xml.findall(self.USERTURN_PATH)
        turn_xml = filter(
            lambda turn_xml: \
                int(turn_xml.get(self.TURNNUMBER_ATTR)) \
                    == trs.turn.turn_number,
            user_turns)[0]
        if self.TRANSCRIPTIONS_ELEM is not None:
            trss_xml = turn_xml.find(self.TRANSCRIPTIONS_ELEM)
            if trss_xml is None:
                trss_left_sib = turn_xml.find(
                    self.TRANSCRIPTIONS_BEFORE)
                if trss_left_sib is None:
                    insert_idx = len(turn_xml)
                else:
                    insert_idx = turn_xml.index(trss_left_sib) + 1
                trss_xml = etree.Element(self.TRANSCRIPTIONS_ELEM)
                turn_xml.insert(insert_idx, trss_xml)
        else:
            trss_xml = turn_xml
        trs_xml = etree.Element(
            self.TRANSCRIPTION_ELEM,
            author=dg_ann.user.username,
            annotation=str(dg_ann.pk),
            is_gold="0",
            breaks_gold="1" if trs.breaks_gold else "0",
            some_breaks_gold="1" if trs.some_breaks_gold else "0",
            program_version=dg_ann.program_version)
        trs_xml.set(self.DATE_ATTR,
                    self.format_datetime(dg_ann.date_saved))
        trs_xml.text = trs.text
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

    def add_annotation(self, dg_ann):
        anns_above = self.sess_xml.find(self.ANNOTATIONS_ABOVE)
        anns_after = anns_above.find(self.ANNOTATIONS_AFTER)
        anns_after_idx = (anns_above.index(anns_after)
                          if anns_after is not None
                          else len(anns_above))
        found_anns = False
        if anns_after_idx > 0:
            anns_el = anns_above[anns_after_idx - 1]
            if anns_el.tag == self.ANNOTATIONS_ELEM:
                found_anns = True
        if not found_anns:
            anns_el = etree.Element(self.ANNOTATIONS_ELEM)
            anns_above.insert(anns_after_idx, anns_el)
        # Second, create an appropriate element for the new annotation.
        etree.SubElement(
            anns_el,
            self.ANNOTATION_ELEM,
            id=str(dg_ann.pk),
            quality=('clear' if dg_ann.quality == 1 else 'noisy'),
            accent=dg_ann.accent or "native",
            offensive=str(dg_ann.offensive),
            program_version=dg_ann.program_version,
            date_saved=self.format_datetime(dg_ann.date_saved),
            user=dg_ann.user.username)\
                .text = dg_ann.notes

    def iter_uturns(self):
        for uturn_xml in self.sess_xml.iterfind(self.USERTURN_PATH):
            rec = uturn_xml.find(self.REC_SUBPATH)
            if rec is not None:
                rec = rec.attrib[self.REC_FNAME_ATTR]
            turn_number = uturn_xml.attrib[self.TURNNUMBER_ATTR]
            yield UserTurn_nt(turn_number, rec)

    def iter_systurns(self):
        for systurn_xml in self.sess_xml.iterfind(self.SYSTURN_PATH):
            turn_number = systurn_xml.attrib[self.TURNNUMBER_ATTR]
            try:
                text = systurn_xml.findtext(self.SYSTEXT_SUBPATH).strip()
            except AttributeError:
                # Some turns might not have the text subelement.
                yield SystemTurn_nt(turn_number, "")
                continue
            # Throw away some distracting pieces of system prompts.
            if (text.startswith("Thank you for using")
                    or text.startswith("Thank you goodbye")):
                continue
            text = text.replace(
                "Thank you for calling the Cambridge Information system. "
                "Your call will be recorded for research purposes.",
                "").strip()
            yield SystemTurn_nt(turn_number, text)
