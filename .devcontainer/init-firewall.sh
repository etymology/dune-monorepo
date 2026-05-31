#!/bin/bash
# Default-deny outbound firewall with an allowlist. This is the real safety layer
# for running Claude with --dangerously-skip-permissions: the filesystem is the
# container, and the network can only reach the package registries and APIs below.
set -euo pipefail
IFS=$'\n\t'

echo "==> Configuring egress firewall..."

# Flush existing rules / ipsets.
iptables -F
iptables -X
iptables -t nat -F 2>/dev/null || true
iptables -t nat -X 2>/dev/null || true
iptables -t mangle -F 2>/dev/null || true
iptables -t mangle -X 2>/dev/null || true
ipset destroy allowed-domains 2>/dev/null || true

# DNS, SSH and loopback must work before we lock things down.
iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
iptables -A INPUT  -p udp --sport 53 -j ACCEPT
iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT
iptables -A INPUT  -p tcp --sport 53 -j ACCEPT
iptables -A OUTPUT -p tcp --dport 22 -j ACCEPT
iptables -A INPUT  -p tcp --sport 22 -j ACCEPT
iptables -A INPUT  -i lo -j ACCEPT
iptables -A OUTPUT -o lo -j ACCEPT

ipset create allowed-domains hash:net

# GitHub publishes its IP ranges; add them all (git/api/web/packages/actions).
echo "    fetching GitHub IP ranges..."
gh_ranges=$(curl -s --max-time 10 https://api.github.com/meta || true)
if [ -n "$gh_ranges" ] && echo "$gh_ranges" | jq -e '.web' >/dev/null 2>&1; then
  echo "$gh_ranges" | jq -r '(.web + .api + .git + .actions + .packages)[]' \
    | aggregate -q 2>/dev/null | while read -r cidr; do
      ipset add allowed-domains "$cidr" 2>/dev/null || true
    done
else
  echo "    WARN: could not fetch GitHub ranges; continuing with DNS-resolved hosts only"
fi

# Resolve and allow these hosts (package registries + Anthropic/Claude Code).
for domain in \
  registry.npmjs.org \
  api.anthropic.com \
  console.anthropic.com \
  claude.ai \
  statsig.anthropic.com \
  statsig.com \
  sentry.io \
  pypi.org \
  files.pythonhosted.org \
  astral.sh \
  static.rust-lang.org \
  sh.rustup.rs \
  crates.io \
  index.crates.io \
  static.crates.io \
  objects.githubusercontent.com \
  ; do
  ips=$(dig +short A "$domain" | grep -E '^[0-9.]+$' || true)
  if [ -z "$ips" ]; then
    echo "    WARN: no A record for $domain"
    continue
  fi
  for ip in $ips; do
    ipset add allowed-domains "$ip" 2>/dev/null || true
  done
done

# Allow replies on connections we initiated.
iptables -A INPUT  -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

# Allow the Docker host subnet so VS Code server / port forwarding works.
HOST_IP=$(ip route | awk '/default/ {print $3; exit}')
if [ -n "${HOST_IP:-}" ]; then
  HOST_NET=$(echo "$HOST_IP" | sed 's/\.[0-9]*$/.0\/24/')
  iptables -A OUTPUT -d "$HOST_NET" -j ACCEPT
  iptables -A INPUT  -s "$HOST_NET" -j ACCEPT
fi

# Default deny, then allow the allowlist.
iptables -P INPUT DROP
iptables -P OUTPUT DROP
iptables -P FORWARD DROP
iptables -A OUTPUT -m set --match-set allowed-domains dst -j ACCEPT

# Sanity checks.
echo "==> Verifying..."
if curl -s --max-time 5 https://example.com >/dev/null 2>&1; then
  echo "    WARN: reached example.com (expected to be blocked)"
else
  echo "    OK: unlisted hosts blocked"
fi
if curl -s --max-time 5 https://api.github.com/zen >/dev/null 2>&1; then
  echo "    OK: github reachable"
else
  echo "    WARN: github not reachable (check DNS / ranges)"
fi
echo "==> Firewall ready."
