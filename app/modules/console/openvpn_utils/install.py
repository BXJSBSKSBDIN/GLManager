import os

from urllib.request import urlopen
from console import Console, FuncItem, COLOR_NAME

from ..utils import logger


RCLOCAL = '/etc/rc.local'

OPENVPN_PATH = '/etc/openvpn'
EASYRSA_PATH = os.path.join(OPENVPN_PATH, 'easy-rsa')
EASYRSA_PKI_PATH = os.path.join(EASYRSA_PATH, 'easy-rsa/pki')

EASYRSA_PKI_CA = os.path.join(EASYRSA_PKI_PATH, 'ca.crt')
EASYRSA_PKI_TLS = os.path.join(EASYRSA_PKI_PATH, 'ta.key')

EASYRSA_PKI_CERT_PATH = os.path.join(EASYRSA_PKI_PATH, 'issued/')
EASYRSA_PKI_KEY_PATH = os.path.join(EASYRSA_PKI_PATH, 'private/')

CLIENT_COMMON_CONFIG = os.path.join(OPENVPN_PATH, 'client-common.txt')

ROOT_PATH = os.path.expanduser('~')

IP_ADDRESS = (
    os.popen(
        '|'.join(
            [
                'ip addr',
                'grep \'inet\'',
                'grep -v inet6',
                'grep -vE \'127\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\'',
                'grep -o -E \'[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\'',
                'head -1',
            ]
        )
    )
    .read()
    .strip()
)

IP_ADDRESS2 = urlopen('https://api.ipify.org').read().decode('utf8')

if not IP_ADDRESS:
    IP_ADDRESS = os.popen('hostname -I | cut -d\' \' -f1').read().strip()

if IP_ADDRESS == IP_ADDRESS2:
    IP_ADDRESS = IP_ADDRESS2

EASYRSA_VERSION = '3.1.0'
EASYRSA_NAME = 'EasyRSA-%s.tgz' % EASYRSA_VERSION
EASYRSA_URL = 'https://github.com/OpenVPN/easy-rsa/releases/download/v%s/%s' % (
    EASYRSA_VERSION,
    EASYRSA_NAME,
)


def create_ovpn_client(username: str) -> None:
    os.chdir(EASYRSA_PATH)
    os.system('./easyrsa build-client-full %s nopass' % username)

    ovpn_config_template = '\n'.join(
        [
            '%s',
            '<ca>',
            '%s',
            '</ca>',
            '<cert>',
            '%s',
            '</cert>',
            '<key>',
            '%s',
            '</key>',
            '<tls-auth>',
            '%s',
            '</tls-auth>',
        ]
    )

    ovpn_config = ovpn_config_template % (
        open(CLIENT_COMMON_CONFIG).read(),
        open(EASYRSA_PKI_CA).read(),
        open(EASYRSA_PKI_CERT_PATH + username + '.crt').read(),
        open(EASYRSA_PKI_KEY_PATH + username + '.key').read(),
        open(EASYRSA_PKI_TLS).read(),
    )

    with open(os.path.join(ROOT_PATH, username + '.ovpn'), 'w') as f:
        f.write(ovpn_config)


def create_common_client_config(port: int, protocol: str) -> None:
    with open(CLIENT_COMMON_CONFIG, 'w') as f:
        f.write(
            '\n'.join(
                [
                    'client' 'dev tun',
                    'proto %s' % protocol,
                    'sndbuf 0',
                    'rcvbuf 0',
                    'remote 127.0.0.1 %s' % port,
                    'resolv-retry 5',
                    'nobind',
                    'persist-key',
                    'persist-tun',
                    'remote-cert-tls server',
                    'cipher AES-256-CBC',
                    'comp-lzo yes',
                    'setenv opt block-outside-dns',
                    'key-direction 1',
                    'verb 3',
                    'auth-user-pass',
                    'keepalive 10 120',
                    'float',
                ]
            )
        )


def confirm_ip_address() -> bool:
    global IP_ADDRESS

    if not IP_ADDRESS:
        logger.error('Não foi possível encontrar o IP do servidor.')
        return False

    logger.info((COLOR_NAME.YELLOW + 'IP do servidor: %s' + COLOR_NAME.END) % IP_ADDRESS)
    result = input('Confirmar IP do servidor? [s/N] ')

    if result.lower() != 's':
        result = input(COLOR_NAME.YELLOW + 'Digite o IP do servidor: ' + COLOR_NAME.END)

        if not result:
            logger.error('IP do servidor não confirmado.')
            return False

        IP_ADDRESS = result

    return True


