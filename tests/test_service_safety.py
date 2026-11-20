import socket
import unittest
from unittest.mock import patch
from pathlib import Path
from ab_proofread.engines.languagetool import LTService, LanguageToolError

class ServiceSafetyTests(unittest.TestCase):
    def test_occupied_port_does_not_spawn(self):
        with socket.socket() as server:
            server.bind(('127.0.0.1', 0))
            server.listen()
            port = server.getsockname()[1]
            with patch('ab_proofread.engines.languagetool.subprocess.Popen') as spawn:
                service = LTService(__file__, port=port)
                with self.assertRaises(LanguageToolError): service.ensure_running()
                spawn.assert_not_called()
    def test_shutdown_blocks_late_worker_start(self):
        service = LTService(__file__)
        service.stop()
        with patch('ab_proofread.engines.languagetool.subprocess.Popen') as spawn:
            with self.assertRaises(LanguageToolError): service.ensure_running()
            spawn.assert_not_called()
