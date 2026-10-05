"""Three ordinary-button presets; voice and hardware settings stay shared."""
import copy
import importlib
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ovb_rc003 import config, remote_settings


class ButtonPresetTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("ovb_rc003.button_presets"),
                             "ordinary-button presets are not implemented")
        self.presets = importlib.import_module("ovb_rc003.button_presets")
        self.original = config.default_key_bindings()
        self.original["bindings"]["home"] = {"kind": "key_combo", "keys": ["ctrl", "a"]}
        self.original["secondary_bindings"]["home"] = {
            "double_click": {"kind": "key_combo", "keys": ["ctrl", "b"]}}
        self.original["display_notes"] = {"home": {"single_click": "Select all"}}
        self.original["physical_bindings"] = {"example": "home"}

    def test_initial_slots_copy_current_settings_without_mutating_input(self):
        before = copy.deepcopy(self.original)
        doc = self.presets.ensure(self.original)
        store = doc[self.presets.STORE]
        self.assertEqual(store["active"], 0)
        self.assertEqual([p["name"] for p in store["slots"]], ["预设 1", "预设 2", "预设 3"])
        self.assertEqual(self.original, before)
        for slot in store["slots"]:
            self.assertEqual(slot["bindings"]["home"], before["bindings"]["home"])
            self.assertNotIn("mic", slot["bindings"])
            self.assertNotIn("physical_bindings", slot)
        store["slots"][0]["bindings"]["home"]["keys"] = ["ctrl", "z"]
        self.assertEqual(store["slots"][1]["bindings"]["home"]["keys"], ["ctrl", "a"])

    def test_switch_isolates_all_ordinary_gestures_but_shares_mic_and_hardware(self):
        doc = self.presets.ensure(self.original)
        doc["bindings"]["home"]["keys"] = ["ctrl", "z"]
        doc["secondary_bindings"] = {}
        doc["display_notes"] = {}
        doc["bindings"]["mic"] = {"kind": "disabled"}
        doc["secondary_bindings"]["mic"] = {"double_click": {"kind": "disabled"}}
        doc["display_notes"]["mic"] = {"single_click": "Shared mic"}
        next_doc = self.presets.switch(doc, 1)
        self.assertEqual(next_doc["bindings"]["home"]["keys"], ["ctrl", "a"])
        self.assertIn("home", next_doc["secondary_bindings"])
        self.assertEqual(next_doc["bindings"]["mic"], doc["bindings"]["mic"])
        self.assertEqual(next_doc["secondary_bindings"]["mic"], doc["secondary_bindings"]["mic"])
        self.assertEqual(next_doc["display_notes"]["mic"], doc["display_notes"]["mic"])
        self.assertEqual(next_doc["physical_bindings"], doc["physical_bindings"])
        self.assertEqual(next_doc["combo_bindings"], doc["combo_bindings"])
        restored = self.presets.switch(next_doc, 0)
        self.assertEqual(restored["bindings"]["home"]["keys"], ["ctrl", "z"])
        self.assertNotIn("home", restored["secondary_bindings"])
        self.assertNotIn("home", restored["display_notes"])

    def test_copy_and_rename_keep_names_and_independent_data(self):
        doc = self.presets.rename(self.original, 1, "  办公  ")
        doc["bindings"]["home"]["keys"] = ["ctrl", "z"]
        doc = self.presets.copy_slot(doc, 0, 1)
        doc = self.presets.switch(doc, 1)
        self.assertEqual(doc[self.presets.STORE]["slots"][1]["name"], "办公")
        self.assertEqual(doc["bindings"]["home"]["keys"], ["ctrl", "z"])
        doc["bindings"]["home"]["keys"] = ["ctrl", "x"]
        self.assertEqual(self.presets.switch(doc, 0)["bindings"]["home"]["keys"], ["ctrl", "z"])

    def test_copy_into_active_slot_updates_live_view(self):
        doc = self.presets.ensure(self.original)
        doc["bindings"]["home"]["keys"] = ["ctrl", "z"]
        doc = self.presets.copy_slot(doc, 1, 0)
        self.assertEqual(doc["bindings"]["home"]["keys"], ["ctrl", "a"])

    def test_invalid_names_indices_and_corrupt_stores_fail_closed(self):
        for name in ("", " ", "x" * 25, "bad\nname"):
            with self.assertRaises(ValueError):
                self.presets.rename(self.original, 0, name)
        for index in (-1, 3, True, "1"):
            with self.assertRaises(ValueError):
                self.presets.switch(self.original, index)
        doc = self.presets.ensure(self.original)
        doc[self.presets.STORE]["slots"].pop()
        with self.assertRaises(ValueError):
            self.presets.ensure(doc)

    def test_disk_roundtrip_preserves_selected_slot_and_does_not_touch_voice_config(self):
        with tempfile.TemporaryDirectory() as root:
            cp, bp = config.config_path(Path(root)), config.key_bindings_path(Path(root))
            config.save_config(cp, config.default_config())
            original_config = cp.read_bytes()
            doc = self.presets.ensure(config.default_key_bindings())
            doc["bindings"]["home"] = {"kind": "key_combo", "keys": ["ctrl", "z"]}
            config.save_key_bindings(bp, doc)
            doc = self.presets.switch(config.load_key_bindings(bp), 2)
            config.save_key_bindings(bp, doc)
            loaded = config.load_key_bindings(bp)
            self.assertEqual(loaded[self.presets.STORE]["active"], 2)
            self.assertEqual(self.presets.switch(loaded, 0)["bindings"]["home"]["keys"], ["ctrl", "z"])
            self.assertEqual(cp.read_bytes(), original_config)
            previous = bp.read_bytes()
            with mock.patch.object(config.os, "replace", side_effect=PermissionError("locked")):
                with self.assertRaises(PermissionError):
                    config.save_key_bindings(bp, self.presets.switch(loaded, 1))
            self.assertEqual(bp.read_bytes(), previous)

    def test_existing_device_projection_retains_presets_without_leaking_them(self):
        doc = self.presets.ensure(self.original)
        self.assertIn(self.presets.STORE, remote_settings.BINDING_FIELDS)
        doc[remote_settings.STORE] = {"schema": 1, "records": {}, "unassigned": {}}
        doc[remote_settings.OWNER] = "a" * 64
        packed = remote_settings.pack(doc, remote_settings.BINDING_FIELDS, "a" * 64)
        projected = remote_settings.project(packed, remote_settings.BINDING_FIELDS, "a" * 64)
        self.assertEqual(projected[self.presets.STORE], doc[self.presets.STORE])
        other = remote_settings.project(packed, remote_settings.BINDING_FIELDS, "b" * 64)
        self.assertNotIn(self.presets.STORE, other)


if __name__ == "__main__":
    unittest.main()
