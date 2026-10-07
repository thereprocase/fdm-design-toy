# Rules for people and agents working here

## No personal information (public repo)
- No personal names (owners, friends, collaborators), email addresses, phone numbers, home
  addresses, account handles other than the repo owner's, private hostnames, tailnet names,
  IP addresses, or local paths that contain a user name (`C:\Users\<name>`, `/home/<name>`).
- Refer to people by role ("a collaborator", "the owner") and machines by role:
  - **laptop GPU workstation**: RTX-class laptop GPU (development, smaller solves)
  - **compute box**: 40 Broadwell threads, 300 GB RAM, no GPU (Linux)
  - **second workstation**: Ryzen desktop with an RTX 3080 Ti, Windows + WSL (solver workhorse)
- Commits use the GitHub no-reply address. A local pre-commit hook blocks known personal
  terms; it reads a denylist that lives outside the repo and is never committed.

## Honest numbers
- Every number states what it does and does not establish (evidence tier: own print,
  slicer-only, vendor data, literature, estimate/guess).
- Prefer known-answer tests and measured receipts (hashes, timings, inputs) over claims.
- "Passes the checks" never means "qualified"; physical testing is its own tier.

## Remote compute
- Long jobs on shared machines always run in named, detached tmux sessions
  (`<area>-<project>-<task>`), logging to a file with an exit-code file; never kill
  sessions you didn't start; never kill processes by image name.

## Tracking
- Work items, decisions and open disputes are GitHub issues; the plan links to them.
