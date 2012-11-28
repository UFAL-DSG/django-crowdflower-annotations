import datetime
import hashlib
import itertools
import os
import random
import re
from subprocess import check_output
from collections import OrderedDict, defaultdict

import lxml.etree as etree
import settings
from transcription.models import Transcription, Dialogue
from transcription.parser import DialogParser
from django import forms
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.template import RequestContext
from django.utils.safestring import mark_safe


# Constants.
TRS_FNAME = "user-transcription.xml"
_more_spaces = re.compile(r'\s{2,}')
_special_words = ["breath", "hum", "laugh", "noise", "sil", "unint"]
_special_rx = '(?:' + '|'.join(_special_words) + ')'
_dashusc_rx = re.compile(r'[_-]')
_nondashusc_punct_rx = re.compile(r'(?![\s_-])\W', flags=re.UNICODE)
_w_vimrx = re.compile(r'\b\w*\W*', flags=re.UNICODE)


def group_by(objects, attrs):
    """Groups `objects' by the values of their attributes `attrs'.

    Returns a dictionary mapping from a tuple of attribute values to a list of
    objects with those attribute values.

    """
    groups = dict()
    for obj in objects:
        key = tuple(obj.__dict__[attr] for attr in attrs)
        groups.setdefault(key, []).append(obj)
    return groups


def lowercase(text):
    """Lowercases text except for words with multiple capital ltrs in them.

    Assumes the text has been tokenised.

    May return the same object, or a newly constructed string, depending on
    whether any substitutions were needed.

    """
    words = _w_vimrx.findall(text)
    made_changes = False
    for wordIdx, word in enumerate(words):
        lower = word.lower()
        # If the lowercased version does not differ from the original word
        # except maybe for the first letter,
        if sum(map(lambda char1, char2: char1 != char2,
                   word[1:],
                   lower[1:])) == 0:
            # Substitute the word with its lowercased version.
            words[wordIdx] = lower
            made_changes = True
    if made_changes:
        return u''.join(words)
    else:
        return text


def remove_punctuation(text):
    """Removes punctuation characters from `text' except for parentheses around
    special symbols."""
    text = re.sub(_dashusc_rx, '', text)
    text = re.sub(r'\(({s})\)'.format(s=_special_rx),
                  r'_\1-',
                  text)
    text = re.sub(_nondashusc_punct_rx, '', text)
    return re.sub(r'_({s})-'.format(s=_special_rx),
                  r'(\1)',
                  text)


def _get_hashed(files, hash):
    res = list(itertools.ifilter(
        lambda x: x[1] == hash,
        map(lambda f: (f, _hash(f)), files)))
    if len(res) == 1:
        return res[0]
    elif len(res) == 0:
        return None
    else:
        raise Exception("finding appropriate hash failed, " + \
                        "{0} matches".format(len(res)))


def _hash(s):
    return hashlib.sha1(s).hexdigest()


class HorizRadioRenderer(forms.RadioSelect.renderer):
    """ This overrides `widget' method to put radio buttons horizontally
        instead of vertically.
        """
    def render(self):
        """Outputs radios"""
        return mark_safe(u'\n'.join([u'%s\n' % w for w in self]))


class TranscriptionForm(forms.Form):
    def __init__(self, *args, **kwargs):
        turns = kwargs.pop('turns')
        cid = kwargs.pop('cid', None)
        super(TranscriptionForm, self).__init__(*args, **kwargs)

        self.fields['cid'] = forms.CharField(widget=forms.HiddenInput(),
                                             initial=cid)

        for turn in turns:
            if not turn.has_rec:
                continue
            self.fields['trs_{0}'.format(turn.id)] = \
                forms.CharField(widget=forms.Textarea(
                    attrs={'style': 'width: 90%', 'rows': '3'}),
                    label=turn.id)


