import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "source_runtime",
    Path(__file__).resolve().parents[1] / "tools" / "source_runtime.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

A = "a" * 40
B = "b" * 40


class SourceRuntimeTests(unittest.TestCase):
    def test_inventory_links_canonical_source_across_providers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            uma = root / "uma"
            gek = root / "gek"
            kei = root / "kei"
            (uma / "src/main/kotlin/tsuki/site/id").mkdir(parents=True)
            (gek / "src/main/kotlin/tsuki/site/all").mkdir(parents=True)
            (kei / "src/id/kiryuu").mkdir(parents=True)
            (uma / "src/main/kotlin/tsuki/site/id/Kiryuu.kt").write_text(
                '@MangaSourceParser("KIRYUU", "Kiryuu", "id")\n'
                'class Kiryuu: Parser("v7.kiryuu.to")\n',
                encoding="utf-8",
            )
            (gek / "src/main/kotlin/tsuki/site/all/Gelbooru.kt").write_text(
                '@MangaSourceParser("GELBOORU", "Gelbooru")\n'
                'val base = "https://gelbooru.com"\n',
                encoding="utf-8",
            )
            (kei / "src/id/kiryuu/build.gradle.kts").write_text(
                'baseUrl = "https://v7.kiryuu.to"\n', encoding="utf-8"
            )
            packs = {
                "packs": {
                    "id": {"sources": ["Kiryuu.kt"]},
                    "en": {"sources": []},
                    "global": {"gekkoushiSources": ["GELBOORU"]},
                }
            }
            aliases = {
                "aliases": [{
                    "canonicalId": "miyorare:miyorare-id:KIRYUU",
                    "verifiedDomain": "v7.kiryuu.to",
                    "official": {"pack": "id", "sourceName": "KIRYUU"},
                    "uma": {"file": "src/main/kotlin/tsuki/site/id/Kiryuu.kt"},
                    "keiyoushi": {"module": "src/id/kiryuu"},
                }]
            }
            (root / "packs.json").write_text(json.dumps(packs), encoding="utf-8")
            (root / "aliases.json").write_text(json.dumps(aliases), encoding="utf-8")

            inventory = MODULE.discover_inventory(
                root / "packs.json", root / "aliases.json", uma, gek, kei
            )
            by_key = {item["sourceKey"]: item for item in inventory}
            self.assertEqual(
                "miyorare:miyorare-id:KIRYUU",
                by_key["uma:id:KIRYUU"]["canonicalId"],
            )
            self.assertEqual(
                "miyorare:miyorare-id:KIRYUU",
                by_key["keiyoushi:id:KIRYUU"]["canonicalId"],
            )
            self.assertEqual("gelbooru.com", by_key["gekkoushi:global:GELBOORU"]["probeHost"])

    def test_one_broken_source_does_not_mark_whole_provider_broken(self):
        state = {
            "schema": 1,
            "sources": {
                "uma:id:A": {"provider": "uma", "runtimeHealth": "BROKEN"},
                "uma:id:B": {"provider": "uma", "runtimeHealth": "HEALTHY"},
            },
        }
        summary = MODULE.provider_summary(state)["providers"]["uma"]
        self.assertEqual("DEGRADED", summary["runtimeHealth"])

    def test_repeated_hard_failure_required_before_broken(self):
        entry = {
            "activeCommit": A,
            "runtimeHealth": "UNKNOWN",
            "consecutiveFailures": 0,
            "healthyHistory": [A],
        }
        failure = {"reachable": False, "detail": "timeout"}
        MODULE.apply_probe_result(entry, failure, 3)
        self.assertEqual("DEGRADED", entry["runtimeHealth"])
        MODULE.apply_probe_result(entry, failure, 3)
        self.assertEqual("DEGRADED", entry["runtimeHealth"])
        MODULE.apply_probe_result(entry, failure, 3)
        self.assertEqual("BROKEN", entry["runtimeHealth"])

    def test_http_403_is_reachable_not_broken(self):
        error = __import__("urllib.error").error.HTTPError(
            "https://example.com/", 403, "Forbidden", {}, None
        )
        with patch("urllib.request.urlopen", side_effect=error):
            result = MODULE.http_probe("example.com", timeout=1)
        self.assertTrue(result["reachable"])
        self.assertEqual(403, result["httpStatus"])

    def test_broken_source_prefers_latest_candidate_then_fallbacks(self):
        state = {
            "schema": 1,
            "sources": {
                "uma:id:KIRYUU": {
                    "sourceKey": "uma:id:KIRYUU",
                    "provider": "uma",
                    "canonicalId": "miyorare:miyorare-id:KIRYUU",
                    "runtimeHealth": "BROKEN",
                    "activeCommit": A,
                    "healthyHistory": [A],
                },
                "keiyoushi:id:KIRYUU": {
                    "sourceKey": "keiyoushi:id:KIRYUU",
                    "provider": "keiyoushi",
                    "canonicalId": "miyorare:miyorare-id:KIRYUU",
                    "runtimeHealth": "HEALTHY",
                    "activeCommit": A,
                    "healthyHistory": [A],
                },
            },
        }
        status = {
            "providers": {
                "uma": {"candidate": B, "activeCommit": A},
                "keiyoushi": {"activeCommit": A},
            }
        }
        attempts = MODULE.recovery_attempts(state["sources"]["uma:id:KIRYUU"], status, state)
        self.assertEqual("ADAPT_LATEST", attempts[0]["action"])
        self.assertTrue(any(item["action"] == "TRY_CANONICAL_FALLBACK" for item in attempts))

    def test_dispatch_token_prevents_repeating_same_recovery_request(self):
        source = {
            "sourceKey": "uma:id:A",
            "provider": "uma",
            "canonicalId": None,
            "runtimeHealth": "BROKEN",
            "activeCommit": A,
            "healthyHistory": [A],
        }
        state = {"schema": 1, "sources": {source["sourceKey"]: source}}
        status = {"providers": {"uma": {"candidate": B}}}
        queue = MODULE.build_recovery_queue(state, status)
        self.assertTrue(queue["queue"][0]["dispatchNeeded"])
        MODULE.acknowledge_dispatch(state, queue)
        queue2 = MODULE.build_recovery_queue(state, status)
        self.assertFalse(queue2["queue"][0]["dispatchNeeded"])


if __name__ == "__main__":
    unittest.main()
