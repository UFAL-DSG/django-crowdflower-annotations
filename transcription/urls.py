from django.conf.urls.defaults import patterns, url

import settings

urlpatterns = patterns('',
                       url(r'^transcribe$',
                           'transcription.views.transcribe',
                           name='transcribe'),

                       url(r'^data/recs/(?P<path>.*)$',
                           'django.views.static.serve',
                           {'document_root': settings.CONVERSATION_DIR}),

                       url(r'^finished$',
                           'transcription.views.finished',
                           name="finished"),

                       url(r'^import$',
                           'transcription.views.import_dialogues',
                           name="import_dialogues"),

                       url(r'^export$',
                           'transcription.views.rating_export',
                           name="rating_export"),

                       url(r'^',
                           'transcription.views.home',
                           name='home')
              )
