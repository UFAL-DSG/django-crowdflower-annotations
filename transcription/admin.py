from django.contrib import admin
from django.forms.widgets import TextInput
from django.db import models
from transcription.models import Dialogue, DialogueAnnotation, Transcription, \
    UserTurn
from transcription.views import update_price


class DialogueAdmin(admin.ModelAdmin):
    add_form_template = 'er/import.html'
    list_display = ['dirname', 'cid', 'transcription_price', 'code', 'code_corr', 'code_incorr']

    def update_price_action(modeladmin, request, queryset):
        for dg in queryset:
            update_price(dg)
            dg.save()

    update_price_action.short_description = u"Update dialogue price"
    actions = [update_price_action]


class DialogueAnnotationAdmin(admin.ModelAdmin):
    exclude = ('program_version', )
    date_hierarchy = 'date_saved'


class TranscriptionAdmin(admin.ModelAdmin):
    date_hierarchy = 'date_updated'

    def toggle_gold(modeladmin, request, queryset):
        for trs in queryset:
            trs.is_gold = not trs.is_gold
            trs.save()

    toggle_gold.short_description = u"Toggle gold status"
    actions = [toggle_gold]


admin.site.register(Dialogue, DialogueAdmin)
admin.site.register(DialogueAnnotation, DialogueAnnotationAdmin)
admin.site.register(Transcription, TranscriptionAdmin)
