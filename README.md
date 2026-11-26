# ComfyUI 可迁移基础环境

同一份仓库可以在 Cloud Studio 或普通 Linux GPU 云主机安装。运行时从私有备份目录读取模型、节点和工作流。Git 仓库只保存自己的安装脚本与所需的上游版本。ComfyUI 源码由安装脚本从官方仓库获取。 [ComfyUI 手动安装文档](https://docs.comfy.org/installation/manual_install)

## 在 Linux 云主机恢复

准备 Git、Python 3.11（含 `venv`）以及与 PyTorch 兼容的 NVIDIA 驱动。基础版本与旧工作区相同。默认安装 CUDA 13.0 版 PyTorch，新主机驱动对应其他版本时可给 `install` 加 `--torch-index`，使用该主机对应的 [PyTorch 官方安装源](https://pytorch.org/get-started/locally/)。只做 CPU 验证时，给安装和启动命令都加 `--cpu`。

把完整备份放在目标主机的持久磁盘上。备份中若有 `portable-support.tar`，在备份目录里用 `tar -xf portable-support.tar` 解包一次。这个压缩包保留了自定义节点的原始目录大小写，建议在 Linux 上解包。保留 `models/`、`custom_nodes/`、`input/`、`user/` 和清单的相对位置，再进入本仓库目录执行下面的命令。

```bash
export COMFY_DATA_DIR=/path/to/comfyui-backup
python3 portable.py verify
python3 portable.py install --node-dependencies
python3 portable.py start
```

启动默认只监听本机 `127.0.0.1:8188`。普通云主机可经 SSH 转发后访问本机的 `http://127.0.0.1:8188`，或使用云平台带身份验证的入口。

```bash
ssh -N -L 8188:127.0.0.1:8188 user@cloud-host
```

## 在 Cloud Studio 恢复

从模板新建应用或导入本仓库，完成上面的校验和安装。若使用 IDE 的「运行」，把 `examples/cloudstudio-preview.yml` 复制为 `.vscode/preview.yml`，并在 `run` 前设置实际 `COMFY_DATA_DIR`。样例让预览代理连到 8188，先在端口管理确认该端口「仅自己可见」。用自己的浏览器验证私有预览能打开，再搬大量模型。 [Cloud Studio 运行配置](https://cloudstudio.net/docs/guide/quick_start/developer/how-to-run/) · [端口与访问权限](https://cloudstudio.net/docs/guide/code_editing/productivity_plugin/port-plug/)

## 恢复后检查

先确认模型清单逐文件通过，在画布里打开常用工作流，检查加载节点的模型名和 LoRA 下拉选项。个别自定义节点可能还需要系统软件或针对目标 GPU 安装额外依赖。节点来源和旧版本见备份里的 `environment.json`，节点文件快照由备份提供。原工作区的临时运行文件和账户配置可以分别归档在自己的私有存储中。
