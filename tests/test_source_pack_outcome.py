import importlib.util
from pathlib import Path


SPEC = importlib.util.spec_from_file_location(
    "source_pack_outcome",
    Path(__file__).parents[1] / "tools" / "source_pack_outcome.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def status(*states: str) -> dict:
    return {
        "schema": 2,
        "providers": {
            f"provider-{index}": {"state": state}
            for index, state in enumerate(states)
        },
    }


def test_all_safe_is_pass():
    result = MODULE.classify(status("synced", "promoted"))
    assert result["outcome"] == "PASS"
    assert result["activeSetSafe"] is True


def test_candidate_hold_keeps_active_set_safe():
    result = MODULE.classify(status("synced", "held"))
    assert result["outcome"] == "HELD"
    assert result["activeSetSafe"] is True
    assert result["heldProviders"] == ["provider-1"]


def test_active_broken_is_fail():
    result = MODULE.classify(status("synced", "broken"))
    assert result["outcome"] == "FAIL"
    assert result["activeSetSafe"] is False


def test_unknown_or_invalid_state_fails_closed():
    assert MODULE.classify(status("mystery"))["outcome"] == "FAIL"
    assert MODULE.classify({"schema": 99, "providers": {}})["outcome"] == "FAIL"
