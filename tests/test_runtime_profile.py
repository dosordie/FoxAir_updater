import unittest

from updater.common.runtime_profile import CANCEL_BREAKPOINTS


class RuntimeProfileTests(unittest.TestCase):
    def test_cancel_breakpoint_profile_is_unique_and_word_aligned(self):
        addresses = [site.address for site in CANCEL_BREAKPOINTS]
        self.assertEqual(len(addresses), 8)
        self.assertEqual(len(set(addresses)), len(addresses))
        for site in CANCEL_BREAKPOINTS:
            self.assertEqual(site.address % 4, 0)
            self.assertEqual(len(site.instruction), 4)


if __name__ == "__main__":
    unittest.main()
