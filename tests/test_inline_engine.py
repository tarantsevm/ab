import unittest
from unittest.mock import Mock
from ab_proofread.integration.inline_engine import InlineEngine


class InlineTests(unittest.TestCase):
    def test_clean_result_is_distinct_from_unresolved_findings(self):
        from ab_proofread.core import Suggestion
        client = Mock()
        engine = InlineEngine(client=client)
        client.check.return_value = []
        self.assertIs(engine.review('Это тест.', 'ru-RU')['findings'], False)
        client.check.return_value = [Suggestion(0, 3, '', (), 'GRAMMAR')]
        result = engine.review('Это тест.', 'ru-RU')
        self.assertIs(result['findings'], True)
        self.assertEqual(result['changes'], 0)
    def test_start_does_not_check_unrelated_phrases(self):
        service, client = Mock(), Mock()
        engine = InlineEngine(client=client, service=service)
        engine.start()
        service.ensure_running.assert_called_once_with()
        client.check.assert_not_called()

    def test_russian_warmup_is_fixed_bounded_and_once(self):
        service, client = Mock(), Mock()
        engine = InlineEngine(client=client, service=service)
        engine.warm_russian()
        engine.warm_russian()
        service.ensure_running.assert_called_once_with()
        client.check.assert_called_once_with("Это проверочная фраза.", "ru-RU")

    def test_concurrent_warm_request_is_not_queued_twice(self):
        import threading
        entered, release = threading.Event(), threading.Event()
        calls = []
        class Client:
            def check(self, text, language):
                calls.append((text, language))
                entered.set()
                release.wait(1)
        engine = InlineEngine(client=Client())
        first = threading.Thread(target=engine.warm_russian)
        first.start()
        self.assertTrue(entered.wait(1))
        engine.warm_russian()
        release.set()
        first.join(1)
        self.assertFalse(first.is_alive())
        self.assertEqual(calls, [("Это проверочная фраза.", "ru-RU")])

    def test_mixed_selection_reviews_russian_only_and_preserves_exact_offsets(self):
        from ab_proofread.core import Suggestion
        source = 'Title 🙂\nЭто ашибка.\r\nEnglish recieved line.\nКонец'
        calls = []

        class Client:
            def check(self, text, language):
                calls.append((text, language))
                if language != 'ru-RU':
                    raise AssertionError('English line must not be submitted')
                if 'ашибка' in text:
                    start = text.index('ашибка')
                    return [Suggestion(start, start + len('ашибка'), '', ('ошибка',), 'MORFOLOGIK_RULE_RU_RU')]
                return []

        result = InlineEngine(client=Client()).review(source, 'ru-RU')
        self.assertEqual(result['text'], 'Title 🙂\nЭто ошибка.\r\nEnglish recieved line.\nКонец')
        self.assertEqual([p['text'] for p in result['parts'] if p['changed']], ['ошибка'])
        self.assertEqual(calls, [('Это ашибка.\r\n', 'ru-RU'), ('Конец', 'ru-RU')])

    def test_ranked_spelling_candidate_is_previewed(self):
        from ab_proofread.core import Suggestion
        class Client:
            def check(self, text, language):
                return [Suggestion(0, 6, '', ('ошибка', 'ошибку'), 'MORFOLOGIK_RULE_RU_RU')]
        result = InlineEngine(client=Client()).review('ашибка', 'ru-RU')
        self.assertEqual(result['text'], 'ошибка')
        self.assertEqual(result['changes'], 1)

    def test_review_json_has_changed_parts_and_result(self):
        from ab_proofread.core import Suggestion
        engine=InlineEngine(client=type("C",(),{"check":lambda self,t,l:[Suggestion(0,3,"",("The",),"x")]})())
        result=engine.review("teh", "en-US")
        self.assertEqual(result["text"], "teh")
        self.assertEqual(result["changes"], 0)
        self.assertEqual(result["parts"], [{"text": "teh", "changed": False}])