class RatingForm(forms.Form):
    def __init__(self, *args, **kwargs):
        questions = kwargs.pop('questions')
        cid = kwargs.pop('cid', None)
        super(RatingForm, self).__init__(*args, **kwargs)

        self.fields['_cid'] = forms.CharField(widget=forms.HiddenInput(),
                                              initial=cid)

        for i, q in enumerate(questions):
            self.fields['custom_{0}'.format(q.id_text)] =\
                forms.ModelChoiceField(
                    q.answer_set.all().order_by('order_index'),
                    label=q.text,
                    widget=forms.RadioSelect(renderer=HorizRadioRenderer),
                    empty_label=None)
            if len(q.text_whynot) > 0:
                self.fields['comment_custom_{0}'.format(q.id_text)] =\
                    forms.CharField(widget=forms.Textarea(
                        attrs={'style': 'width: 80%', 'rows': "4", }),
                        label=q.text_whynot,
                        required=False)


def _get_conversations():
#     cdir = settings.CONVERSATION_DIR
    cdirs_fname = settings.CONVERSATION_FILE_LIST
    with open(cdirs_fname, "r") as cdirs_file:
        dirnames = [line.rstrip() for line in cdirs_file]

    dirnames = [dirname for dirname in dirnames
                if settings.CONVERSATION_PATTERN.match(dirname) is not None]
    #dirnames.sort()
    return dirnames


@login_required
def finished(request):
    return render(request, "er/finished.html")


def _find_free_dir(dirnames, user):
    # Here we assume the following:
    #   If the user has transcribed some non-gold items (turns) from the
    #   dialogue, he/she has transcribed the whole dialogue.
    trsed_dirs = set([trs.object_id for trs in
                      Transcription.objects.filter(user=user, is_gold=False)])
    for dirname in dirnames:
        if not dirname in trsed_dirs:
            return dirname
        else:
            trsed_dirs.remove(dirname)


def _gen_codes():
    """Generates a random code for a dialogue, to be used in validation of CF
    workers' input."""
    code = ''.join([random.choice('0123456789')
                    for _ in xrange(settings.CODE_LENGTH)])
    code_corr = ''.join([random.choice('0123456789')
                         for _ in xrange(settings.CODE_LENGTH_EXT)])
    code_incorr = ''.join([random.choice('0123456789')
                           for _ in xrange(settings.CODE_LENGTH_EXT)])
    return (code, code_corr, code_incorr)


def _write_codes(codes, fname):
    """Writes dialogue codes to the file with the name specified."""
    with open(fname, 'w') as code_file:
        code_file.writelines(code + '\n' for code in codes)


def _read_codes(fname):
    """Reads dialogue codes from the file with the name specified."""
    with open(fname, 'r') as code_file:
        codes = [line.rstrip('\n') for line in code_file.readlines()]
    return codes


def _get_codes(dirname,
               cdir=settings.CONVERSATION_DIR,
               fname=settings.CODE_FNAME):
    code_fname = os.path.join(cdir, dirname, fname)
    # Assign the dialogue a persistent code for validation of CF workers.
    # Create two more (shorter, perhaps 3-character) codes, one for
    # correct transcriptions, one for wrong ones.
    if not os.path.exists(code_fname):
        # Generate new codes for the dialogue.
        dg_codes = _gen_codes()
        _write_codes(dg_codes, code_fname)
    else:
        # or, use the previously generated ones.
        dg_codes = _read_codes(code_fname)
    return dg_codes


def normalise_trs_text(text):
    """Normalises the text of a transcription:

        - throws away capitalisation except for words with multiple capital
          letters in them
        - throws away punctuation marks except for parentheses in special
          symbols
        - removes non-speech symbols
        - performs some predefined word substitutions.

    """
    # Remove punctuation.
    text = remove_punctuation(text)
    # Shrink spaces.
    text = _more_spaces.sub(u' ', text.strip())
    text = lowercase(text)
    # TODO Do the other modifications yet.
    return text


