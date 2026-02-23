import os
import subprocess

import pytest

# pytest integration scaffold for golden paths

# We only run these if specifically requested to avoid running them during
# standard fast unit tests, since they require a fully running stack.
RUN_INTEGRATION_TESTS = os.environ.get("RUN_INTEGRATION_TESTS", "false").lower() == "true"


@pytest.mark.skipif(not RUN_INTEGRATION_TESTS, reason="RUN_INTEGRATION_TESTS not set")
class TestGoldenPaths:
    """
    Executes the bash-based Golden Paths as part of the pytest suite.
    """

    def _run_script(self, script_name: str):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script_path = os.path.join(base_dir, "paths", script_name)

        # Ensure executable
        os.chmod(script_path, 0o755)

        env = os.environ.copy()
        # Ensure tests point to local defaults if not defined
        env.setdefault("NEXUS_API_URL", "http://localhost:8000")
        env.setdefault("ADMIN_EMAIL", "admin@local.host")
        env.setdefault("ADMIN_PASSWORD", "admin")

        result = subprocess.run(["bash", script_path], env=env, capture_output=True, text=True)

        # Assert the script didn't exit 1 (which it does via the `fail` function)
        assert result.returncode == 0, (
            f"Golden path '{script_name}' failed:\n{result.stderr}\n{result.stdout}"
        )

    def test_path_01_kb_ingest(self):
        self._run_script("01_kb_ingest_and_rag_search.sh")

    def test_path_02_dns_lookup(self):
        self._run_script("02_dns_lookup_with_rag_context.sh")

    def test_path_03_pbx_inventory(self):
        self._run_script("03_pbx_inventory_snapshot_to_sor.sh")

    def test_path_04_monitoring(self):
        self._run_script("04_monitoring_ingest_alert_to_task.sh")

    def test_path_05_storage(self):
        self._run_script("05_storage_copy_job.sh")

    def test_path_06_carrier(self):
        self._run_script("06_carrier_inventory_snapshot.sh")

    def test_path_07_sor_idempotency(self):
        self._run_script("07_sor_idempotency_proof.sh")

    def test_path_08_audits(self):
        self._run_script("08_audit_proof.sh")
