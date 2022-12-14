import logging
import pytest
import shlex
import yaml
import re
from pathlib import Path

log = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
@pytest.mark.skip_if_deployed
async def test_build_and_deploy(ops_test):
    log.info("Build charm...")
    charm = await ops_test.build_charm(".")
    log.info("Deploy charm...")
    bundle = ops_test.render_bundle(Path("tests/data/charm.yaml"), charm=charm)
    model = ops_test.model_full_name
    cmd = f"juju deploy -m {model} {bundle}"
    rc, stdout, stderr = await ops_test.run(*shlex.split(cmd))
    assert rc == 0, f"Bundle deploy failed: {(stderr or stdout).strip()}"

    await ops_test.model.block_until(
        lambda: all(app in ["bird0", "bird1"] for app in ops_test.model.applications),
        timeout=60,
    )

    await ops_test.model.wait_for_idle(status="active", timeout=60 * 10)


async def test_bgp(ops_test):
    log.info("Configure charms...")
    apps_a = ops_test.model.applications.get("bird0")
    apps_b = ops_test.model.applications.get("bird1")
    peers_a = [{"as-number": 64513, "address": apps_b.units[0].public_address}]
    peers_b = [{"as-number": 64512, "address": apps_a.units[0].public_address}]
    await apps_a.set_config(
        {"as-number": "64512", "bgp-peers": yaml.safe_dump(peers_a)}
    )
    await apps_b.set_config(
        {"as-number": "64513", "bgp-peers": yaml.safe_dump(peers_b)}
    )

    await ops_test.model.wait_for_idle(status="active", timeout=60 * 2)

    log.info("Check BGP connection 0 to 1...")
    cmd = "juju run --unit bird0/0 birdc show protocols"
    rc, stdout, stderr = await ops_test.run(*shlex.split(cmd))
    assert rc == 0, f"birdc failed: {(stderr or stdout).strip()}"
    # wokeignore:rule=master
    bgp_re = re.compile(r"bgp\d\s+BGP\s+master\s+up")
    match = bgp_re.findall(stdout)
    assert len(match) == 1

    log.info("Check BGP connection 1 to 0...")
    cmd = "juju run --unit bird1/0 birdc show protocols"
    rc, stdout, stderr = await ops_test.run(*shlex.split(cmd))
    assert rc == 0, f"birdc failed: {(stderr or stdout).strip()}"
    match = bgp_re.findall(stdout)
    assert len(match) == 1
