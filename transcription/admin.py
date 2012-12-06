from django.contrib import admin
from django.forms.widgets import TextInput
from django.db import models
from transcription.models import Dialogue, Transcription


# class AnswerInline(admin.TabularInline):
#     model = Answer
#     formfield_overrides = {
#         models.TextField:
#         {
#             'widget': TextInput,
#         }
#     }


# class QuestionAdmin(admin.ModelAdmin):
#     list_display = ('id', 'id_text', 'text',)
#     inlines = [
#         AnswerInline,
#         ]

class DialogueAdmin(admin.ModelAdmin):
    add_form_template = 'er/import.html'
    list_display = ['dirname', 'cid', 'code', 'code_corr', 'code_incorr']


class TranscriptionAdmin(admin.ModelAdmin):
    date_hierarchy = 'date_saved'
    exclude = ('program_version', )

    def toggle_gold(modeladmin, request, queryset):
        for trs in queryset:
            trs.is_gold = not trs.is_gold
            trs.save()

    toggle_gold.short_description = u"Toggle gold status"
    actions = [toggle_gold]


# admin.site.register(Question, QuestionAdmin)
admin.site.register(Dialogue, DialogueAdmin)
admin.site.register(Transcription, TranscriptionAdmin)