def trss_match(trs1, trs2):
    """Checks whether two given transcriptions can be considered equal.

    Keyword arguments:
        trs1: first Transcription to compare
        trs2: second Transcription to compare

    """
    # FIXME: Ignore non-speech events.
    return normalise_trs_text(trs1.text) == normalise_trs_text(trs2.text)


def _read_dialogue(dirname, cdir=settings.CONVERSATION_DIR, xmlname=TRS_FNAME):
    dialogue = DialogParser.parse(os.path.join(cdir, dirname, xmlname))
    dialogue.delete_from("Thank you for using the system.")
    # TODO Delete also the long, repeating introduction.
    dialogue.path = "/data/recs/" + dirname
    return dialogue


@login_required
def transcribe(request):
    # If the form has been submitted,
    if request.method == "POST":
        cid = request.POST['cid']
        dirname = Dialogue.objects.get(cid=cid).dirname
        dialogue = _read_dialogue(dirname)
        dg_codes = _get_codes(dirname)
        form = TranscriptionForm(request.POST, cid=cid, turns=dialogue.turns)

        if form.is_valid():
            trss = dict()
            for turn in dialogue.turns:
                if not turn.has_rec:
                    continue
                trs = Transcription()
                trss[turn.id] = trs
                trs.user = request.user
                trs.text = form.cleaned_data['trs_{0}'.format(turn.id)]
                trs.turn_id = turn.id
                trs.object_id = dirname
                trs.program_version = unicode(check_output(
                    ["git", "rev-parse", "HEAD"]))
                trs.timestamp = datetime.datetime.now()

            # Check the form against any gold items.  If all are OK, return one
            # code; if not, return another.
            gold_trss = Transcription.objects.filter(object_id=dirname,
                                                     is_gold=True)
            gold_trss = group_by(gold_trss, ('object_id', 'turn_id'))
            mismatch = False
            for turn_gold_trss in gold_trss.itervalues():
                submismatch = True
                for gold_trs in turn_gold_trss:
                    if trss_match(trss[gold_trs.turn_id], gold_trs):
                        submismatch = False
                        break
                if submismatch:
                    mismatch = True
                    trss[gold_trs.turn_id].breaks_gold = True

            # Update transcriptions in the light of their comparison to gold
            # transcriptions, and save them.
            for turn in dialogue.turns:
                if not turn.has_rec:
                    continue
                trss[turn.id].some_breaks_gold = mismatch
                trss[turn.id].save()

            context = dict()
            context['code'] = dg_codes[0] + (dg_codes[2] if mismatch else
                                             dg_codes[1])
            return render(request,
                          "er/code.html",
                          context,
                          context_instance=RequestContext(request))
        # If the form is not valid,
        else:
            # Populate context with data from the previous dialogue (form).
            # TODO Test that the following works.
            context = dict()
            for key, value in request.POST.iteritems():
                context[key] = value
            return render(request,
                          "er/transcribe.html",
                          context,
                          context_instance=RequestContext(request))
    # Else, if a blank form is to be served,
    else:
        # Find the dialogue to transcribe.
        dirnames = _get_conversations()
        dirname = _find_free_dir(dirnames, request.user)
        if dirname is None:
            return HttpResponseRedirect(reverse("rating_finished"))
        dialogue = _read_dialogue(dirname)
        dg_codes = _get_codes(dirname)
        # Check that this CID does not collide with a hash for another dirname.
        # This is a crude implementation of hashing with replacement.
        cid = _hash(dirname)
        same_cid_dgs = Dialogue.objects.filter(cid=cid)
        salt = -1
        while same_cid_dgs and same_cid_dgs[0].dirname != dirname:
            salt += 1
            cid = _hash(dirname + str(salt))
            same_cid_dgs = Dialogue.objects.filter(cid=cid)
        # Save the dialogue in the DB, unless it has been there already.
        if not same_cid_dgs:
            Dialogue(dirname=dirname, cid=cid).save()

        context = dict()
        context['cid'] = cid
        context['dialogue'] = dialogue
        context['codes'] = dg_codes

        # TODO Populate context with data for a new dialogue.
        form = context['form'] = \
            TranscriptionForm(cid=cid,
                              turns=dialogue.turns)
    return render(request,
                  "er/transcribe.html",
                  context,
                  context_instance=RequestContext(request))


