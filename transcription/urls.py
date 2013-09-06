from django.conf.urls.defaults import patterns, url

import settings

pattern_args = ['',
                url('^transcribe$',
                    'transcription.views.transcribe',
                    name='transcribe'),

                url('^data/recs/(?P<path>.*)$',
                    'django.views.static.serve',
                    {'document_root': settings.CONVERSATION_DIR}),

                url('^finished$',
                    'transcription.views.finished',
                    name="finished"),

                url('^import$',
                    'transcription.views.import_dialogues',
                    name="import_dialogues"),

#                 url(r'^temp-test$',
#                     'transcription.views.temp_test',
#                     name="temp_test"),
               ]
if settings.USE_CF:
    cf_pattern_args = [url('^log-work$',
                           'transcription.views.log_work',
                           name="log_work"),
                       url('^create-job$',
                           'transcription.views.create_job_view',
                           name="create_job"),
                       url('^fire-hooks$',
                           'transcription.views.fire_hooks',
                           name="fire_hooks"),
                       ]
    pattern_args.extend(cf_pattern_args)
pattern_args.append(url(r'^',
                        'transcription.views.home',
                        name='home'))

urlpatterns = patterns(*pattern_args)
