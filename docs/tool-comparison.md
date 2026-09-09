# Used one agent only : Cursor

## What Cursor made easy

Plan mode asked whether to copy the lesson's Task Manager Dockerfile or
write one for this FastAPI service. That question happened before any
file existed. The Dockerfile then followed `uv.lock`, copied `src/` and
`data/`, and kept `StubPolicyClient`'s `Path(__file__).parents[2]` path
valid. 
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