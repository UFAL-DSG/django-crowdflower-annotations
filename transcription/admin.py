from django import forms
from django.contrib import admin
from django.db import models

from transcription.models import Dialogue, DialogueAnnotation, \
        Transcription, UserTurn
from transcription.dg_util import JsonDialogueUpload, update_gold, update_price
from transcription.db_fields import SizedTextField, ROCharField
from transcription.form_fields import LinkField
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
    add_form_template = 'er/import.html'
    list_display = ['dirname', 'cid', 'transcription_price', 'code',
                    'code_corr', 'code_incorr']
    formfield_overrides = {
        ROCharField: {'widget': ROInput},
        models.FilePathField: {'widget': ROInput},
        models.ForeignKey: {'form_class': LinkField}
    }
    inlines = [ DgAnnInline, UTurnInline ]
    search_fields = ['cid', 'code', 'dirname', 'list_filename']

    def update_price_action(modeladmin, request, queryset):
        for dg in queryset:
            update_price(dg)
            dg.save()

    update_price_action.short_description = u"Update dialogue price"

    def update_gold_action(modeladmin, request, queryset):
        for dg in queryset:
            success, msg = update_gold(dg)
            if not success:
                raise ValueError()

    update_gold_action.short_description = u"Update dialogue gold status on CF"

    def upload_to_crowdflower(modeladmin, request, queryset):
        JsonDialogueUpload(queryset).upload()

    upload_to_crowdflower.short_description = \
        (u'Upload to CrowdFlower (only those dialogues that have not been '
         u'uploaded yet)')

    actions = [update_price_action, upload_to_crowdflower, update_gold_action]


class DialogueAnnotationAdmin(admin.ModelAdmin):
    formfield_overrides = {
        ROCharField: {'widget': ROInput},
        models.ForeignKey: {'form_class': LinkField},
        SizedTextField: {'widget': forms.Textarea(attrs={'rows': '3'})}
    }
    inlines = [ TranscriptionInline ]

    date_hierarchy = 'date_saved'

    def update_gold_action(modeladmin, request, queryset):
        dialogues = set(dg_ann.dialogue for dg_ann in queryset)
        for dialogue in dialogues:
            success, _ = update_gold(dialogue)
            if not success:
                raise ValueError()

    update_gold_action.short_description = \
            u"Update gold status of related dialogues on CF"

    actions = [update_gold_action]


class TranscriptionAdmin(admin.ModelAdmin):
    date_hierarchy = 'date_updated'
    fields = ('text', 'turn', 'dialogue_annotation', 'is_gold', 'breaks_gold')
    raw_id_fields = ('turn', 'dialogue_annotation')
    formfield_overrides = {
        ROCharField: {'widget': ROInput},
        models.ForeignKey: {'form_class': LinkField},
        SizedTextField: {'widget': forms.Textarea(attrs={'rows': '3'})}
    }

    def toggle_gold(modeladmin, request, queryset):
        for trs in queryset:
            trs.is_gold = not trs.is_gold
            trs.save()

    toggle_gold.short_description = u"Toggle gold status"
    actions = [toggle_gold]


class UserTurnAdmin(admin.ModelAdmin):
    formfield_overrides = {
        ROCharField: {'widget': ROInput},
        models.ForeignKey: {'form_class': LinkField},
    }
    inlines = [ TranscriptionInline ]


admin.site.register(UserTurn, UserTurnAdmin)
admin.site.register(Dialogue, DialogueAdmin)
admin.site.register(DialogueAnnotation, DialogueAnnotationAdmin)
admin.site.register(Transcription, TranscriptionAdmin)
