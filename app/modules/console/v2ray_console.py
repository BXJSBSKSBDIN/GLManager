import typing as t
import os
import json

import uuid
import time

from console import Console, FuncItem, COLOR_NAME
from console.formatter import create_menu_bg, create_line

from app.utilities.logger import logger
from app.utilities.v2ray_config_template import config as v2ray_config_template

V2RAY_CMD_INSTALL = 'bash -c \'bash <(curl -L -s https://multi.netlify.app/go.sh)\' -f'
V2RAY_CONFIG_PATH = '/etc/v2ray/config.json'


def create_uuid(name: str = time.time()) -> str:
    if not isinstance(name, str):
        name = str(name)

    return str(uuid.uuid5(uuid.NAMESPACE_DNS, name))


class V2RayConfig:
    def __init__(self) -> None:
        self.config_path = V2RAY_CONFIG_PATH
        self.config_data = {}

    def load(self) -> dict:
        if not os.path.exists(self.config_path):
            self.create(port=5555, protocol='vless')

        with open(self.config_path, 'r') as f:
            self.config_data = json.load(f)

        return self.config_data

    def save(self, config_data: dict) -> None:
        with open(self.config_path, 'w') as f:
            json.dump(config_data, f, indent=4)

    def create(self, port: int, protocol: str) -> None:
        v2ray_config_template['inbounds'][1]['port'] = port
        v2ray_config_template['inbounds'][1]['protocol'] = protocol
        self.save(v2ray_config_template)


class V2RayManager:
    def __init__(self) -> None:
        self.config = V2RayConfig()

    @staticmethod
    def install() -> bool:
        cmd = V2RAY_CMD_INSTALL
        status = os.system(cmd) == 0

        if status:
            V2RayConfig().create(port=5555, protocol='vless')
            V2RayManager.restart()

        return status

    @staticmethod
    def uninstall() -> bool:
        os.system('rm -rf /etc/v2ray')
        os.system('rm -rf /usr/bin/v2ray/')

        V2RayManager.stop()

        return not V2RayManager.is_installed()

    @staticmethod
    def is_installed() -> bool:
        return os.path.exists('/usr/bin/v2ray/v2ray')

    @staticmethod
    def is_running() -> bool:
        cmd = 'ps -ef | grep v2ray | grep -v grep'
        return os.system(cmd) == 0

    @staticmethod
    def start() -> bool:
        cmd = 'systemctl start v2ray'
        return os.system(cmd) == 0

    @staticmethod
    def stop() -> bool:
        cmd = 'systemctl stop v2ray'
        return os.system(cmd) == 0

    @staticmethod
    def restart() -> bool:
        cmd = 'systemctl restart v2ray'
        return os.system(cmd) == 0

    def get_running_port(self) -> int:
        config_data = self.config.load()
        return config_data['inbounds'][1]['port']

    def change_port(self, port: int) -> bool:
        config_data = self.config.load()
        config_data['inbounds'][1]['port'] = port

        self.config.save(config_data)
        self.restart()

        return self.is_running()

    def create_new_uuid(self, name: str = time.time()) -> str:
        config_data = self.config.load()
        uuid = create_uuid(name)

        config_data['inbounds'][1]['settings']['clients'].append(
            {
                'id': uuid,
                'flow': 'xtls-rprx-direct',
            }
        )

        self.config.save(config_data)
        self.restart()
        return uuid

    def remove_uuid(self, uuid: str) -> None:
        config_data = self.config.load()
        config_data['inbounds'][1]['settings']['clients'] = [
            client
            for client in config_data['inbounds'][1]['settings']['clients']
            if client['id'] != uuid
        ]

        self.config.save(config_data)
        self.restart()

    def get_uuid_list(self) -> t.List[str]:
        config_data = self.config.load()
        return [client['id'] for client in config_data['inbounds'][1]['settings']['clients']]


