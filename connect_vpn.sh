#!/bin/bash
sudo apt-get update
sudo apt-get install -y openvpn curl jq

echo "TKns6zrWuLiQxg9K" > /tmp/auth.txt
echo "Jv1hsQCPF9X9DjPRIZQPsJHkyEiRRkVM" >> /tmp/auth.txt

cat > /tmp/config.ovpn << 'OVPN'
client
dev tun
proto udp
remote 185.159.157.40 1194
resolv-retry infinite
nobind
persist-key
persist-tun
remote-cert-tls server
verify-x509-name ProtonVPN_Free_US name
auth-user-pass /tmp/auth.txt
comp-lzo
verb 3
OVPN

sudo openvpn --config /tmp/config.ovpn --auth-user-pass /tmp/auth.txt --daemon
sleep 20
echo "🖥️ Current IP:"
curl -s https://api.ipify.org
