# -*- coding: UTF-8 -*-
# This code is mostly PEP8-compliant. See
# http://www.python.org/dev/peps/pep-0008/.
from __future__ import unicode_literals

from collections import namedtuple
from datetime import datetime
import os
import os.path
import shutil

from django import forms
from django.contrib import admin, messages
from django.db import models
# from django.db.models import Count
from django.shortcuts import render

from session_xml import update_worker_cers, XMLSession
import settings
from transcription.crowdflower import price_class_handler
if settings.USE_CF:
    from transcription.crowdflower import JsonDialogueUpload, update_gold
from transcription.db_fields import SizedTextField, ROCharField
from transcription.dg_util import update_price
from transcription.form_fields import LinkField
from transcription.models import (Dialogue, DialogueAnnotation, Transcription,
                                  UserTurn, SystemTurn)
from transcription.tr_normalisation import char_er, trss_match
from transcription.util import group_by
from transcription.widgets import ROInput


TrsComparison_nt = namedtuple('TrsComparison',
                              ['turn_id', 'turn_name', 'gold_trss',
                               'breaking_trss'])


class DgAnnInline(admin.TabularInline):
    model = DialogueAnnotation
    extra = 0
    formfield_overrides = {
        ROCharField: {'widget': ROInput},
        SizedTextField: {'widget': forms.Textarea(attrs={'rows': '3'})}
    }


class TranscriptionInline(admin.TabularInline):
    model = Transcription
    extra = 0
    formfield_overrides = {
        ROCharField: {'widget': ROInput},
        SizedTextField: {'widget': forms.Textarea(attrs={'rows': '3'})},
        models.ForeignKey: {'form_class': LinkField}
    }


class UTurnInline(admin.TabularInline):
    model = UserTurn
    extra = 0
    formfield_overrides = {
        ROCharField: {'widget': ROInput}
    }


class SysTurnInline(admin.TabularInline):
    model = SystemTurn
    extra = 0
    formfield_overrides = {
        ROCharField: {'widget': ROInput}
    }


