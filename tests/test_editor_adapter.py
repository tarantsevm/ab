import unittest
from unittest.mock import Mock


class EditorAdapterTests(unittest.TestCase):
    def test_session_adapter_never_sends_selection_to_unrelated_process(self):
        from ab_proofread.integration.editor_adapter import EditorAdapter
        bus = Mock()
        adapter = EditorAdapter(bus, Mock())
        adapter._call = Mock(side_effect=[(':1.7',), (4321,)])
        self.assertIsNone(adapter.prepare(1234, 2, 8, 'ашибка'))
        self.assertEqual(adapter._call.call_count, 2)

    def test_expired_offer_sends_no_request(self):
        from ab_proofread.integration.editor_adapter import EditorAdapter, Offer
        adapter = EditorAdapter(None, None)
        adapter._call = Mock()
        self.assertIs(adapter.replace(Offer(':1.42', 'token', 0), 'fixed'), False)
        adapter._call.assert_not_called()

    def test_lost_reply_is_not_a_refusal_and_is_not_retried(self):
        from gi.repository import GLib
        from ab_proofread.integration.editor_adapter import EditorAdapter, Offer
        adapter = EditorAdapter(None, None)
        adapter._call = Mock(side_effect=GLib.Error('reply timed out'))
        self.assertIsNone(adapter.replace(Offer(':1.42', 'token', 10**30), 'fixed'))
        adapter._call.assert_called_once()
