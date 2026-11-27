import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import venv
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parent
LOCK = json.loads((ROOT / 'runtime-lock.json').read_text(encoding='utf-8'))
CORE = ROOT / 'runtime' / 'ComfyUI'
VENV = ROOT / '.venv'
PYTHON = VENV / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def git_value(directory, *args):
    return subprocess.check_output(['git', '-C', str(directory), *args], text=True).strip()


def install_core():
    upstream = LOCK['comfyui']
    if CORE.exists():
        if (Path(git_value(CORE, 'rev-parse', '--show-toplevel')).resolve() != CORE
                or git_value(CORE, 'rev-parse', 'HEAD') != upstream['commit']
                or git_value(CORE, 'status', '--porcelain', '--untracked-files=no')):
            raise ValueError(f'已有源码目录与锁定版本不一致，请检查 {CORE}')
        return
    CORE.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=CORE.parent, prefix='.checkout-') as scratch:
        checkout = Path(scratch) / 'ComfyUI'
        subprocess.run(['git', 'init', str(checkout)], check=True)
        subprocess.run(['git', '-C', str(checkout), 'remote', 'add', 'origin', upstream['url']], check=True)
        subprocess.run(['git', '-C', str(checkout), 'fetch', '--depth=1', 'origin', upstream['commit']], check=True)
        if git_value(checkout, 'rev-parse', 'FETCH_HEAD') != upstream['commit']:
            raise ValueError('远端返回的 ComfyUI 版本与锁定版本不一致')
        subprocess.run(['git', '-C', str(checkout), 'checkout', '--detach', 'FETCH_HEAD'], check=True)
        checkout.rename(CORE)


def requirements(data):
    if data is None:
        return []
    if not data.is_dir():
        raise ValueError(f'数据目录不存在 {data}')
    return sorted((data / 'custom_nodes').glob('*/requirements.txt'))


def install(args, data):
    node_requirements = requirements(data) if args.node_dependencies else []
    ref = LOCK['reference']
    index = args.torch_index or ('https://download.pytorch.org/whl/cpu' if args.cpu else ref['torch_index'])
    packages = ref['torch_packages']
    install_core()
    if not PYTHON.is_file():
        venv.EnvBuilder(with_pip=True).create(VENV)
    accelerator = VENV / 'portable-torch-index.txt'
    if accelerator.exists() and accelerator.read_text(encoding='utf-8').strip() != index:
        raise ValueError('此虚拟环境已绑定另一种 PyTorch 软件源。切换 CPU 或 GPU 时请使用新的仓库副本。')
    pip = [str(PYTHON), '-m', 'pip', '--disable-pip-version-check']
    subprocess.run([*pip, 'install', '--index-url', index, *packages], check=True)
    accelerator.write_text(index + '\n', encoding='utf-8')
    core_requirements = CORE / 'requirements.txt'
    if args.skip_example_templates:
        pinned_templates = f"comfyui-workflow-templates=={ref['workflow_templates']}"
        lines = core_requirements.read_text(encoding='utf-8').splitlines()
        if lines.count(pinned_templates) != 1:
            raise ValueError('上游示例模板依赖与锁定版本不一致')
        lines.remove(pinned_templates)
        core_requirements = VENV / 'portable-core-requirements.txt'
        core_requirements.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    files = [core_requirements, *node_requirements]
    flags = [flag for path in files for flag in ('-r', str(path))]
    constraints = VENV / 'portable-constraints.txt'
    constraints.write_text('\n'.join(packages) + '\n', encoding='utf-8')
    subprocess.run([*pip, 'install', '-c', str(constraints), *flags], cwd=CORE, check=True)
    subprocess.run([*pip, 'check'], check=True)


def verify(data):
    if data is None:
        raise ValueError('用 --data 指定包含模型清单的备份目录')
    for filename in ('model-manifest.json', 'support-manifest.json'):
        items = json.loads((data / filename).read_text(encoding='utf-8'))
        if not isinstance(items, list) or not items:
            raise ValueError(f'备份清单为空 {filename}')
        seen = set()
        for item in items:
            path = PurePosixPath(item['path'])
            if (not path.parts or path.parts[0] not in {'models', 'custom_nodes', 'user', 'input'}
                    or '..' in path.parts or '\\' in str(path) or ':' in str(path)
                    or path in seen or not re.fullmatch(r'[a-f0-9]{64}', item['sha256'])):
                raise ValueError(f'清单含有不可用的文件路径 {path}')
            seen.add(path)
            target = data.joinpath(*path.parts).resolve(strict=True)
            if not target.is_relative_to(data) or target.stat().st_size != item['size']:
                raise ValueError(f'文件大小或位置与备份不一致 {path}')
            digest = hashlib.sha256()
            with target.open('rb') as stream:
                for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
                    digest.update(block)
            if digest.hexdigest() != item['sha256']:
                raise ValueError(f'文件内容与备份不一致 {path}')
        print(f'{filename} 已核对 {len(items)} 个文件')


def start(args, data):
    if not PYTHON.is_file() or not (CORE / 'main.py').is_file():
        raise ValueError('先运行 python3 portable.py install')
    if data is None:
        data = ROOT / 'data'
        data.mkdir(exist_ok=True)
    if not data.is_dir():
        raise ValueError(f'数据目录不存在 {data}')
    (data / 'custom_nodes').mkdir(exist_ok=True)
    cmd = [str(PYTHON), str(CORE / 'main.py'), '--base-directory', str(data),
           '--listen', args.listen, '--port', str(args.port), '--disable-auto-launch']
    if args.cpu:
        cmd.append('--cpu')
    if args.lowvram:
        cmd.append('--lowvram')
    if os.name == 'nt':
        raise SystemExit(subprocess.run(cmd, cwd=CORE).returncode)
    os.chdir(CORE)
    os.execv(PYTHON, cmd)


def main():
    parser = argparse.ArgumentParser(description='可迁移的 ComfyUI 基础环境')
    parser.add_argument('--data', type=Path, default=os.environ.get('COMFY_DATA_DIR'), help='模型与工作流目录')
    actions = parser.add_subparsers(dest='action', required=True)
    setup = actions.add_parser('install', help='安装锁定的 ComfyUI 基础环境')
    setup.add_argument('--cpu', action='store_true', help='安装 CPU 版 PyTorch')
    setup.add_argument('--torch-index', help='与云主机驱动兼容的 PyTorch 官方软件源')
    setup.add_argument('--node-dependencies', action='store_true', help='一并安装备份中自定义节点声明的依赖')
    setup.add_argument('--skip-example-templates', action='store_true', help='跳过官方示例模板库，仍可加载自己的工作流')
    actions.add_parser('verify', help='按清单核对模型、工作流和节点文件')
    run = actions.add_parser('start', help='启动画布')
    run.add_argument('--cpu', action='store_true')
    run.add_argument('--lowvram', action='store_true')
    run.add_argument('--listen', default='127.0.0.1')
    run.add_argument('--port', type=int, default=8188)
    args = parser.parse_args()
    data = Path(args.data).expanduser().resolve() if args.data else None
    if args.action == 'install' and args.node_dependencies and data is None:
        parser.error('--node-dependencies 需要 --data 或 COMFY_DATA_DIR')
    try:
        if args.action == 'install':
            install(args, data)
        elif args.action == 'verify':
            verify(data)
        else:
            start(args, data)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
