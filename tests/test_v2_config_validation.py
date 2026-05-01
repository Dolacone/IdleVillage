import os
import unittest

from support import ALL_TEST_ENV

import sys
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from core import config


class ValidateEnvBehavior(unittest.TestCase):
    def setUp(self):
        self._original = {key: os.environ.get(key) for key in config.REQUIRED_KEYS}
        for key, value in ALL_TEST_ENV.items():
            os.environ[key] = value

    def tearDown(self):
        for key, original in self._original.items():
            if original is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original

    def test_all_required_keys_present_passes_validation(self):
        self.assertTrue(config.validate_env())

    def test_missing_single_key_fails_validation(self):
        os.environ.pop("STAGE_BASE_TARGET")
        self.assertFalse(config.validate_env())

    def test_blank_value_treated_as_missing(self):
        os.environ["BASE_OUTPUT"] = "   "
        self.assertFalse(config.validate_env())

    def test_missing_keys_are_all_reported(self, capsys=None):
        os.environ.pop("STAGE_BASE_TARGET")
        os.environ.pop("GEAR_PITY_BONUS")
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = config.validate_env()
        output = buf.getvalue()
        self.assertFalse(result)
        self.assertIn("STAGE_BASE_TARGET", output)
        self.assertIn("GEAR_PITY_BONUS", output)

    def test_required_keys_list_matches_env_example(self):
        env_example_path = os.path.join(ROOT_DIR, ".env.example")
        with open(env_example_path) as f:
            lines = f.readlines()
        example_keys = set()
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                example_keys.add(line.split("=", 1)[0].strip())
        self.assertEqual(set(config.REQUIRED_KEYS), example_keys)


class TypedGettersBehavior(unittest.TestCase):
    def setUp(self):
        self._original = {key: os.environ.get(key) for key in config.REQUIRED_KEYS}
        for key, value in ALL_TEST_ENV.items():
            os.environ[key] = value

    def tearDown(self):
        for key, original in self._original.items():
            if original is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original

    def test_get_env_int_returns_integer(self):
        result = config.get_env_int("ACTION_CYCLE_MINUTES")
        self.assertIsInstance(result, int)
        self.assertEqual(result, 10)

    def test_get_env_float_returns_float(self):
        result = config.get_env_float("MATERIAL_DROP_RATE")
        self.assertIsInstance(result, float)
        self.assertAlmostEqual(result, 0.05)

    def test_get_env_str_returns_string(self):
        result = config.get_env_str("DISCORD_GUILD_ID")
        self.assertIsInstance(result, str)
        self.assertEqual(result, "111111111111111111")

    def test_get_stage_base_target_returns_int(self):
        result = config.get_stage_base_target()
        self.assertIsInstance(result, int)
        self.assertEqual(result, 1000)

    def test_get_action_cycle_minutes_returns_int(self):
        result = config.get_action_cycle_minutes()
        self.assertIsInstance(result, int)
        self.assertEqual(result, 10)

    def test_get_discord_guild_id_returns_str(self):
        result = config.get_discord_guild_id()
        self.assertIsInstance(result, str)
        self.assertEqual(result, "111111111111111111")

    def test_get_announcement_channel_id_returns_str(self):
        result = config.get_announcement_channel_id()
        self.assertIsInstance(result, str)
        self.assertEqual(result, "222222222222222222")
