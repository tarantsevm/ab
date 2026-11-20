import unittest
from unittest.mock import patch

from ab_proofread.engines.languagetool import LTClient, LTService, LanguageToolError


class EngineTests(unittest.TestCase):
    def test_loopback_endpoint_and_post_protocol(self):
        client = LTClient(timeout=1)
        with patch.object(client._opener, "open") as open_url:
            class Response:
                status = 200
                def __enter__(self): return self
                def __exit__(self, *args): return False
                def read(self, n=-1): return b'{"matches": []}'
            open_url.return_value = Response()
            self.assertEqual(client.check("hello", "en-US"), [])
            req = open_url.call_args.args[0]
            self.assertEqual(req.full_url, "http://127.0.0.1:18081/v2/check")
            self.assertEqual(req.method, "POST")

    def test_reject_non_loopback_service_url(self):
        with self.assertRaises(ValueError):
            LTClient(base_url="http://example.com:18081")

    def test_reject_redirects(self):
        client = LTClient()
        with patch.object(client._opener, "open", side_effect=Exception("redirect")):
            with self.assertRaises(LanguageToolError):
                client.check("hello", "en-US")

    def test_service_jar_validation(self):
        with self.assertRaises((ValueError, FileNotFoundError)):
            LTService("/not/a/real/languagetool.jar")


if __name__ == "__main__":
    unittest.main()
