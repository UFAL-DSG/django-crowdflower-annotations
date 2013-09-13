from django.conf.urls.defaults import patterns, url

import settings
from crowdflower import price_class_handler

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

                url(r'^test-view$',
                    'transcription.views.temp_test',
                    name="test_view"),
               ]

# Only when using Crowdflower:
if settings.USE_CF:
    cf_pattern_args = [url('^log-work$',
                           'transcription.views.log_work',
                           name="log_work"),
                       url('^fire-hooks$',
                           'transcription.views.fire_hooks',
                           name="fire_hooks"),
                       url('^finalize-job$',
                           'transcription.views.finalize_job',
                           name="finalize_job"),
                       ]

    # Only when tracking Crowdflower job IDs using a job IDs file:
    if price_class_handler.uses_jobfile:
        cf_pattern_args.extend([
            url('^create-jobs$',
                'transcription.views.create_job_view',
                name="create_jobs"),
            url('^delete-jobs$',
                'transcription.views.delete_job_view',
                name="delete_jobs"),
            ])
    pattern_args.extend(cf_pattern_args)
pattern_args.append(url(r'^',
                        'transcription.views.home',
                        name='home'))

urlpatterns = patterns(*pattern_args)
