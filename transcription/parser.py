#!/usr/bin/env python
import lxml.etree as etree
import sys


class Feedback:
    def get_goal_what(self):
        return self.goal.split(';')[0]

    def get_goal_what_info(self):
        return self.goal.split(';')[1]

    def get_goal_constraint(self):
        return self.goal.split(';')[2]


class FeedbackParser:
    @classmethod
    def parse(self, fname):
        doc = etree.parse(fname)
        f = Feedback()
        f.task = doc.findtext(".//task")
        f.goal = doc.findtext(".//goal")
        return f


class Dialog:
    def __init__(self):
        self.turns = []

    def add_turn(self, t):
        self.turns.append(t)

    def delete_from(self, s):
        self.turns = [turn for turn in self.turns
                      if turn.transcription is not None
                          and not s in turn.transcription]

    def __unicode__(self):
        ret = u'('
        for turn in self.turns:
            ret += u"\n--- TURN {0} ---".format(turn.id)
            if turn.prompt:
                ret += u"\n s:{0}".format(turn.prompt)
            if turn.transcription:
                ret += u"\n u:{0}".format(turn.transcription)
        ret += u"\n)"
        return ret


class DialogTurn:
    pass


class DialogParser:
    @staticmethod
    def parse(fname):
        doc = etree.parse(fname)
        dialog = Dialog()

        num_recs = 0 # number of recs seen so far
        for turn_xml in doc.findall("turn"):
            # FIXME: Most of the following should perhaps be moved to
            # DialogTurn.__init__().
            turn = DialogTurn()
            turn.id = int(turn_xml.attrib["turnnum"])
            turn.prompt = turn_xml.findtext(".//prompt")
            turn.transcription = turn_xml.findtext(".//transcription")
            #if turn.transcription is not None:
            try:
                turn.rec = turn_xml.find(".//rec").attrib["fname"]
            except:
                pass
            turn.has_rec = ('rec' in turn.__dict__)
            if turn.has_rec:
                turn.rec_num = num_recs
                turn.dbl_rec_num = 2 * num_recs
                num_recs += 1
            dialog.add_turn(turn)

        dialog.num_recs = num_recs
        dialog.dbl_num_recs = 2 * num_recs
        return dialog



if __name__ == '__main__':
    erp = DialogParser.parse(sys.argv[1])
