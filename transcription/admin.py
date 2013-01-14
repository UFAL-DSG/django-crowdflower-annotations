from django import forms
from django.contrib import admin
from django.db import models

from transcription.models import Dialogue, DialogueAnnotation, \
        Transcription, UserTurn
from transcription.dg_util import JsonDialogueUpload, update_gold, update_price
from transcription.db_fields import SizedTextField
from transcription.form_fields import LinkField


class DgAnnInline(admin.TabularInline):
    model = DialogueAnnotation
    extra = 0
    formfield_overrides = {
        SizedTextField: {'widget': forms.Textarea(attrs={'rows': '3'})}
    }


class TranscriptionInline(admin.TabularInline):
    model = Transcription
    extra = 0
    formfield_overrides = {
        SizedTextField: {'widget': forms.Textarea(attrs={'rows': '3'})},
        models.ForeignKey: {'form_class': LinkField}
    }


class UTurnInline(admin.TabularInline):
    model = UserTurn
    extra = 0


class DialogueAdmin(admin.ModelAdmin):
    add_form_template = 'er/import.html'
    list_display = ['dirname', 'cid', 'transcription_price', 'code',
                    'code_corr', 'code_incorr']
    formfield_overrides = {
        models.ForeignKey: {'form_class': LinkField}
    }
    inlines = [ DgAnnInline, UTurnInline ]

    def update_price_action(modeladmin, request, queryset):
        for dg in queryset:
            update_price(dg)
            dg.save()

    update_price_action.short_description = u"Update dialogue price"

    def update_gold_action(modeladmin, request, queryset):
        for dg in queryset:
            success, _ = update_gold(dg)
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
        models.ForeignKey: {'form_class': LinkField},
        SizedTextField: {'widget': forms.Textarea(attrs={'rows': '3'})}
    }
    inlines = [ TranscriptionInline ]

    date_hierarchy = 'date_saved'


class TranscriptionAdmin(admin.ModelAdmin):
    date_hierarchy = 'date_updated'
    fields = ('text', 'turn', 'dialogue_annotation', 'is_gold', 'breaks_gold')
    raw_id_fields = ('turn', 'dialogue_annotation')
    formfield_overrides = {
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
        models.ForeignKey: {'form_class': LinkField},
    }
    inlines = [ TranscriptionInline ]


admin.site.register(UserTurn, UserTurnAdmin)
admin.site.register(Dialogue, DialogueAdmin)
admin.site.register(DialogueAnnotation, DialogueAnnotationAdmin)
admin.site.register(Transcription, TranscriptionAdmin)
