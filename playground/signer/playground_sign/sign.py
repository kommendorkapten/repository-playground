# Copyright 2023 Google LLC

"""playground-sign: A command line tool to sign Repository Playground changes"""

import click
import logging
import os

from playground_sign._common import (
    get_signing_key_input,
    git,
    SignerConfig,
    signing_event,
)
from playground_sign._signer_repository import SignerState

logger = logging.getLogger(__name__)

@click.command()
@click.option("-v", "--verbose", count=True, default=0)
@click.option("--push/--no-push", default=True)
@click.argument("event-name", metavar="signing-event")
def sign(verbose: int, push: bool, event_name: str):
    """Signing tool for Repository Playground signing events."""
    logging.basicConfig(level=logging.WARNING - verbose * 10)

    toplevel = git(["rev-parse", "--show-toplevel"])
    settings_path = os.path.join(toplevel, ".playground-sign.ini")
    user_config = SignerConfig(settings_path)

    with signing_event(event_name, user_config) as repo:
        if repo.state == SignerState.UNINITIALIZED:
            click.echo("No metadata repository found")
            changed = False
        elif repo.state == SignerState.INVITED:
            click.echo(f"You have been invited to become a signer for role(s) {repo.invites}.")
            key = get_signing_key_input("To accept the invitation, please insert your HW key and press enter")
            for rolename in repo.invites.copy():
                # Modify the delegation
                role_config = repo.get_role_config(rolename)
                repo.set_role_config(rolename, role_config, key)

                # Sign the role we are now a signer for
                if rolename != "root":
                    repo.sign(rolename)

            # Sign any other roles we may be asked to sign at the same time
            if repo.unsigned:
                click.echo(f"Your signature is requested for role(s) {repo.unsigned}.")
                for rolename in repo.unsigned:
                    click.echo(repo.status(rolename))
                    repo.sign(rolename)
            changed = True
        elif repo.state == SignerState.SIGNATURE_NEEDED:
            click.echo(f"Your signature is requested for role(s) {repo.unsigned}.")
            for rolename in repo.unsigned:
                click.echo(repo.status(rolename))
                repo.sign(rolename)
            changed = True
        elif repo.state == SignerState.TARGETS_CHANGED:
            click.echo(f"Following local target files changes have been found:")
            for rolename, states in repo.target_changes.items():
                for target_state in states.values():
                    click.echo(f"  {target_state.target.path} ({target_state.state.name})")
            click.prompt("Press enter to approve these changes", default=True, show_default=False)

            repo.update_targets()
            changed = True
        elif repo.state == SignerState.NO_ACTION:
            changed = False
        else:
            raise NotImplementedError

        if changed:
            git(["commit", "-m", f"Signed by {user_config.user_name}", "--", "metadata"])
            if push:
                msg = f"Press enter to push signature(s) to {user_config.push_remote}/{event_name}"
                click.prompt(msg, default=True, show_default=False)
                git(["push", user_config.push_remote, f"HEAD:refs/heads/{event_name}"])
                click.echo(f"Pushed branch {event_name} to {user_config.push_remote}")
            else:
                # TODO: maybe deal with existing branch?
                click.echo(f"Creating local branch {event_name}")
                git(["branch", event_name])
        else:
            click.echo("Nothing to do.")