@login_required
def home(request):
    return render(request, "er/home.html")


def sort_by_question(lst):
    if lst is None:
        return None
    else:
        return sorted(lst,
                      cmp=lambda a, b: cmp(a.answer.question.id,
                                           b.answer.question.id))


def _compute_avg_rating(lst):
    s = defaultdict(lambda: 0)
    cnt = defaultdict(lambda: 0)
    for l in lst:
        if l is None:
            continue
        for r in l:
            if r.answer.weight != 0.0:
                cnt[r.answer.question.id] += 1
                if not r.answer.question.id in s:
                    s[r.answer.question.id] = 0

                s[r.answer.question.id] += r.answer.weight

    return [float(s[k]) / cnt[k] for k in s.keys()]


def _color_val(expression, vars):
    return eval(expression, vars)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def rating_overview_dialog(request):
    sortby = request.GET.get('sort', 'id')
    try:
        sortorder = int(request.GET.get('sorder', 1))
    except:
        sortorder = 1

    context = {}
    context['users'] = users = User.objects\
        .filter(~Q(username="admin") & ~Q(username="test"))\
        .order_by('username')

    expression = context['expression'] = \
        request.GET.get('expression',
                        'min(avg_rating_0, avg_rating_1, avg_rating_2)')

    files = _get_conversations()
    ratings = Transcription.objects.filter(
        ~Q(user__username="admin") & ~Q(user__username="test"))

    counts_db = defaultdict(lambda: defaultdict(lambda: []))
    for r in ratings:
        counts_db[r.object_id][r.user.id] += [r]

    counts = OrderedDict()
    cntr = 0
    for fname in files:
        cntr += 1
        uratings = counts_db.get(fname, {})
        sorted_ratings = [sort_by_question(uratings.get(u.id, None))
                          for u in users]
        counts[fname] = {'id': cntr,
                         'count': len(counts_db.get(fname, [])),
                         'fname': fname,
                         'ratings': sorted_ratings,
                         }

        avg_ratings = _compute_avg_rating(sorted_ratings)
        counts[fname]['avg_ratings'] = \
            {i: rat for i, rat in enumerate(avg_ratings)}

        for i, rat in enumerate(avg_ratings):
            counts[fname]['avg_rating_%d' % i] = rat

        try:
            counts[fname]['colorval'] = _color_val(expression, counts[fname])
        except:
            counts[fname]['colorval'] = -1

    context['rows'] = rows = counts.items()
    context['trsh_green'] = float(request.GET.get('trsh_green', '0.9'))
    context['trsh_red'] = float(request.GET.get('trsh_red', '0.1'))
    rows.sort(lambda a, b: sortorder * cmp(a[1].get(sortby), b[1].get(sortby)))

    return render(request, "er/overview_dialogs.html", context)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def rating_overview(request):
    counts = {}
    for user in User.objects.all():
        counts[user] = sorted(list(set(
            [o['object_id'] for o in
             Transcription.objects.filter(user=user).order_by('object_id')\
                .values('object_id')])))

    context = {}
    context['counts'] = counts
    res = render(request, "er/overview.html", context)
    return res


def rating_export(request):
    root = etree.Element('transcription')
    for user in User.objects.all():
        uelement = etree.SubElement(root, 'expert')
        uelement.attrib["login"] = user.username
        for rating in user.rating_set.all():
            relement = etree.SubElement(uelement, 'rating')
            relement.attrib["fname"] = rating.object_id
            relement.attrib["question"] = rating.answer.question.id_text
            relement.attrib["answer"] = rating.answer.id_text
            if rating.ratingcomment_set.count() > 0:
                relement.attrib["comment"] = \
                    rating.ratingcomment_set.get().comment
    return HttpResponse(etree.tostring(root), content_type="text/xml")
