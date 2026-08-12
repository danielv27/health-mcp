# stdio over SSH instead of a public HTTPS endpoint

> The phone-access mechanism described here (SSH into a VM) is superseded by
> [ADR-0007](./0007-claude-code-remote-access-instead-of-a-vm.md). The transport
> decision below — stdio, no HTTP, no TLS, no token — still stands.

The server speaks stdio and is launched by the client on the same host. There is no HTTP
transport, no TLS, no bearer token, and no port open to the internet.

Phone access — the reason a remote host was wanted at all — is satisfied by SSHing into
a small always-on VM and running the agent there in a terminal. Once the client and the
server share a host, the entire network layer becomes dead weight: a public endpoint
holding a personal food diary, guarded by one static token, protecting against a threat
that SSH already handles better.

## Consequences

Deployment is a Python package plus one SQLite file. Moving hosts is `rsync`, not a
migration. The trade is that nothing can reach the server except a session on that box —
in particular claude.ai web and mobile can't, since those would need full OAuth 2.1 with
dynamic client registration, which is a different project.

Tool logic stays free of transport concerns so that adding an HTTP front end later is an
addition rather than a rewrite.