class V2RayActions:
    v2ray_manager = V2RayManager()

    @staticmethod
    def install(callback: t.Callable) -> None:
        logger.info('Instalando V2Ray...')
        status = V2RayActions.v2ray_manager.install()

        if status:
            logger.info('V2Ray instalado com sucesso!')
        else:
            logger.error('Falha ao instalar V2Ray!')

        Console.pause()
        callback(status)

    @staticmethod
    def uninstall(callback: t.Callable) -> None:
        logger.info('Desinstalando V2Ray...')
        status = V2RayActions.v2ray_manager.uninstall()

        if status:
            logger.info('V2Ray desinstalado com sucesso!')
        else:
            logger.error('Falha ao desinstalar V2Ray!')

        Console.pause()
        callback(status)

    @staticmethod
    def start(callback: t.Callable) -> None:
        logger.info('Iniciando V2Ray...')
        status = V2RayActions.v2ray_manager.start()

        if status:
            logger.info('V2Ray iniciado com sucesso!')
        else:
            logger.error('Falha ao iniciar V2Ray!')

        Console.pause()
        callback(status)

    @staticmethod
    def stop(callback: t.Callable) -> None:
        logger.info('Parando V2Ray...')
        status = V2RayActions.v2ray_manager.stop()

        if status:
            logger.info('V2Ray parado com sucesso!')
        else:
            logger.error('Falha ao parar V2Ray!')

        Console.pause()
        callback(status)

    @staticmethod
    def restart(callback: t.Callable) -> None:
        logger.info('Reiniciando V2Ray...')
        status = V2RayActions.v2ray_manager.restart()

        if status:
            logger.info('V2Ray reiniciado com sucesso!')
        else:
            logger.error('Falha ao reiniciar V2Ray!')

        Console.pause()
        callback(status)

    @staticmethod
    def change_port() -> None:
        v2ray_manager = V2RayActions.v2ray_manager

        current_port = v2ray_manager.get_running_port()
        logger.info(f'Porta atual: {current_port}')

        try:
            port = None
            while port is None:
                port = input(COLOR_NAME.YELLOW + 'Porta: ' + COLOR_NAME.RESET)

                try:
                    if not port.isdigit() or int(port) < 1 or int(port) > 65535:
                        raise ValueError

                    port = int(port)
                    if port == v2ray_manager.get_running_port():
                        logger.error('Porta já em uso!')
                        port = None

                except ValueError:
                    logger.error('Porta inválida!')
                    port = None

            if v2ray_manager.change_port(port):
                logger.info(f'Porta alterada para {port}')
            else:
                logger.error('Falha ao alterar porta!')

        except KeyboardInterrupt:
            return

        Console.pause()

    @staticmethod
    def create_uuid() -> None:
        v2ray_manager = V2RayActions.v2ray_manager
        uuid = v2ray_manager.create_new_uuid()
        logger.info(f'UUID criado: {uuid}')

        Console.pause()

    @staticmethod
    def remove_uuid() -> None:
        v2ray_manager = V2RayActions.v2ray_manager
        uuid_list = v2ray_manager.get_uuid_list()
        logger.info(f'UUIDs disponíveis: {uuid_list}')

        try:
            uuid = None
            while uuid is None:
                uuid = input(COLOR_NAME.YELLOW + 'UUID: ' + COLOR_NAME.RESET)

                if uuid not in uuid_list:
                    logger.error('UUID inválido!')
                    uuid = None

            v2ray_manager.remove_uuid(uuid)
            logger.info(f'UUID removido: {uuid}')

        except KeyboardInterrupt:
            return

        Console.pause()

    @staticmethod
    def get_uuid_list() -> None:
        v2ray_manager = V2RayActions.v2ray_manager
        uuid_list = v2ray_manager.get_uuid_list()
        logger.info(f'UUIDs disponíveis: {uuid_list}')

        Console.pause()


def v2ray_console_main():
    console = Console('V2Ray Manager')
    actions = V2RayActions()

    def console_callback(is_restart) -> None:
        if is_restart:
            console.exit()
            v2ray_console_main()

    if not actions.v2ray_manager.is_installed():
        console.append_item(FuncItem('INSTALAR V2RAY', actions.install, console_callback))
        console.show()
        return

    if not V2RayManager.is_running():
        console.append_item(FuncItem('INICIAR V2RAY', actions.start, console_callback))

    if V2RayManager.is_running():
        console.append_item(FuncItem('PARAR V2RAY', actions.stop, console_callback))
        console.append_item(FuncItem('REINICIAR V2RAY', actions.restart, console_callback))

    console.append_item(FuncItem('ALTERAR PORTA', actions.change_port))
    console.append_item(FuncItem('CRIAR NOVO UUID', actions.create_uuid))
    console.append_item(FuncItem('REMOVER UUID', actions.remove_uuid))
    console.append_item(FuncItem('LISTAR UUID\'S', actions.get_uuid_list))

    console.append_item(FuncItem('DESINSTALAR V2RAY', actions.uninstall, console_callback))
    console.show()