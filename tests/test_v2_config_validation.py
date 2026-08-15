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

    def test_missing_key_falls_back_to_env_example_default(self):
        os.environ.pop("STAGE_BASE_TARGET")
        self.assertTrue(config.validate_env())
        self.assertEqual(
            config.get_stage_base_target(),
            int(config._ENV_EXAMPLE_DEFAULTS["STAGE_BASE_TARGET"]),
        )

    def test_blank_value_falls_back_to_env_example_default(self):
        os.environ["BASE_OUTPUT"] = "   "
        self.assertTrue(config.validate_env())
        self.assertEqual(
            config.get_env_int("BASE_OUTPUT"),
            int(config._ENV_EXAMPLE_DEFAULTS["BASE_OUTPUT"]),
        )

    def test_validation_fails_when_key_missing_from_both_env_and_example(self):
        os.environ.pop("STAGE_BASE_TARGET")
        os.environ.pop("GEAR_PITY_BONUS")
        original = {
            "STAGE_BASE_TARGET": config._ENV_EXAMPLE_DEFAULTS.pop("STAGE_BASE_TARGET"),
            "GEAR_PITY_BONUS": config._ENV_EXAMPLE_DEFAULTS.pop("GEAR_PITY_BONUS"),
        }
        try:
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = config.validate_env()
            output = buf.getvalue()
            self.assertFalse(result)
            self.assertIn("STAGE_BASE_TARGET", output)
            self.assertIn("GEAR_PITY_BONUS", output)
        finally:
            config._ENV_EXAMPLE_DEFAULTS.update(original)

    def test_auto_tool_keys_are_required_and_resolve(self):
        self.assertIn("AUTO_TOOL_SECONDS_PER_MATERIAL", config.REQUIRED_KEYS)
        self.assertIn("AUTO_TOOL_MAX_HOURS", config.REQUIRED_KEYS)
        self.assertEqual(config.get_env_int("AUTO_TOOL_SECONDS_PER_MATERIAL"), 3600)
        self.assertEqual(config.get_env_int("AUTO_TOOL_MAX_HOURS"), 24)

    def test_dynamic_trial_target_settings_are_required_and_resolve(self):
        self.assertEqual(config.get_env_int("TRIAL_TARGET_STEP"), 25000)
        self.assertEqual(config.get_env_int("TRIAL_RESOURCE_RESERVE"), 10000)
        self.assertNotIn("TRIAL_TARGET_AMOUNT", config.REQUIRED_KEYS)

    def test_legacy_trial_target_setting_is_not_documented(self):
        env_example_path = os.path.join(ROOT_DIR, ".env.example")
        with open(env_example_path) as f:
            self.assertNotIn("TRIAL_TARGET_AMOUNT=", f.read())

    def test_missing_dynamic_trial_target_setting_fails_validation(self):
        original = config._ENV_EXAMPLE_DEFAULTS.pop("TRIAL_TARGET_STEP")
        os.environ.pop("TRIAL_TARGET_STEP")
        try:
            output = self._validate_with_output()
            self.assertFalse(output[0])
            self.assertIn("TRIAL_TARGET_STEP", output[1])
        finally:
            config._ENV_EXAMPLE_DEFAULTS["TRIAL_TARGET_STEP"] = original

    def test_trial_target_step_must_be_positive_integer(self):
        for value in ("0", "-1", "not-an-integer"):
            with self.subTest(value=value):
                os.environ["TRIAL_TARGET_STEP"] = value
                result, diagnostics = self._validate_with_output()
                self.assertFalse(result)
                self.assertIn("TRIAL_TARGET_STEP", diagnostics)

    def test_blank_trial_target_step_fails_instead_of_using_default(self):
        os.environ["TRIAL_TARGET_STEP"] = "   "
        result, diagnostics = self._validate_with_output()
        self.assertFalse(result)
        self.assertIn("TRIAL_TARGET_STEP", diagnostics)

    def test_trial_resource_reserve_allows_zero_but_not_negative_or_non_integer(self):
        os.environ["TRIAL_RESOURCE_RESERVE"] = "0"
        self.assertTrue(config.validate_env())
        for value in ("-1", "not-an-integer", "   "):
            with self.subTest(value=value):
                os.environ["TRIAL_RESOURCE_RESERVE"] = value
                result, diagnostics = self._validate_with_output()
                self.assertFalse(result)
                self.assertIn("TRIAL_RESOURCE_RESERVE", diagnostics)

    def test_trial_duration_and_cooldown_remain_twelve_hours(self):
        self.assertEqual(config.get_env_int("TRIAL_DURATION_SECONDS"), 43200)
        self.assertEqual(config.get_env_int("TRIAL_COOLDOWN_SECONDS"), 43200)

    @staticmethod
    def _validate_with_output():
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            result = config.validate_env()
        return result, buf.getvalue()

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
