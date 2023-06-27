# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest
import yaml
import ops.testing

from unittest import mock
from charm import BirdCharm

ops.testing.SIMULATE_CAN_CONNECT = True

bird_config = """log syslog all;
debug protocols all;

protocol kernel {
  persist;
  scan time 20;
  export all;
}

protocol device {
  scan time 10;
}

protocol bgp {
  import all;
  local as 64512;
  neighbor 10.0.0.2 as 64512;
  direct;
}

protocol bgp {
  import all;
  local as 64512;
  neighbor 10.0.0.3 as 64513;
  direct;
}
"""


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = ops.testing.Harness(BirdCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    @mock.patch("charm.check_call", autospec=True)
    def test_on_install(self, mock_check):
        self.harness.charm.install("mock_event")
        mock_check.assert_has_calls(
            [
                mock.call(["apt-get", "update"]),
                mock.call(["apt-get", "install", "-y", "bird"]),
            ]
        )

    @mock.patch("builtins.open", new_callable=mock.mock_open())
    @mock.patch("charm.BirdCharm.render_bird_conf")
    @mock.patch("charm.check_call")
    def test_config_changed(self, mock_call, mock_render, mock_open):
        mock_render.return_value = bird_config
        self.harness.update_config({"as-number": 12345})
        mock_open.assert_called_once_with("/etc/bird/bird.conf", "w")
        mock_open.return_value.__enter__().write.assert_called_once_with(bird_config)
        mock_call.assert_called_once_with(["systemctl", "reload", "bird"])

    def test_render_bird_conf(self):
        bgp_config = [
            {"address": "10.0.0.2", "as-number": "64512"},
            {"address": "10.0.0.3", "as-number": "64513"},
        ]
        self.harness.disable_hooks()
        self.harness.update_config({"bgp-peers": yaml.safe_dump(bgp_config)})
        self.harness.enable_hooks()
        assert bird_config == self.harness.charm.render_bird_conf()
