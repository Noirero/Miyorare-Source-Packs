import json
import tempfile
import unittest
from pathlib import Path

from tools.validate_audio_runtime_contract import RuntimeContractError, validate


IDS = {
    "miyorare.audio.asmr_one": ("asmr_one_audio_extension.dart", "ASMR.one", "optional", ["catalog", "search", "detail", "playback", "download", "subtitles"]),
    "miyorare.audio.hentai_asmr": ("hentai_asmr_audio_extension.dart", "HentaiASMR", "none", ["catalog", "search", "detail", "playback", "download"]),
    "miyorare.audio.japanese_asmr": ("japanese_asmr_audio_extension.dart", "JapaneseASMR", "none", ["catalog", "search", "detail", "playback", "download"]),
    "miyorare.audio.asmr18": ("asmr18_audio_extension.dart", "ASMR+18", "none", ["catalog", "search", "detail", "playback"]),
    "miyorare.audio.ero_voice": ("ero_voice_audio_extension.dart", "EroVoice", "none", ["catalog", "search", "detail", "download"]),
    "miyorare.audio.asmr_hentai_net": ("asmr_hentai_net_audio_extension.dart", "ASMR Hentai", "none", ["catalog", "search", "detail", "playback", "subtitles"]),
}


def write_fixture(root: Path, *, mutate_catalog=None) -> tuple[Path, Path]:
    ext_root = root / "hiraukan" / "lib" / "src" / "extensions"
    ext_root.mkdir(parents=True)
    catalog = {"extensions": []}
    for extension_id, (filename, name, auth, caps) in IDS.items():
        cap_lines = "\n".join(f"          AudioExtensionCapability.{cap}," for cap in caps)
        (ext_root / filename).write_text(
            "AudioExtensionManifest(\n"
            f"  id: '{extension_id}',\n"
            f"  name: '{name}',\n"
            "  version: '1.0.0',\n"
            f"  auth: AudioExtensionAuthRequirement.{auth},\n"
            "  capabilities: {\n"
            f"{cap_lines}\n"
            "  },\n"
            "  languages: ['ja'],\n"
            ");\n",
            encoding="utf-8",
        )
        catalog["extensions"].append(
            {
                "id": extension_id,
                "name": name,
                "version": "1.0.0",
                "auth": auth,
                "capabilities": list(caps),
                "languages": ["ja"],
                "delivery": {"kind": "builtin", "runtimeId": extension_id},
            }
        )
    if mutate_catalog is not None:
        mutate_catalog(catalog)
    catalog_path = root / "pack.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    return catalog_path, root / "hiraukan"


class AudioRuntimeContractTests(unittest.TestCase):
    def test_exact_contract_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            catalog, hiraukan = write_fixture(Path(tmp))
            result = validate(catalog, hiraukan)
            self.assertEqual(6, result["runtimeCount"])

    def test_capability_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            def mutate(data):
                data["extensions"][0]["capabilities"].remove("subtitles")
            catalog, hiraukan = write_fixture(Path(tmp), mutate_catalog=mutate)
            with self.assertRaises(RuntimeContractError):
                validate(catalog, hiraukan)

    def test_external_delivery_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            def mutate(data):
                data["extensions"][0]["delivery"]["kind"] = "download"
            catalog, hiraukan = write_fixture(Path(tmp), mutate_catalog=mutate)
            with self.assertRaises(RuntimeContractError):
                validate(catalog, hiraukan)

    def test_missing_runtime_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            def mutate(data):
                data["extensions"].pop()
            catalog, hiraukan = write_fixture(Path(tmp), mutate_catalog=mutate)
            with self.assertRaises(RuntimeContractError):
                validate(catalog, hiraukan)


if __name__ == "__main__":
    unittest.main()