def get_port_openvpn() -> int:
    console = Console('Porta do OpenVPN')
    console.append_item(FuncItem('1194', lambda: '1194', shuld_exit=True))
    console.append_item(FuncItem('8888', lambda: '8888', shuld_exit=True))
    console.append_item(
        FuncItem(
            'Custom',
            lambda: input(COLOR_NAME.YELLOW + 'Digite a porta: ' + COLOR_NAME.END),
            shuld_exit=True,
        )
    )
    console.show()
    port = console.item_returned

    if port is not None and not port.isdigit():
        logger.error('Porta não definida.')
        raise ValueError('Porta não definida.')

    return int(port)


def get_dns_openvpn() -> str:
    def get_system_dns() -> str:
        template = 'push "dhcp-option DNS %s"'
        dns = '\n'.join(
            [
                template % line.strip()
                for line in os.popen(
                    'grep -v \'#\' /etc/resolv.conf | grep \'nameserver\' | grep -E -o \'[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\''
                ).readlines()
                if line.strip()
            ]
        )

        return dns

    console = Console('Escolha o DNS do OpenVPN:')
    console.append_item(
        FuncItem(
            'DNS do sistema',
            lambda: get_system_dns(),
            shuld_exit=True,
        )
    )
    console.append_item(
        FuncItem(
            'Google DNS',
            lambda: 'push "dhcp-option DNS 8.8.8.8"\npush "dhcp-option DNS 8.8.4.4"',
            shuld_exit=True,
        )
    )
    console.append_item(
        FuncItem(
            'OpenDNS',
            lambda: 'push "dhcp-option DNS 208.67.222.222"\npush "dhcp-option DNS 208.67.220.220"',
            shuld_exit=True,
        )
    )
    console.append_item(
        FuncItem(
            'Cloudflare',
            lambda: 'push "dhcp-option DNS 1.1.1.1"\npush "dhcp-option DNS 1.0.0.1"',
            shuld_exit=True,
        )
    )
    console.show()

    if console.item_returned is None:
        logger.error('DNS não definido.')
        raise ValueError('DNS não definido.')

    return console.item_returned


def get_protocol_openvpn() -> str:
    console = Console('Escolha o protocolo do OpenVPN:')
    console.append_item(
        FuncItem(
            'UDP',
            lambda: 'UDP',
            shuld_exit=True,
        )
    )
    console.append_item(
        FuncItem(
            'TCP',
            lambda: 'TCP',
            shuld_exit=True,
        )
    )
    console.show()

    if console.item_returned is None:
        logger.error('Protocolo não definido.')
        raise ValueError('Protocolo não definido.')

    return console.item_returned


def update_package() -> None:
    os.system('apt-get update -y 1>/dev/null 2>&1')


def install_packages() -> None:
    os.system('apt-get install openvpn iptables openssl ca-certificates zip -y 1>/dev/null 2>&1')


def setup_dir() -> None:
    if os.path.exists(EASYRSA_PATH):
        os.system('rm -rf %s' % EASYRSA_PATH)

    os.system('mkdir -p %s' % EASYRSA_PATH)


def download_easyrsa() -> None:
    os.system('wget %s -O %s' % (EASYRSA_URL, EASYRSA_NAME))


def build_easyrsa() -> None:
    os.system('tar -xzf %s --strip-components=1 --directory %s' % (EASYRSA_NAME, EASYRSA_PATH))

    if not os.path.exists(EASYRSA_PATH):
        logger.error('Não foi possível baixar o EasyRSA.')
        raise ValueError('Não foi possível baixar o EasyRSA.')

    os.system('chown -R root:root %s' % EASYRSA_PATH)

    os.chdir(EASYRSA_PATH)

    os.system('bash -c "./easyrsa init-pki"')
    os.system('bash -c "./easyrsa --batch build-ca nopass"')
    os.system('bash -c "./easyrsa gen-dh"')
    os.system('bash -c "./easyrsa build-server-full server nopass"')
    os.system('bash -c "./easyrsa build-client-full GLTUNNEL nopass"')
    os.system('bash -c "./easyrsa gen-crl"')

    os.system(
        'cp pki/ca.crt pki/private/ca.key pki/dh.pem pki/issued/server.crt pki/private/server.key /etc/openvpn/easy-rsa/pki/crl.pem /etc/openvpn'
    )
    os.system('chown -R nobody:nogroup /etc/openvpn/crl.pem')
    os.system('openvpn --genkey --secret /etc/openvpn/ta.key')


