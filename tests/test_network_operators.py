import unittest

from updater.common.network_operators import home_operator_from_imsi, lookup_operator


class NetworkOperatorTests(unittest.TestCase):
    def test_live_current_network_is_telekom_germany(self):
        operator = lookup_operator(262, 1)
        self.assertIsNotNone(operator)
        self.assertEqual(operator.name, "Telekom Deutschland GmbH")
        self.assertEqual(operator.code, "262 / 01")

    def test_live_sim_home_network_is_orange_france(self):
        operator = home_operator_from_imsi("208012402223359")
        self.assertIsNotNone(operator)
        self.assertEqual(operator.name, "Orange France")
        self.assertEqual(operator.code, "208 / 01")

    def test_unknown_operator_keeps_code_without_guessing_name(self):
        operator = lookup_operator(262, 99)
        self.assertIsNotNone(operator)
        self.assertIsNone(operator.name)
        self.assertEqual(operator.display, "262 / 99")

    def test_unknown_imsi_country_is_not_guessed(self):
        self.assertIsNone(home_operator_from_imsi("310260123456789"))


if __name__ == "__main__":
    unittest.main()
