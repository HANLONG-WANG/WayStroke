#!/usr/bin/python3
"""Unprivileged probe controller. No evdev dependency in the client."""
import argparse
import json
import socket
import time

SOCKET = '/run/waystroke-input-probe/control.sock'


def request(q):
    with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as connection:
        connection.settimeout(10)
        connection.connect(SOCKET)
        connection.send(json.dumps(q).encode())
        value = json.loads(connection.recv(16384))
        if 'error' in value:
            raise RuntimeError(value['error'])
        return value


def main():
    parser = argparse.ArgumentParser(description='WayStroke mouse-input capability probe')
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('devices')
    sub.add_parser('status')
    sub.add_parser('stop')
    watch = sub.add_parser('watch')
    watch.add_argument('device', help='/dev/input/eventN from devices')
    watch.add_argument('--seconds', type=int, default=60)
    args = parser.parse_args()
    try:
        if args.action == 'devices':
            response = request({'action': 'devices'})
            devices = response['devices']
            for d in devices:
                print(f"{d['path']}  {d['name']}  {d['phys']}")
            for d in response.get('rejected', []):
                print(f"跳过 {d['path']} {d['name']}：{d['reason']}")
            if not devices:
                print('没有找到符合条件的相对鼠标；触摸板不在本次验证范围内。')
        elif args.action == 'status':
            print(json.dumps(request({'action': 'status'}), ensure_ascii=False, indent=2))
        elif args.action == 'stop':
            print(request({'action': 'disarm'})['note'])
        else:
            request({'action': 'arm', 'device': args.device, 'seconds': args.seconds})
            print('验证已开始：普通右键点击应正常；按住右键画轨迹应被消耗，不弹菜单。', flush=True)
            print('仅记录相对距离与辅助键，不执行动作。Ctrl+C 停止；断开后最多 3 秒释放。', flush=True)
            sequence = 0
            try:
                while True:
                    state = request({'action': 'poll'})
                    if not state['armed']:
                        print(state['note'], flush=True)
                        break
                    for record in state['records']:
                        if record['sequence'] > sequence:
                            print(json.dumps(record, ensure_ascii=False), flush=True)
                            sequence = record['sequence']
                    time.sleep(.02)
            finally:
                request({'action': 'disarm'})
    except KeyboardInterrupt:
        print('\n验证已停止。')
    except (OSError, RuntimeError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