class DialogueAdmin(admin.ModelAdmin):
    list_display = ['dirname', 'cid', 'transcription_price', 'code',
                    'code_corr', 'code_incorr']
    formfield_overrides = {
        ROCharField: {'widget': ROInput},
        models.FilePathField: {'widget': ROInput},
        models.ForeignKey: {'form_class': LinkField}
    }
    inlines = [DgAnnInline, UTurnInline, SysTurnInline]
    search_fields = ['cid', 'code', 'dirname']

    # Filters #
    ###########
    class PriceBinListFilter(admin.SimpleListFilter):
        title = 'price bin'
        parameter_name = 'price_bin'

        def lookups(self, request, model_admin):
            price_ranges = price_class_handler.price_ranges
            # If there are no price ranges to distinguish,
            if len(price_ranges) == 1:
                # Do not use this filter at all.
                return None
            else:
                def format_cents(price_usd):
                    return ('' if abs(price_usd) == float('inf')
                            else '{0}c'.format(int(100 * price_usd)))

                readable = ['{start}-{end}'.format(start=format_cents(low),
                                                   end=format_cents(high))
                            for low, high in price_ranges]
                return [(readable_mem, readable_mem)
                        for readable_mem in readable]

        def queryset(self, request, queryset):
            val = self.value()
            if not val or val == 'all':
                return queryset
            else:
                new_set = queryset
                start, end = val.split('-', 1)
                # Filter by lower bound on the price (inclusive).
                if start:
                    # strip the trailing 'c', convert to dollars
                    start = float(start[:-1]) / 100.
                    new_set = new_set.filter(transcription_price__gte=start)
                # Filter by upper bound on the price (exclusive).
                if end:
                    # strip the trailing 'c', convert to dollars
                    end = float(end[:-1]) / 100.
                    new_set = new_set.filter(transcription_price__lt=end)
                return new_set

    class GoldListFilter(admin.SimpleListFilter):
        title = 'gold status'
        parameter_name = 'gold'

        def lookups(self, request, model_admin):
            return (('1', 'true'), ('0', 'false'))

        def queryset(self, request, queryset):
            val = self.value()
            if not val:
                return queryset

            if val == '1':
                return queryset.filter(
                    dialogueannotation__transcription__is_gold=True).distinct()
            else:
                return queryset.exclude(
                    dialogueannotation__transcription__is_gold=True).distinct()

    class AnnotatedListFilter(admin.SimpleListFilter):
        title = 'Is annotated'
        parameter_name = 'anned'

        def lookups(self, request, model_admin):
            return (('1', 'true'), ('0', 'false'))

        def queryset(self, request, queryset):
            val = self.value()
            if not val:
                return queryset

            is_anned = bool(int(val))
            if is_anned:
                return queryset.filter(dialogueannotation__finished=True
                                       ).distinct()
            else:
                return queryset.exclude(dialogueannotation__finished=True)

    list_filter = ('list_filename', GoldListFilter, AnnotatedListFilter,
                   PriceBinListFilter)

    # Add view #
    ############
    add_form_template = 'trs/import.html'

    def add_view(self, request, form_url="", extra_context=None):
        if extra_context is None:
            extra_context = dict()
        extra_context['use_cf'] = settings.USE_CF
        extra_context['app_url'] = settings.APP_URL
        return super(DialogueAdmin, self).add_view(
            request, form_url, extra_context)

    # Actions #
    ###########
    def update_price_action(modeladmin, request, queryset):
        for dg in queryset:
            update_price(dg)
            dg.save()
        modeladmin.message_user(
            request, 'Price for dialogue shas been successfully updated.')

    update_price_action.short_description = "Update dialogue price"

    def export_annotations(self, request, queryset):
        tgt_dir = os.path.join(settings.EXPORT_DIR, '{dt}-sessions'.format(
            dt=datetime.strftime(datetime.now(), '%y%m%d%H%M')))
        os.makedirs(tgt_dir)
        for dg in queryset:
            dg_dir = os.path.join(settings.CONVERSATION_DIR, dg.cid)
            dg_xml = XMLSession.find_session_fname(dg_dir)
            tgt_dg_dir = os.path.join(tgt_dir, dg.dirname)
            os.mkdir(tgt_dg_dir)
            shutil.copy2(dg_xml, tgt_dg_dir)
        # Output a message to the user.
        self.message_user(request,
                          '{num} dialogue annotation{shashave} been '
                          'successfully exported to {outdir}.'.format(
                          num=len(queryset),
                          shashave=' has' if len(queryset) == 1 else 's have',
                          outdir=tgt_dir))

    export_annotations.short_description = "Export annotations"

    def export_logs(self, request, queryset):
        tgt_dir = os.path.join(settings.EXPORT_DIR, '{dt}-logs'.format(
            dt=datetime.strftime(datetime.now(), '%y%m%d%H%M')))
        os.makedirs(tgt_dir)
        for dg in queryset:
            dg_dir = os.path.join(settings.CONVERSATION_DIR, dg.cid)
            tgt_dg_dir = os.path.join(tgt_dir, dg.dirname)
            shutil.copytree(dg_dir, tgt_dg_dir)
        # Output a message to the user.
        self.message_user(request,
                          '{num} dialogue log{shashave} been '
                          'successfully exported to {outdir}.'.format(
                          num=len(queryset),
                          shashave=' has' if len(queryset) == 1 else 's have',
                          outdir=tgt_dir))

    export_logs.short_description = "Export logs (annotations and audio)"

    def compute_ers(modeladmin, request, queryset):
        """Computes average error rates for workers."""
        # TODO Test.
        ann2w_cer = dict()  # :: {dg_ann.pk -> [trs_char_er]}

        # Compute ann2w_cer for queryset
        gold_turns = (UserTurn.objects.filter(transcription__is_gold=True,
                                              dialogue__in=queryset)
                      .distinct())
        trss = Transcription.objects.filter(turn__in=gold_turns)
        trss_by_turn = group_by(trss, ('turn', ))

        for (turn, ), trss in trss_by_turn.iteritems():
            gold_trss = [trs for trs in trss if trs.is_gold]
            for trs in trss:
                if trs.is_gold:
                    min_char_er = 0.
                else:
                    min_char_er = min(char_er(trs, gold_trs)
                                      for gold_trs in gold_trss)
                dg_ann = trs.dialogue_annotation.pk
                ann2w_cer.setdefault(dg_ann, list()).append(min_char_er)

        # Pass ann2w_cer to a session_xml method that saves it to the XML
        # logs.
        n_files, n_workers, n_anns = update_worker_cers(ann2w_cer)

        # Return a success message.
        msg = ('Worker average character error rates for {n_workers} '
               'workers have been updated.  {n_files} session logs and '
               '{n_anns} individual annotations were updated.'
               ).format(n_workers=n_workers, n_files=n_files, n_anns=n_anns)
        modeladmin.message_user(request, msg)

    compute_ers.short_description = 'Compute average character error rates'

    if settings.USE_CF:
        def update_gold_action(modeladmin, request, queryset):
            for dg in queryset:
                success, msg = update_gold(dg)
                if success:
                    modeladmin.message_user(
                        request,
                        ('Gold status of {cid} has been updated at Crowdflower'
                         .format(cid=dg.cid)))
                else:
                    messages.error(
                        request,
                        ('Failed to update the gold status of {cid} at '
                         'Crowdflower: {msg}').format(cid=dg.cid, msg=msg))

        update_gold_action.short_description = (
            "Update dialogue gold status on CF")

        def upload_to_crowdflower(modeladmin, request, queryset):
            success, msg = JsonDialogueUpload(queryset).upload()
            if success:
                modeladmin.message_user(
                    request,
                    '{num} dialogues have been successfully uploaded to '
                    'Crowdflower.'.format(num=msg))
            else:
                messages.error(request,
                               ('Failed to upload the dialogues: {msg}'
                                .format(msg=msg)))

        upload_to_crowdflower.short_description = (
            'Upload to CrowdFlower (only those dialogues that have not been '
            'uploaded yet)')

        def upload_to_higher_job(modeladmin, request, queryset):
            success, msg = JsonDialogueUpload(queryset, to_higher=True
                                              ).upload()
            if success:
                modeladmin.message_user(
                    request,
                    '{num} dialogues have been successfully uploaded to '
                    'Crowdflower to a higher price class.'.format(num=msg))
            else:
                messages.error(request,
                               ('Failed to upload the dialogues: {msg}'
                                .format(msg=msg)))

        upload_to_higher_job.short_description = (
            'Upload to CrowdFlower (to a higher price class)')

        actions = [update_price_action, export_annotations, export_logs,
                   compute_ers, upload_to_crowdflower, update_gold_action,
                   upload_to_higher_job]
    else:
        actions = [update_price_action, compute_ers, export_annotations,
                   export_logs]


