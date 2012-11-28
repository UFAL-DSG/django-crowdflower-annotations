from django.conf.urls.defaults import patterns, include, url

import settings

urlpatterns = patterns('',
    url(r'^transcribe$',
        'transcription.views.transcribe',
        name='transcribe'),

    url(r'^data/recs/(?P<path>.*)$',
        'django.views.static.serve',
        {'document_root': settings.CONVERSATION_DIR,}),

    url(r'^finished$',
        'transcription.views.finished',
        name="rating_finished"),

    url(r'^overview_dialogs$',
        'transcription.views.rating_overview_dialog',
        name="rating_overview_dialog"),

    url(r'^overview$',
        'transcription.views.rating_overview',
        name="rating_overview"),

    url(r'^export$',
        'transcription.views.rating_export',
        name="rating_export"),

    url(r'^',
        'transcription.views.home',
        name='home'),
)
