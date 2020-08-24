#!/usr/bin/python3

"""Ghrunt - Entrypoint

Entrypoint of the GitHub-Actions-Runner container. See the Dockerfile for
the general setup. This entrypoint registers the runner and spawns it.
"""


import argparse
import contextlib
import json
import subprocess
import sys
import urllib.request


class Ghrunt(contextlib.AbstractContextManager):
    """Application Runtime Class"""

    def __init__(self, argv):
        self.args = None
        self._argv = argv
        self._parser = None

    def _parse_args(self):
        self._parser = argparse.ArgumentParser(
            add_help=True,
            allow_abbrev=False,
            argument_default=None,
            description="GitHub-Actions-Runner Terminal",
            prog="ghrunt",
        )
        self._parser.add_argument(
            "--labels",
            help="Additional labels for the runner (comma separated)",
            metavar="LIST",
            required=True,
            type=str,
        )
        self._parser.add_argument(
            "--name",
            help="Unique-name of this runner",
            metavar="STRING",
            required=True,
            type=str,
        )
        self._parser.add_argument(
            "--pat",
            help="Personal Access Token",
            metavar="TOKEN",
            required=True,
            type=str,
        )
        self._parser.add_argument(
            "--registry",
            help="Organization or repository to register on",
            metavar="ORG/REPO",
            required=True,
            type=str,
        )

        return self._parser.parse_args(self._argv[1:])

    def __enter__(self):
        self.args = self._parse_args()
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        pass

    def _acquire_token(self):
        """Acquire Git Hub Runner Token

        Git Hub provides an API to acquire a registration token for the runner
        application. They use Azure Pipelines internally, so the standard
        Git Hub tokens are not sufficient. Instead, we use a normal Git Hub
        PAT (Personal Access Token) to access the Git Hub API and acquire an
        Azure token for the runner.

        This token is only valid for 24h (or as long as a registered runner
        uses it), so there is no point in caching it. We re-acquire it on every
        run.

        You need a PAT with full `repo` access for this to work.
        """

        url = "https://api.github.com/"
        if "/" in self.args.registry:
            url += f"repos/{self.args.registry}"
        else:
            url += f"orgs/{self.args.registry}"
        url += "/actions/runners/registration-token"

        request = urllib.request.Request(
            url=url,
            data="".encode(),
            headers={
                "Accept": "application/vnd.github.v3+json",
                "Authorization": f"token {self.args.pat}",
            },
        )

        with urllib.request.urlopen(request) as filp:
            data = json.load(filp)

        return data.get("token")

    def _configure_runner(self, token):
        """Configure Runner Application

        Use the `config.sh` script shipped with the Git Hub Runner application
        to configure the runner. This will write configuration files with all
        this information included.
        """

        subprocess.run(
            [
                "./config.sh",
                "--labels", self.args.labels,
                "--name", self.args.name,
                "--replace",
                "--token", token,
                "--unattended",
                "--url", f"https://github.com/{self.args.registry}",
                "--work", "/ghrunt/workdir",
            ],
            check=True,
        )

    def _spawn_runner(self):
        """Spawn Runner

        This synchronously executes the Git Hub Runner application. We use the
        `run.sh` wrapper script shipped with the Git Hub Runner executable.
        """

        subprocess.run(
            [
                "./run.sh"
            ],
            check=True,
        )

    def _remove_runner(self, token):
        """Remove Runner

        Remove the Git Hub registration of the local runner. This will make
        sure no registration is left on Git Hub when the runner exits. We
        always use ephemeral runners, so we want them to register/unregister
        as they come and go. We do not use stateful runners.

        This will fail if there is no matching registration, but this should
        not matter.
        """

        subprocess.run(
            [
                "./config.sh",
                "remove",
                "--token", token,
            ],
            check=True,
        )

    def run(self):
        """Run Application"""

        print("Acquire token from GitHub...")
        token = self._acquire_token()
        print("Token:", token)

        try:
            print("Configure runner...")
            self._configure_runner(token)
            print("Configured.")

            print("Execute runner...")
            self._spawn_runner()
            print("Finished.")
        finally:
            print("Remove runner...")
            self._remove_runner(token)
            print("Removed.")

        print("Done.")


if __name__ == "__main__":
    with Ghrunt(sys.argv) as global_main:
        sys.exit(global_main.run())