class DialogueAnnotationAdmin(admin.ModelAdmin):
    formfield_overrides = {
        ROCharField: {'widget': ROInput},
        models.ForeignKey: {'form_class': LinkField},
        SizedTextField: {'widget': forms.Textarea(attrs={'rows': '3'})}
    }
    inlines = [TranscriptionInline]
    search_fields = ['dialogue__cid', 'dialogue__code', 'dialogue__dirname']

    # Filters #
    ###########
    class GoldListFilter(admin.SimpleListFilter):
        title = 'gold status'
        parameter_name = 'gold'

        def lookups(self, request, model_admin):
            return (('1', 'true'), ('0', 'false'))

        def queryset(self, request, queryset):
            val = self.value()
            if not val:
                return queryset

            if val == '1':
                return queryset.filter(transcription__is_gold=True).distinct()
            else:
                return queryset.exclude(transcription__is_gold=True).distinct()

    class TranscriptionCountListFilter(admin.SimpleListFilter):
        title = 'number of transcriptions'
        parameter_name = 'trs_count'

        def lookups(self, request, model_admin):
            return (('0', '0'), ('1', '>0'))
#             trs_counts = set(
#                 attrs['num_trss'] for attrs in
#                 Transcription.objects.values('dialogue_annotation')
#                     .annotate(num_trss=Count('pk')))
#             if (DialogueAnnotation.objects.annotate(Count('transcription'))
#                     .filter(transcription__count=0).exists()):
#                 trs_counts.add('0')
#             return sorted(((cnt, cnt) for cnt in trs_counts),
#                           key=lambda tup: int(tup[0]))

        def queryset(self, request, queryset):
            val = self.value()
            if not val:
                return queryset

            if val == '0':
                return queryset.filter(transcription__isnull=True).distinct()
            elif val == '1':
                return queryset.filter(transcription__isnull=False).distinct()
            else:
                return queryset

