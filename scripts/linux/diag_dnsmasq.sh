#!/bin/bash
set -u

cleanup() {
  if [ -n "${DPID:-}" ]; then
    kill "$DPID" 2>/dev/null || true
    wait "$DPID" 2>/dev/null || true
  fi
  ip netns del wfdbg 2>/dev/null || true
  ip link del wfdbg-h 2>/dev/null || true
  rm -f /tmp/wfdbg-*
}
trap cleanup EXIT

ip netns del wfdbg 2>/dev/null || true
ip link del wfdbg-h 2>/dev/null || true
ip netns add wfdbg || exit 1
ip link add wfdbg-h type veth peer name wfdbg-g || exit 1
ip link set wfdbg-g netns wfdbg || exit 1
ip addr add 10.200.0.1/24 dev wfdbg-h || exit 1
ip link set wfdbg-h up || exit 1
ip netns exec wfdbg ip addr add 10.200.0.2/24 dev wfdbg-g || exit 1
ip netns exec wfdbg ip link set wfdbg-g up || exit 1
ip netns exec wfdbg ip link set lo up || exit 1

cat > /tmp/wfdbg-dnsmasq.conf <<'EOF'
interface=wfdbg-h
except-interface=lo
bind-interfaces
listen-address=10.200.0.1
port=53
domain=workflo.internal
address=/app.workflo.internal/10.200.0.2
address=/agent.workflo.internal/10.200.0.2
address=/browser.workflo.internal/10.200.0.2
address=/test.workflo.internal/10.200.0.2
no-resolv
no-hosts
log-queries
log-facility=/tmp/wfdbg-dnsmasq.log
pid-file=/tmp/wfdbg-dnsmasq.pid
EOF

echo '=== config test ==='
echo '=== start ==='
dnsmasq -C /tmp/wfdbg-dnsmasq.conf -k --no-daemon >/tmp/wfdbg-dnsmasq.stdout 2>/tmp/wfdbg-dnsmasq.stderr &
DPID=$!
sleep 1
if kill -0 "$DPID" 2>/dev/null; then
  echo RUNNING
  ss -lunpt | grep -E '(:53|wfdbg|10\.200\.0\.1)' || true
  cat > /etc/netns/wfdbg.resolv.conf <<'EOF'
nameserver 10.200.0.1
EOF
  ip netns exec wfdbg getent hosts app.workflo.internal 2>&1 || true
else
  echo DIED
fi
echo '=== stderr ==='
cat /tmp/wfdbg-dnsmasq.stderr 2>/dev/null || true
echo '=== log ==='
cat /tmp/wfdbg-dnsmasq.log 2>/dev/null || true
