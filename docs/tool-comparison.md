# Cursor vs Claude Code

Bounded task done in Cursor: the Day 4 Dockerfile, `.dockerignore`,
README, and getting `docker buildx build --platform linux/amd64` to a
process that accepted `POST /notifications`.

Claude Code is the usual agent. This note is from doing that one piece
in Cursor instead, not from a feature list.

## What Cursor made easy

Plan mode asked whether to copy the lesson's Task Manager Dockerfile or
write one for this FastAPI service. That question happened before any
file existed. The Dockerfile then followed `uv.lock`, copied `src/` and
`data/`, and kept `StubPolicyClient`'s `Path(__file__).parents[2]` path
valid. A Claude Code session started from the lesson notes would have
been more likely to emit `CMD ["python", "task_manager.py"]`.

Ask mode later checked the four lab items against the files without
editing them. The editor already had `routes.py`, `test_routes.py`, and
the contract open. That is a review pass, not a generate-and-hope pass.

## What Cursor made awkward

The agent ran inside an unprivileged container. `docker buildx build`
failed with `failed to mount ... operation not permitted`. The agent
then tried to install Docker and start `dockerd` in that same box. None
of that was the task. The image only built after leaving Cursor, cloning
`http-integration-tests` on the Mac, and running the same command there.

`git push` from the agent failed (`could not read Username for
'https://github.com'`). The same branch pushed from the lab terminal.
The agent could commit. It could not ship.

The first Mac instructions used `~/Downloads/claims-intake` as if that
folder were empty. It already existed and had no `Dockerfile`. `git
clone` without a target name kept colliding with that folder. Cursor
could see the lab workspace; it could not see the Mac disk.

## What Claude Code made easy (by contrast)

Claude Code is usually started in the same terminal as Docker Desktop.
`docker buildx build --platform linux/amd64 --load .` would have run on
the machine that is allowed to create containers. There would have been
no nested-daemon detour and no "clone it again under a new folder name"
thread.

A CLI agent also treats the shell as the workspace. `pwd`, `ls
Dockerfile`, and the build are one session, not an IDE folder that is
not the Mac folder.

## What Claude Code made awkward (by contrast)

Claude Code does not sit on the contract and the route in split panes
while you write. The easy failure mode is a generic Python Dockerfile
and a README that tells the joiner to `pip install`. This repo has no
`requirements.txt`; CI is `uv sync --frozen`. Cursor had those files in
context without being asked to go find them.

Plan vs Agent vs Ask is not a Claude Code habit. The Dockerfile would
have been easier to over-build there (env vars and volumes the service
does not use) because the lesson text invited that and nothing in the
UI forced a scope question first.

## When to reach for which

- **Cursor:** a change that has to match files already in the repo
  (this Dockerfile, the HTTP mapping, a README that must not invent an
  install step). The cost of being wrong is a grader reading the
  contract against the code.
- **Claude Code, on the laptop that has Docker:** a success criterion
  that is a command (`docker buildx`, `docker run`, `curl`). The cost of
  being wrong is "it failed in a box that cannot run Docker."

## Preference

For the rest of this lab, **Cursor**. The work is "does this match
`docs/api-contract.md` and the tree that is already here," and Cursor
made that the default. The Docker verify belonged on the Mac; that is a
place to run a command, not a reason to author the Dockerfile in a tool
that cannot see `policy_client.py`.

I would not start Claude Code to write the next route or test. I would
open a Mac terminal, or Claude Code in that terminal, the next time the
acceptance line is "the image builds and the process answers."