#             val = int(val)
#             return queryset.annotate(Count('transcription')).filter(
#                 transcription__count=val)

    class BreaksGoldListFilter(admin.SimpleListFilter):
        title = 'breaks gold'
        parameter_name = 'breaks_gold'

        def lookups(self, request, model_admin):
            return (('1', 'true'), ('0', 'false'), ('-1', 'has no gold'))

        def queryset(self, request, queryset):
            val = self.value()
            if not val:
                return queryset

            if val == '1':
                return queryset.filter(transcription__breaks_gold=True
                                       ).distinct()
            elif val == '-1':
                return queryset.exclude(
                    transcription__turn__transcription__is_gold=True
                    ).distinct()
            else:
                return queryset.exclude(transcription__breaks_gold=True
                                        ).distinct()

    class PriceBinListFilter(admin.SimpleListFilter):
        title = 'price bin'
        parameter_name = 'price_bin'

        def lookups(self, request, model_admin):
            price_ranges = price_class_handler.price_ranges
            # If there are no price ranges to distinguish,
            if len(price_ranges) == 1:
                # Do not use this filter at all.
                return None
            else:
                def format_cents(price_usd):
                    return ('' if abs(price_usd) == float('inf')
                            else '{0}c'.format(int(100 * price_usd)))

                readable = ['{start}-{end}'.format(start=format_cents(low),
                                                   end=format_cents(high))
                            for low, high in price_ranges]
                return [(readable_mem, readable_mem)
                        for readable_mem in readable]

        def queryset(self, request, queryset):
            val = self.value()
            if not val or val == 'all':
                return queryset
            else:
                new_set = queryset
                start, end = val.split('-', 1)
                # Filter by lower bound on the price (inclusive).
                if start:
                    # strip the trailing 'c', convert to dollars
                    start = float(start[:-1]) / 100.
                    new_set = new_set.filter(
                        dialogue__transcription_price__gte=start)
                # Filter by upper bound on the price (exclusive).
                if end:
                    # strip the trailing 'c', convert to dollars
                    end = float(end[:-1]) / 100.
                    new_set = new_set.filter(
                        dialogue__transcription_price__lt=end)
                return new_set

    list_filter = [GoldListFilter,
                   BreaksGoldListFilter,
                   TranscriptionCountListFilter,
                   PriceBinListFilter,
                   'user__username',
                   'finished']
    if 'offensive' in settings.EXTRA_QUESTIONS:
        list_filter.append('offensive')
    if 'accent' in settings.EXTRA_QUESTIONS:
        list_filter.append('accent')

    # Actions #
    ###########
    def update_gold_status_action(modeladmin, request, queryset):
        n_changed = [0, 0]  # to not breaks, to breaks

        dgs = queryset.values_list('dialogue', flat=True).distinct()
        for dg in dgs:
            dg_trss = Transcription.objects.filter(
                dialogue_annotation__dialogue=dg)
            gold_trss = dg_trss.filter(is_gold=True)
            gold_trss_turns = (
                gold_trss.values_list('turn__turn_number', flat=True)
                .distinct())
            plain_trss = dg_trss.filter(dialogue_annotation__in=queryset,
                                        is_gold=False)

            # Transcriptions for turns with no gold do not break gold.
            n_changed[0] += plain_trss.filter(breaks_gold=True)\
                .exclude(turn__turn_number__in=gold_trss_turns)\
                .update(breaks_gold=False)

            # Transcriptions for turns that have gold need to be checked.
            to_check_trss = plain_trss.filter(
                turn__turn_number__in=gold_trss_turns)
            gold4turn = {turnnum: gold_trss.filter(turn__turn_number=turnnum)
                         for turnnum in gold_trss_turns}

            for plain_trs in to_check_trss:
                broke_gold = plain_trs.breaks_gold

                breaks_gold = True
                for gold_trs in gold4turn[plain_trs.turn.turn_number]:
                    if trss_match(plain_trs, gold_trs,
                                  max_char_er=settings.MAX_CHAR_ER):
                        breaks_gold = False
                        break

                if breaks_gold != broke_gold:
                    plain_trs.breaks_gold = breaks_gold
                    plain_trs.save()
                    n_changed[breaks_gold] += 1

        msg = ('{n} transcriptions had their gold breaking status changed, '
               '{good} to OK, {bad} to gold-breaking.').format(
                   n=n_changed[0] + n_changed[1],
                   good=n_changed[0],
                   bad=n_changed[1])
        modeladmin.message_user(request, msg)

    update_gold_status_action.short_description = (
        "Update gold breaking statuses")

    def show_gold_breaking_trss(modeladmin, request, queryset):
        # Find the transcriptions from the queryset that break gold.
        breaking_trss = Transcription.objects.filter(
            breaks_gold=True, dialogue_annotation__in=queryset)
        broken_turn_pks = breaking_trss.values_list('turn',
                                                    flat=True).distinct()
        # Find gold transcriptions for corresponding turns.
        gold_trss = Transcription.objects.filter(
            is_gold=True, turn__in=broken_turn_pks).distinct()
        # Group them by the turn.
        brss_by_turn = group_by(breaking_trss, ('turn', ))
        goss_by_turn = group_by(gold_trss, ('turn', ))

        # Generate the template.
        dummy_trs = {'text': '!!!MISSING!!!'}
        turn_name_tpt = '{dirname}:{turn_number}'

        def turn_key2str(turn_key):
            turn, = turn_key
            return turn_name_tpt.format(dirname=turn.dialogue.dirname,
                                        turn_number=turn.turn_abs_number)

        comparisons = [TrsComparison_nt(
            turn_key[0].pk,
            turn_key2str(turn_key),
            goss_by_turn.get(turn_key, [dummy_trs]),
            brss_by_turn.get(turn_key, [dummy_trs]))
            for turn_key in brss_by_turn]
        context = {'comparisons': comparisons,
                   'SUB_SITE': settings.SUB_SITE}
        return render(request, 'trs/goldbreaking.html', context)

    show_gold_breaking_trss.short_description = (
        "Show what transcriptions break gold")

    date_hierarchy = 'date_saved'

    if settings.USE_CF:
        def update_gold_action(modeladmin, request, queryset):
            dialogues = set(dg_ann.dialogue for dg_ann in queryset)
            for dialogue in dialogues:
                success, _ = update_gold(dialogue)
                if not success:
                    raise ValueError()

        update_gold_action.short_description = (
            "Update gold status of related dialogues on CF")

        actions = (update_gold_action, update_gold_status_action,
                   show_gold_breaking_trss)
    else:
        actions = (update_gold_status_action, show_gold_breaking_trss)


