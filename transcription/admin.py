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


# admin.site.register(Question, QuestionAdmin)
admin.site.register(Dialogue)
admin.site.register(Transcription)
