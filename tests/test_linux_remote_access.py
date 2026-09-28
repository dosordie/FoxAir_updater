import unittest
from pathlib import Path


class LinuxRemoteAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.launcher = Path("foxair-updater").read_text(encoding="utf-8")
        cls.installer = Path("updater/linux/install.sh").read_text(encoding="utf-8")
        cls.remote = Path("updater/linux/remote_access.sh").read_text(encoding="utf-8")
        cls.debug = Path("updater/linux/remote_debug_stream.py").read_text(encoding="utf-8")

    def test_remote_adb_uses_expected_network_port(self):
        self.assertIn("ExecStart=$adb_path -a -P $REMOTE_ADB_PORT nodaemon server", self.installer)
        self.assertIn("REMOTE_ADB_PORT=5038", self.installer)
        self.assertIn("foxair-adb-remote.service", self.installer)

    def test_local_launcher_reuses_running_remote_adb_server(self):
        self.assertIn("systemctl is-active --quiet foxair-adb-remote.service", self.launcher)
        self.assertIn('ADB_SERVER_SOCKET="tcp:127.0.0.1:5038"', self.launcher)

    def test_debug_bridge_is_interface_based_and_read_only(self):
        self.assertIn('USB_VENDOR_ID = "1e0e"', self.debug)
        self.assertIn('USB_PRODUCT_ID = "9001"', self.debug)
        self.assertIn('USB_INTERFACE_NUM = "04"', self.debug)
        self.assertIn("os.O_RDONLY", self.debug)
        self.assertNotIn("os.write(", self.debug)
        self.assertIn("while await reader.read(4096)", self.debug)

    def test_remote_control_manages_both_services(self):
        self.assertIn('ADB_SERVICE="foxair-adb-remote.service"', self.remote)
        self.assertIn('DEBUG_SERVICE="foxair-debug-stream.service"', self.remote)
        for action in ("start)", "stop)", "restart)", "enable)", "disable)", "status)"):
            self.assertIn(action, self.remote)

    def test_ser2net_is_not_a_linux_runtime_dependency(self):
        self.assertNotIn("command -v ser2net", self.installer)
        self.assertNotIn("apt-get install -y ser2net", self.installer)
        self.assertNotIn("systemctl start ser2net", self.remote)
        self.assertNotIn("systemctl restart ser2net", self.remote)


if __name__ == "__main__":
    unittest.main()
