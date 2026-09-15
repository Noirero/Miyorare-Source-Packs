import tempfile
import unittest
from pathlib import Path

from tools.repair_engine import RepairError, apply_recipe


RECIPES = {
    "recipes": [
        {
            "id": "forward-parser-request-headers-to-http-get",
            "providers": ["gekkoushi"],
            "operation": "append-http-get-header-argument",
            "argument": "getRequestHeaders()",
            "requiresTokens": ["getRequestHeaders()", "webClient.httpGet("],
            "safety": {
                "minChanges": 1,
                "maxChanges": 20,
                "idempotent": True,
                "failClosed": True,
            },
        }
    ]
}


class RepairEngineTest(unittest.TestCase):
    def source_file(self, content: str):
        tmp = tempfile.TemporaryDirectory()
        path = Path(tmp.name) / "Source.kt"
        path.write_text(content, encoding="utf-8")
        return tmp, path

    def test_forwards_headers_without_rewriting_existing_explicit_headers(self):
        tmp, path = self.source_file(
            '''
            override fun getRequestHeaders() = Headers.Builder().build()
            val a = webClient.httpGet(url)
            val b = webClient.httpGet("https://api.test/detail/${manga.url}")
            val c = webClient.httpGet(other, getRequestHeaders())
            '''
        )
        self.addCleanup(tmp.cleanup)
        report = apply_recipe(
            RECIPES,
            "forward-parser-request-headers-to-http-get",
            "gekkoushi",
            "miyorare:test",
            path,
        )
        text = path.read_text(encoding="utf-8")
        self.assertEqual("APPLIED", report["status"])
        self.assertEqual(2, report["changes"])
        self.assertEqual(1, report["alreadyAppliedCalls"])
        self.assertIn("webClient.httpGet(url, getRequestHeaders())", text)
        self.assertIn('webClient.httpGet("https://api.test/detail/${manga.url}", getRequestHeaders())', text)
        self.assertEqual(3, text.count("getRequestHeaders())"))

    def test_second_application_is_idempotent(self):
        tmp, path = self.source_file(
            "override fun getRequestHeaders() = x\nval a = webClient.httpGet(url)\n"
        )
        self.addCleanup(tmp.cleanup)
        apply_recipe(RECIPES, "forward-parser-request-headers-to-http-get", "gekkoushi", "miyorare:test", path)
        first = path.read_text(encoding="utf-8")
        report = apply_recipe(RECIPES, "forward-parser-request-headers-to-http-get", "gekkoushi", "miyorare:test", path)
        self.assertEqual("ALREADY_APPLIED", report["status"])
        self.assertEqual(first, path.read_text(encoding="utf-8"))

    def test_missing_precondition_fails_closed(self):
        tmp, path = self.source_file("val a = webClient.httpGet(url)\n")
        self.addCleanup(tmp.cleanup)
        with self.assertRaises(RepairError):
            apply_recipe(RECIPES, "forward-parser-request-headers-to-http-get", "gekkoushi", "miyorare:test", path)

    def test_provider_mismatch_is_rejected(self):
        tmp, path = self.source_file(
            "override fun getRequestHeaders() = x\nval a = webClient.httpGet(url)\n"
        )
        self.addCleanup(tmp.cleanup)
        with self.assertRaises(RepairError):
            apply_recipe(RECIPES, "forward-parser-request-headers-to-http-get", "keiyoushi", "miyorare:test", path)


if __name__ == "__main__":
    unittest.main()
