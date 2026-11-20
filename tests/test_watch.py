import unittest
import json
from types import SimpleNamespace
from unittest.mock import Mock

from ab_proofread.integration import watch


class WatchTests(unittest.TestCase):
    def test_caret_event_rechecks_selection_when_editor_omits_selection_event(self):
        watcher = watch.SelectionWatcher(Mock(), watch.Protocol(Mock()))
        self.addCleanup(watcher.executor.shutdown)
        watcher.refresh = Mock()
        event = SimpleNamespace(type='object:text-caret-moved', source=Mock())
        watcher.on_event(event)
        watcher.refresh.assert_called_once_with(event)

    def test_click_does_not_run_synthetic_warmup_before_check(self):
        target = Mock()
        atspi = SimpleNamespace(StateType=SimpleNamespace(FOCUSED=1), Text=Mock())
        atspi.Text.get_text.return_value = 'Это ошибка'
        engine = Mock()
        engine.warm_russian = Mock()
        engine.review.return_value = {'review': 'result'}
        watcher = watch.SelectionWatcher(atspi, watch.Protocol(Mock()), engine=engine)
        atspi.EventListener = Mock()
        watcher.register()
        self.addCleanup(watcher.close)
        watcher.source, watcher.start, watcher.end, watcher.focused = target, 0, 2, True
        watcher._read_selection = Mock(return_value=(target, 0, 10))
        watcher.check_clicked()
        self.assertTrue(watcher.pending)
        watcher.pending.result(timeout=1)
        engine.review.assert_called_once_with('Это ошибка', 'ru-RU')
        engine.warm_russian.assert_not_called()

    def test_click_reads_final_drag_range_from_same_focused_object(self):
        target = Mock()
        atspi = SimpleNamespace(StateType=SimpleNamespace(FOCUSED=1), Text=Mock())
        atspi.Text.get_text.return_value = 'ашибка!'
        engine = Mock()
        engine.warm_russian = Mock()
        engine.review.return_value = {'review': 'result'}
        watcher = watch.SelectionWatcher(atspi, watch.Protocol(Mock()), engine=engine)
        atspi.EventListener = Mock()
        watcher.register()
        self.addCleanup(watcher.close)
        watcher.source, watcher.start, watcher.end, watcher.focused = target, 0, 2, True
        watcher._read_selection = Mock(return_value=(target, 0, 7))
        self.assertTrue(watcher.check_clicked())
        watcher.pending.result(timeout=1)
        atspi.Text.get_text.assert_called_once_with(target, 0, 7)
        engine.review.assert_called_once_with('ашибка!', 'ru-RU')

    def test_latin_selection_is_not_checked_or_praised(self):
        target = Mock()
        engine, adapter = Mock(), Mock()
        atspi = SimpleNamespace(StateType=SimpleNamespace(FOCUSED=1), Text=Mock())
        atspi.Text.get_text.return_value = 'speling'
        emitted = []
        watcher = watch.SelectionWatcher(atspi, watch.Protocol(emitted.append), engine=engine, adapter=adapter)
        self.addCleanup(watcher.executor.shutdown)
        watcher.source, watcher.start, watcher.end, watcher.focused = target, 0, 7, True
        watcher._read_selection = Mock(return_value=(target, 0, 7))
        watcher.check_clicked()
        self.assertEqual(json.loads(emitted[-1]), {'review': 'unsupported'})
        engine.review.assert_not_called()
        adapter.prepare.assert_not_called()

    def test_matching_native_offer_applies_only_one_engine_proposal(self):
        target = Mock()
        target.get_process_id.return_value = 123
        atspi = SimpleNamespace(StateType=SimpleNamespace(FOCUSED=1), Text=Mock())
        atspi.Text.get_text.return_value = 'ашибка!'
        engine = Mock()
        engine.warm_russian = Mock()
        engine.review.return_value = {'review': 'result', 'changes': 1, 'text': 'spelling'}
        adapter = Mock()
        adapter.prepare.return_value = SimpleNamespace(expires=10**30)
        emitted = []
        watcher = watch.SelectionWatcher(atspi, watch.Protocol(emitted.append), engine=engine, adapter=adapter)
        self.addCleanup(watcher.executor.shutdown)
        watcher.source, watcher.start, watcher.end, watcher.focused = target, 2, 9, True
        watcher._read_selection = Mock(return_value=(target, 2, 9))
        watcher._focused_source = Mock(return_value=target)
        self.assertTrue(watcher.check_clicked())
        watcher.pending.result(timeout=2)
        offer_id = json.loads(emitted[-1])['replace']
        self.assertFalse(watcher.replace_clicked('wrong'))
        adapter.replace.assert_not_called()
        watcher.replace_clicked(offer_id)
        watcher.replace_clicked(offer_id)
        adapter.replace.assert_called_once_with(adapter.prepare.return_value, 'spelling')

    def test_unknown_replace_outcome_is_reported_once_for_consumed_id(self):
        emitted = []
        adapter = Mock()
        adapter.replace.return_value = None
        watcher = watch.SelectionWatcher(Mock(), watch.Protocol(emitted.append), adapter=adapter)
        self.addCleanup(watcher.executor.shutdown)
        target, offer, proposal_id = Mock(), Mock(), '1' * 32
        watcher.proposal = (proposal_id, offer, 'fixed', target, 0, 4, 0)
        watcher._live_range = Mock(return_value=True)
        watcher.replace_clicked(proposal_id)
        watcher.replace_clicked(proposal_id)
        adapter.replace.assert_called_once_with(offer, 'fixed')
        self.assertIn({'replacement': 'unknown', 'id': proposal_id}, map(json.loads, emitted))

    def test_denies_common_protected_application_names(self):
        for name in ("GNOME Terminal", "Visual Studio Code", "ab_proofread"):
            assert watch._blocked_application(name)
        assert not watch._blocked_application("Firefox")


    def test_protocol_accepts_only_check_click_and_emits_line_json(self):
        output = []
        protocol = watch.Protocol(output.append)
        assert protocol.handle_line('{"check": true}\n')
        assert not protocol.handle_line('{"selection": true}\n')
        protocol.emit_selection(True)
        assert json.loads(output[0]) == {"selection": True}


    def test_emit_does_not_repeat_same_selection_state(self):
        output = []
        protocol = watch.Protocol(output.append)
        protocol.emit_selection(True)
        protocol.emit_selection(True)
        protocol.emit_selection(False)
        assert [json.loads(item) for item in output] == [
            {"selection": True}, {"selection": False}
        ]
