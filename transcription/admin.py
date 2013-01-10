from django.contrib import admin
from django.db import models
from transcription.models import Dialogue, DialogueAnnotation, Transcription
from transcription.dg_util import update_price
from transcription.fields import LinkField

import dg_util
import settings


class DialogueAdmin(admin.ModelAdmin):
    add_form_template = 'er/import.html'
    list_display = ['dirname', 'cid', 'transcription_price', 'code',
                    'code_corr', 'code_incorr']
    formfield_overrides = {
        models.ForeignKey: {'form_class': LinkField}
    }

    def update_price_action(modeladmin, request, queryset):
        for dg in queryset:
            update_price(dg)
            dg.save()

    update_price_action.short_description = u"Update dialogue price"

    def upload_to_crowdflower(modeladmin, request, queryset):
        # TODO Ask CrowdFlower for list of current CIDs.
        # TODO Subtract the CIDs already uploaded from `queryset'.
        # Upload the rest of `queryset' to CrowdFlower.
        json_data = dg_util.JsonDialogueUpload()
        for dg in queryset:
            json_data.add(dg)
        json_data.upload()

    upload_to_crowdflower.short_description = \
            (u'Upload to CrowdFlower (only those dialogues that have not been '
             u'uploaded yet)')

    actions = [update_price_action, upload_to_crowdflower]


class DialogueAnnotationAdmin(admin.ModelAdmin):
    formfield_overrides = {
        models.ForeignKey: {'form_class': LinkField}
    }

    date_hierarchy = 'date_saved'


class TranscriptionAdmin(admin.ModelAdmin):
    date_hierarchy = 'date_updated'
    fields = ('text', 'turn', 'dialogue_annotation', 'is_gold', 'breaks_gold')
    raw_id_fields = ('turn', 'dialogue_annotation')
    formfield_overrides = {
        models.ForeignKey: {'form_class': LinkField}
    }

    def toggle_gold(modeladmin, request, queryset):
        for trs in queryset:
            trs.is_gold = not trs.is_gold
            trs.save()

    toggle_gold.short_description = u"Toggle gold status"
    actions = [toggle_gold]


admin.site.register(Dialogue, DialogueAdmin)
admin.site.register(DialogueAnnotation, DialogueAnnotationAdmin)
admin.site.register(Transcription, TranscriptionAdmin)

