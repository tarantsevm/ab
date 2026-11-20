"""Real engine smoke/latency probe; run only with AB_LT_JAR supplied."""
import os
import time
import unittest
from ab_proofread.engines.languagetool import LTClient, LTService

@unittest.skipUnless(os.environ.get('AB_LT_JAR'), 'requires real LanguageTool archive')
class RealEngineTests(unittest.TestCase):
    def test_russian_english_and_stop(self):
        service = LTService(os.environ['AB_LT_JAR'], port=18089)
        try:
            service.ensure_running()
            client = LTClient('http://127.0.0.1:18089', timeout=60)
            for language, text in [('ru-RU', 'Это ашибка в тексте. 😃')]:
                self.assertTrue(client.check(text, language))
                start=time.monotonic()
                self.assertTrue(client.check(text, language))
                print(language, 'warm seconds:', round(time.monotonic()-start,3))
            process=service.process
        finally:
            service.stop()
        self.assertIsNotNone(process.poll())