class TranscriptionAdmin(admin.ModelAdmin):
    date_hierarchy = 'date_updated'
    fields = ('text', 'turn', 'dialogue_annotation', 'is_gold', 'breaks_gold')
    raw_id_fields = ('turn', 'dialogue_annotation')
    formfield_overrides = {
        ROCharField: {'widget': ROInput},
        models.ForeignKey: {'form_class': LinkField},
        SizedTextField: {'widget': forms.Textarea(attrs={'rows': '3'})}
    }
    search_fields = ['text', 'dialogue_annotation__dialogue__cid']
    list_filter = ['is_gold',
                   'breaks_gold',
                   'dialogue_annotation__user__username',
                   'dialogue_annotation__dialogue__list_filename',
                   'dialogue_annotation__date_saved',
                   'dialogue_annotation__date_paid']

    def toggle_gold(modeladmin, request, queryset):
        for trs in queryset:
            trs.is_gold = not trs.is_gold
            trs.save()

    toggle_gold.short_description = "Toggle gold status"

    def work_measures(modeladmin, request, queryset):
        # Group the transcriptions and their dialogues according to the author.
        user2trss = dict()
        user2prices = dict()  # :: username -> dialogue annotation -> price
        for trs in queryset:
            dg_ann = trs.dialogue_annotation
            try:
                user = dg_ann.user.username
            except AttributeError:
                user = ''
            user2trss.setdefault(user, list()).append(trs)
            user2prices.setdefault(user, dict()).setdefault(
                dg_ann, dg_ann.dialogue.transcription_price)
        # Remap the anonymous user to the 'anonymous' username.
        if '' in user2prices and 'anonymous' not in user2prices:
            user2prices['anonymous'] = user2prices['']
            user2trss['anonymous'] = user2trss['']
            del user2prices['']
            del user2trss['']
        # Compute statistics.
        user2price = {user: sum(ann2price.values())
                      for user, ann2price in user2prices.iteritems()}
        user2dgnum = {user: len(ann2price)
                      for user, ann2price in user2prices.iteritems()}
        user2trsnum = {user: len(user_trss)
                       for user, user_trss in user2trss.iteritems()}
        user2wordcnt = {user: sum(len(trs.text.split()) for trs in user_trss)
                        for user, user_trss in user2trss.iteritems()}
        context = dict()
        context['measures'] = sorted((user, user2dgnum[user],
                                      user2trsnum[user], user2wordcnt[user],
                                      user2price[user])
                                     for user in user2price)
        return render(request, 'trs/work_measures.html', context)

    work_measures.short_description = "Measure work done"

    actions = [toggle_gold, work_measures]


class UserTurnAdmin(admin.ModelAdmin):
    formfield_overrides = {
        ROCharField: {'widget': ROInput},
        models.ForeignKey: {'form_class': LinkField},
    }
    search_fields = ['dialogue__cid', 'dialogue__dirname']
    inlines = [TranscriptionInline]


admin.site.register(UserTurn, UserTurnAdmin)
admin.site.register(Dialogue, DialogueAdmin)
admin.site.register(DialogueAnnotation, DialogueAnnotationAdmin)
admin.site.register(Transcription, TranscriptionAdmin)