def build_server_config(port: int, protocol: str, dns: str) -> None:
    os.chdir(OPENVPN_PATH)

    config_file = 'server.conf'
    with open(config_file, 'w') as f:
        f.write(
            '\n'.join(
                [
                    'port %s' % port,
                    'proto %s' % protocol,
                    'dev tun',
                    'sndbuf 0',
                    'rcvbuf 0',
                    'ca ca.crt',
                    'cert server.crt',
                    'key server.key',
                    'dh dh.pem',
                    'tls-auth ta.key 0',
                    'topology subnet',
                    'server 10.8.0.0 255.255.255.0',
                    'ifconfig-pool-persist ipp.txt',
                    'push "redirect-gateway def1 bypass-dhcp"',
                    '%s' % dns,
                    'float',
                    'cipher AES-256-CBC',
                    'comp-lzo yes',
                    'user nobody',
                    'group $GROUPNAME',
                    'persist-key',
                    'persist-tun',
                    'status openvpn-status.log',
                    'management localhost 7505',
                    'verb 3',
                    'crl-verify crl.pem',
                    'client-to-client',
                    'client-cert-not-required',
                    'username-as-common-name',
                    'plugin %s login'
                    % os.popen('find /usr -type f -name \'openvpn-plugin-auth-pam.so\'')
                    .readline()
                    .strip(),
                    'duplicate-cn',
                ]
            )
        )


def build_ip_forward() -> None:
    os.system('sysctl -w net.ipv4.ip_forward=1')

    with open('/proc/sys/net/ipv4/ip_forward', 'w') as f:
        f.write('1')


def build_rc_local() -> None:
    config = '\n'.join(
        [
            '#!/bin/sh -e',
            'iptables -t nat -A POSTROUTING -s 10.8.0.0/24 -j SNAT --to 10.0.0.4',
            'echo 1 > /proc/sys/net/ipv4/ip_forward',
            'echo 1 > /proc/sys/net/ipv6/conf/all/disable_ipv6',
            'iptables -A INPUT -p tcp --dport 25 -j DROP',
            'iptables -A INPUT -p tcp --dport 110 -j DROP',
            'iptables -A OUTPUT -p tcp --dport 25 -j DROP',
            'iptables -A OUTPUT -p tcp --dport 110 -j DROP',
            'iptables -A FORWARD -p tcp --dport 25 -j DROP',
            'iptables -A FORWARD -p tcp --dport 110 -j DROP',
            'exit 0',
        ]
    )

    with open(RCLOCAL, 'w') as f:
        f.write(config)

    os.system('chmod +x %s' % RCLOCAL)


def build_iptables(ip: str, port: int, protocol: str) -> None:
    os.system('iptables -t nat -A POSTROUTING -s 10.8.0.0/24 -j SNAT --to %s' % ip)

    if os.system('pgrep firewalld') == 0:
        os.system('firewall-cmd --zone=public --add-port=%s/%s' % (port, protocol))
        os.system('firewall-cmd --zone=trusted --add-source=10.8.0.0/24')
        os.system('firewall-cmd --permanent --zone=public --add-port=%s/%s' % (port, protocol))
        os.system('firewall-cmd --permanent --zone=trusted --add-source=10.8.0.0/24')

    if os.system('iptables -L -n | grep -qE \'REJECT|DROP\'') == 0:
        os.system('iptables -I INPUT -p %s --dport %s -j ACCEPT' % (protocol, port))
        os.system('iptables -I FORWARD -s 10.8.0.0/24 -j ACCEPT')
        os.system('iptables -F')
        os.system('iptables -I FORWARD -m state --state RELATED,ESTABLISHED -j ACCEPT')


def build_service_openvpn() -> None:
    if os.system('pgrep systemd-journal') == 0:
        os.system('systemctl restart openvpn@server.service')
    else:
        os.system('/etc/init.d/openvpn restart')


def openvpn_install() -> None:
    if not confirm_ip_address():
        return

    port = get_port_openvpn()
    protocol = get_protocol_openvpn()
    dns = get_dns_openvpn()

    if not port or not protocol or not dns:
        return

    update_package()
    install_packages()
    setup_dir()
    download_easyrsa()
    build_easyrsa()
    build_server_config(port, protocol, dns)
    build_ip_forward()
    build_rc_local()
    build_iptables(IP_ADDRESS, port, protocol)
    build_service_openvpn()
    create_ovpn_client()


def uninstall_openvpn() -> None:
    os.system('rm -rf /etc/openvpn')
    os.system('rm -rf /etc/openvpn/easy-rsa')
    os.system('rm -rf /etc/openvpn/ipp.txt')

    if os.system('pgrep systemd-journal') == 0:
        os.system('systemctl stop openvpn')
        os.system('systemctl disable openvpn')
        os.system('systemctl daemon-reload')
    else:
        os.system('/etc/init.d/openvpn stop')
        os.system('update-rc.d -f openvpn remove')

    os.system('apt-get purge openvpn -y')
    os.system('apt-get autoremove -y')
    os.system('apt-get clean -y')
