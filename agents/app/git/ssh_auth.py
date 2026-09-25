"""SSH deploy-key auth for the brain-as-clone remote (single-repo, read-write, least-privilege).

A repo-scoped GitHub deploy key is the least-privilege credential for machine push access: unlike
a classic PAT (`repo` scope — every repo the token's user can see), a deploy key authorizes exactly
one repository (`HendoCode/content-machine-brain`) and is revocable there alone, with no other
credential affected. The private key material is resolved just-in-time through the secrets shim
(`app.secrets`, e.g. `BRAIN_DEPLOY_KEY`) and never committed, baked into an image, or written to
`.git/config` — this module only ever materializes it into a process-local, mode-0600 file used
for the lifetime of the process.

Host-key checking stays strict (never `StrictHostKeyChecking=no`, never trust-on-first-use):
``_GITHUB_KNOWN_HOSTS`` pins GitHub's own published host keys (docs.github.com, "GitHub's SSH key
fingerprints"), so a stolen/spoofed DNS answer can't MITM the clone/push/pull.
"""

from __future__ import annotations

import atexit
import shutil
import stat
import tempfile
from functools import lru_cache
from pathlib import Path

# GitHub's own published SSH host keys — stable, documented at
# https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints
# Pinned here (rather than trust-on-first-use / ssh-keyscan) so StrictHostKeyChecking can stay
# "yes" with no interactive step and no MITM window.
_GITHUB_KNOWN_HOSTS = (
    "github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl\n"
    "github.com ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBEmKSENjQEezOmxkZMy7opKgwFB9nkt5YRrYMjNuG5N87uRgg6CLrbo5wAdT/y6v0mKV0U2w0WZ2YB/++Tpockg=\n"
    "github.com ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCj7ndNxQowgcQnjshcLrqPEiiphnt+VTTvDP6mHBL9j1aNUkY4Ue1gvwnGLVlOhGeYrnZaMgRK6+PKCUXaDbC7qtbW8gIkhL7aGCsOr/C56SJMy/BCZfxd1nWzAOxSDPgVsmerOBYfNqltV9/hWCqBywINIR+5dIg6JTJ72pcEpEjcYgXkE2YEFXV1JHnsKgbLWNlhScqb2UmyRkQyytRLtL+38TGxkxCflmO+5Z8CSSNY7GidjMIZ7Q4zMjA2n1nGrlTDkzwDCsw+wqFPGQA179cnfGWOWRVruj16z6XyvxvjJwbz0wQZ75XK5tKSb7FNyeIEs4TT4jk+S4dhPeAUC5y+bDYirYgM4GC7uEnztnZyaVWQ7B381AK4Qdrwt51ZqExKbQpTUNn+EjqoTwvqNj4kqx5QUCI0ThS/YkOxJCXmPUWZbhjpCg56i+2aB6CmK2JGhn57K5mj0MNdBXA4/WnwH6XoPWJzK5Nyu2zB3nAZp+S5hpQs+p1vN1/wsjk=\n"
)


class SshDeployKey:
    """One process-local materialization of a deploy-key private key + pinned known_hosts.

    ``git_ssh_command`` is what callers pass as ``GIT_SSH_COMMAND`` to make ``git fetch``/``push``/
    ``clone`` authenticate as this key against a strictly host-key-checked GitHub. Construct via
    :func:`get_ssh_deploy_key` rather than directly, so a process reuses one on-disk copy instead
    of writing a fresh temp file per call.
    """

    def __init__(self, private_key: str) -> None:
        self._dir = Path(tempfile.mkdtemp(prefix="cmw-brain-deploy-key-"))
        atexit.register(shutil.rmtree, self._dir, ignore_errors=True)

        self.key_path = self._dir / "id_deploy_key"
        key_text = private_key if private_key.endswith("\n") else private_key + "\n"
        self.key_path.write_text(key_text, encoding="utf-8")
        self.key_path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600 — ssh refuses a laxer-permission key

        self.known_hosts_path = self._dir / "known_hosts"
        self.known_hosts_path.write_text(_GITHUB_KNOWN_HOSTS, encoding="utf-8")

    @property
    def git_ssh_command(self) -> str:
        return (
            f"ssh -i {self.key_path} -o IdentitiesOnly=yes -o BatchMode=yes "
            f"-o StrictHostKeyChecking=yes -o UserKnownHostsFile={self.known_hosts_path}"
        )


@lru_cache(maxsize=1)
def get_ssh_deploy_key(private_key: str) -> SshDeployKey:
    """One :class:`SshDeployKey` per distinct key value for this process's lifetime — callers
    (``open_brain``/``open_content_store``/``ensure_brain_available``) each resolve the secret and
    call this on every invocation, so caching here is what keeps that from writing a new temp
    key file to disk on every request/job."""
    return SshDeployKey(private_key)
