from datetime import datetime
import os
import os.path
import shutil

from django import forms
from django.contrib import admin, messages
from django.db import models
from django.shortcuts import render

from session_xml import XMLSession
import settings
from transcription.crowdflower import JsonDialogueUpload, \
    price_class_handler, update_gold
from transcription.db_fields import SizedTextField, ROCharField
from transcription.dg_util import update_price
from transcription.form_fields import LinkField
from transcription.models import Dialogue, DialogueAnnotation, \
    Transcription, UserTurn
from transcription.widgets import ROInput


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


class DialogueAdmin(admin.ModelAdmin):
    list_display = ['dirname', 'cid', 'transcription_price', 'code',
                    'code_corr', 'code_incorr']
    formfield_overrides = {
        ROCharField: {'widget': ROInput},
        models.FilePathField: {'widget': ROInput},
        models.ForeignKey: {'form_class': LinkField}
    }
    inlines = [DgAnnInline, UTurnInline]
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

    list_filter = ('list_filename', PriceBinListFilter)

    # Add view #
    ############
    add_form_template = 'trs/import.html'

    def add_view(self, request, form_url="", extra_context=None):
        if extra_context is None:
            extra_context = dict()
        extra_context['use_cf'] = settings.USE_CF
        return super(DialogueAdmin, self).add_view(
            request, form_url, extra_context)

    # Actions #
    ###########
    def update_price_action(modeladmin, request, queryset):
        for dg in queryset:
            update_price(dg)
            dg.save()
        modeladmin.message_user(request,
                          'Price for dialogue shas been successfully updated.')

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

    if settings.USE_CF:
        def update_gold_action(modeladmin, request, queryset):
            for dg in queryset:
                success, msg = update_gold(dg)
                if success:
                    modeladmin.message_user(
                        request,
                        'Gold dialogues have been updated to Crowdflower.')
                else:
                    messages.error(
                        request,
                        ('Failed to update the gold status on Crowdflower: '
                         '{msg}').format(msg=msg))

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

        actions = [update_price_action, export_annotations,
                   upload_to_crowdflower, update_gold_action]
    else:
        actions = [update_price_action, export_annotations]


class DialogueAnnotationAdmin(admin.ModelAdmin):
    formfield_overrides = {
        ROCharField: {'widget': ROInput},
        models.ForeignKey: {'form_class': LinkField},
        SizedTextField: {'widget': forms.Textarea(attrs={'rows': '3'})}
    }
    inlines = [TranscriptionInline]
    search_fields = ['dialogue__cid', 'dialogue__code', 'dialogue__dirname']
    list_filter = ['user__username',
                   'finished',
                   'offensive',
                   'accent']

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

        actions = [update_gold_action]
    else:
        actions = list()


class TranscriptionAdmin(admin.ModelAdmin):
    date_hierarchy = 'date_updated'
    fields = ('text', 'turn', 'dialogue_annotation', 'is_gold', 'breaks_gold')
    raw_id_fields = ('turn', 'dialogue_annotation')
    formfield_overrides = {
        ROCharField: {'widget': ROInput},
        models.ForeignKey: {'form_class': LinkField},
        SizedTextField: {'widget': forms.Textarea(attrs={'rows': '3'})}
    }
    search_fields = ['text']
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
            user = dg_ann.user.username
            user2trss.setdefault(user, list()).append(trs)
            user2prices.setdefault(user, dict()).setdefault(
                dg_ann, dg_ann.dialogue.transcription_price)
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
    inlines = [TranscriptionInline]


admin.site.register(UserTurn, UserTurnAdmin)
admin.site.register(Dialogue, DialogueAdmin)
admin.site.register(DialogueAnnotation, DialogueAnnotationAdmin)
admin.site.register(Transcription, TranscriptionAdmin)
