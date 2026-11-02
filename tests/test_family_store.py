"""Shared configuration persistence, cache refresh and safe concurrent edits."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'family_store.py'


def instance():
    spec = importlib.util.spec_from_file_location('isolated_family_store', SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FamilyStoreTests(unittest.TestCase):
    def setUp(self):
        # Keep every generated test file in the current workspace.
        root = Path(os.environ['J3D_TEST_ROOT']) / 'family-store'
        root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=root)
        self.path = Path(self.temp.name) / 'shared.json'
        self.env = patch.dict(os.environ, {'J3D_NAMING_CONFIG': str(self.path)})
        self.env.start()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.env.stop)
        self.first, self.second = instance(), instance()

    def test_no_file_is_created_by_reads_and_changes_survive_reload(self):
        self.assertEqual(self.first.families(), frozenset())
        self.assertFalse(self.path.exists())
        self.first.set_family(' Wood ', accepted=True)
        self.assertEqual(instance().families(), {'wood'})
        self.assertEqual(json.loads(self.path.read_text())['schema_version'], 1)
        self.first.set_family('wood', accepted=False)
        self.assertFalse(instance().families())

    def test_two_independent_instances_merge_changes_and_refresh(self):
        self.second.families()  # Prime an empty cache, as in another Blender.
        self.first.set_family('wood', accepted=True)
        self.second.set_family('marble', accepted=True)
        self.first.refresh(force=True)
        self.assertEqual(self.first.families(), {'wood', 'marble'})
        self.second.set_family('wood', accepted=False)
        self.first.refresh(force=True)
        self.assertEqual(self.first.families(), {'marble'})

    def test_cross_instance_lock_prevents_lost_update(self):
        self.first.set_family('wood', accepted=True)
        before = self.path.read_bytes()
        with self.first._file_lock(self.path):
            with self.assertRaises(ValueError):
                self.second.set_family('marble', accepted=True)
        self.assertEqual(self.path.read_bytes(), before)
        self.second.set_family('marble', accepted=True)
        self.assertEqual(instance().families(), {'wood', 'marble'})

    def test_damaged_file_is_not_overwritten_and_last_good_list_remains(self):
        self.first.set_family('wood', accepted=True)
        self.path.write_text('{bad json')
        self.first.refresh(force=True)
        self.assertEqual(self.first.families(), {'wood'})
        self.assertTrue(self.first.error())
        with self.assertRaises(ValueError):
            self.first.set_family('marble', accepted=True)
        self.assertEqual(self.path.read_text(), '{bad json')
        self.path.write_text(json.dumps({'schema_version': 1, 'families': ['marble']}))
        self.first.refresh(force=True)
        self.assertEqual(self.first.families(), {'marble'})
        self.assertFalse(self.first.error())

    def test_failed_atomic_replace_keeps_previous_file(self):
        self.first.set_family('wood', accepted=True)
        before = self.path.read_bytes()
        with patch.object(self.first.os, 'replace', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                self.first.set_family('marble', accepted=True)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.glob('*.tmp')), [])

    def test_strict_labels_and_selected_name_extraction(self):
        for name in ('wood0', 'wall3_wood0', 'wood_cube', 'wood.*', '', 'stuff', 'primitive', 'floor', 'hardware'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.first.set_family(name, accepted=True)
        self.assertEqual(self.first.family_from_name('wall3_Wood001.001'), 'wood')
        for name in ('Cube', 'wall3_wood', 'wall3_wood0_cube0', 'wall_3_wood0', ' wall3_wood0', 'wall3_stuff0'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.first.family_from_name(name)
        self.assertFalse(self.path.exists())


if __name__ == '__main__':
    unittest.main()
