import asyncio
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
    # wokeignore:rule=master
    bgp_re = re.compile(r"bgp\d\s+BGP\s+master\s+up")

    async def _check_protocols(unit, direction):
        log.info(f"Check BGP connection {direction}...")
        action = await unit.run("birdc show protocols")
        action = await action.wait()
        rc, stderr, stdout = (
            action.results.get(k) for k in ["return-code", "stderr", "stdout"]
        )
        assert rc == 0, f"birdc failed: {(stderr or stdout).strip()}"
        match = bgp_re.findall(stdout)
        assert len(match) == 1

    await asyncio.gather(
        asyncio.wait_for(_check_protocols(apps_a.units[0], "0 to 1..."), timeout=10),
        asyncio.wait_for(_check_protocols(apps_b.units[0], "1 to 0..."), timeout=10),
    )
