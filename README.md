# singverse-model

SingVerse 的模型下载与离线导入包仓库。模型集中放在本项目 **Git tag 对应的 GitHub Release 附件**中，Git 只保存清单、转换与发布脚本，不保存权重。

模型包独立于应用版本发布，使用 `vMAJOR.MINOR.PATCH`。下载入口固定为：

```text
https://github.com/mynora-dot/singverse-model/releases/download/<tag>/<asset>
```

以下命名用于包含本次变更的新正式 Release，历史版本的附件名和地址保留。消费端固定使用已完成发布的 tag 和 SHA-256，不跟随 `latest`；文中的 `v1.0.0` 仅作命令示例，以实际完成发布的版本为准。

## 下载哪个模型

发布页用中文说明用途和设备，下载后的文件名使用对应的英文名称。通常只需选择自己要用的功能和设备，无需下载全部附件。

| 发布页中文名称 | 适用场景与设备 | 实际下载文件 | 后台对应模型 |
| --- | --- | --- | --- |
| 原唱与伴奏识别-通用版.zip | 识别已有音轨中的人声，辅助判断原唱和伴奏；CPU，无需显卡 | `singverse-track-recognition-universal.zip` | 快速人声分类模型 |
| 标准伴奏生成-通用版.th | 分离人声与乐器并生成伴奏；CPU、NVIDIA / AMD 显卡、Apple 芯片 | `singverse-accompaniment-universal.th` | 标准分离模型 |
| 标准伴奏生成-Intel显卡版.zip | 在 Intel 显卡上分离人声并生成伴奏 | `singverse-accompaniment-intel.zip` | Intel 优化模型 |
| 轻量人声伴奏分离-通用版.zip | 轻量两轨分离、独立 CPU 参考试跑，以及后台支持的加速设备 | `singverse-vocal-accompaniment-universal.zip` | 轻量两轨分离模型 |
| 人声伴奏分离-瑞芯微版.zip | 瑞芯微 RK3566 / RK3568 / RK3588，导入时自动选择当前芯片 | `singverse-vocal-accompaniment-rockchip.zip` | 瑞芯微 NPU 分离模型 |

在后台的模型管理页面找到表格中的对应模型，点击“离线导入”，直接选择下载的 `.zip` 或 `.th`，无需解压或改名。分离模型安装后仍需在目标设备完成试跑。快速识别模型用于判断已有音轨，不负责生成伴奏。

## 当前模型统计

统计日期：2026-11-20。依据 `singverse-compute@eac462b633bc666020f23bd749f43d4a8c88b2d2` 的固定清单与下载脚本核对，共 **5 类模型、7 个硬件版本**；需要取得 **5 个上游文件**，另由 ONNX 转换 **3 个 RKNN 文件**。完整来源、字节数及摘要见 [models.lock.json](models.lock.json)。

模型 ID、固定上游版本和权重摘要保留在固定清单中；用途名称不再使用上游模型缩写或提交哈希。后台导入包见上表。

5 个上游文件合计 **243,575,315 B**。CPU、CUDA、ROCm、MPS 等后端会复用权重，不按运行时重复下载。TensorRT engine、OpenVINO 编译缓存、CoreML / MLX 的设备转换缓存由节点按环境生成，不作为通用权重发布。FFmpeg、Python、Torch、ONNX Runtime 和驱动属于工具或运行环境，不计入模型清单。外部 AI 服务的远端大模型由服务提供方管理，本仓库不下载其权重。

RKNN 包包含三个芯片的六个文件：

```text
rk3566/manifest.json
rk3566/uvr.rknn
rk3568/manifest.json
rk3568/uvr.rknn
rk3588/manifest.json
rk3588/uvr.rknn
```

节点根据设备树选择自己的两个文件。RKNN 与 ONNX 分别安装；AI 干净档和独立 CPU 参考试跑仍需 ONNX 文件。转换与导入成功不授予推理资格，安装后继续在目标设备执行模型试跑。

## 每个 tag 的附件

共 13 个附件：上表的 4 个 ZIP、5 个原始文件、瑞芯微包校验码及 3 个说明或清单文件。标准伴奏的 `.th` 同时是原始权重和导入文件，只发布一份；其余原始权重的中文显示名注明“原始模型文件”，供程序下载和高级用途使用。

```text
singverse-track-recognition-universal.pth
singverse-accompaniment-universal.th
singverse-accompaniment-intel.xml
singverse-accompaniment-intel.bin
singverse-vocal-accompaniment-universal.onnx
singverse-track-recognition-universal.zip
singverse-accompaniment-intel.zip
singverse-vocal-accompaniment-universal.zip
singverse-vocal-accompaniment-rockchip.zip
singverse-vocal-accompaniment-rockchip.zip.sha256
models.json
SHA256SUMS
THIRD_PARTY_NOTICES.md
```

`models.json` 记录 tag、固定清单摘要、各附件的版本化下载地址、大小与 SHA-256，以及 RKNN 各芯片的转换来源和文件摘要。`schemaVersion` 仍为 1，新增模型 `displayName`、适用设备 `devices`、后台导入项 `importTarget` 和附件 `label`。原始文件的 `name` 继续表示缓存及安装时的规范名称，新增 `assetName` 表示实际发布名称，`url` 指向该发布名称，使用者应直接读取 URL，不能根据 `name` 拼接下载地址。

`SHA256SUMS` 覆盖除自身之外的所有附件；RKNN 的 `.sha256` 可直接用于后台“下载到节点”的完整包摘要。三个标准文件名保留，发布页分别显示“模型清单（程序使用）”“文件完整性校验（可选）”“第三方来源与许可”。GitHub 自动提供的 Source code（源码）压缩包不包含模型。

普通 ZIP 根目录只放该模型约定的原始文件；OpenVINO 同时包含 XML 和 BIN。ZIP 内部继续使用 `Cnn6_mAP=0.343.pth`、`htdemucs_fwd.xml`、`htdemucs_fwd.bin`、`UVR_MDXNET_9482.onnx` 等规范名称，外部下载文件改名不影响原有导入规则。署名和许可说明作为独立附件分发，避免加入 ZIP 后被 compute 的严格导入规则拒绝。

下载某个已完成发布的版本：

```sh
tag=v1.0.0
gh release download "$tag" --repo mynora-dot/singverse-model --dir "downloads/$tag"
cd "downloads/$tag"
shasum -a 256 -c SHA256SUMS
```

也可在对应 Release 页面只下载所需模型。在线 RKNN 安装填写本仓固定 tag 的 ZIP 地址，并从同一版本的 `.sha256` 或 `models.json` 取得完整包 SHA-256。

## 本地生成

下载、打包脚本只需要 Python 3.12+ 标准库。新建转换环境需要 **Linux x86_64 / Python 3.12**；[requirements-rknn.lock](requirements-rknn.lock) 固定转换依赖与下载摘要，Torch 使用 CPU wheel，不安装 CUDA 运行库。

```sh
python3.12 scripts/models.py list
python3.12 scripts/models.py fetch
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-rknn.lock
.venv/bin/python scripts/models.py convert
python3.12 scripts/models.py bundle --tag v1.0.0 --output dist/v1.0.0
python3.12 scripts/models.py verify --tag v1.0.0 --output dist/v1.0.0
```

`fetch` 只访问固定清单中的上游来源，按文件大小和完整 SHA-256 校验，在 `.cache/upstream` 原子保存。`--reuse-dir <directory>` 可重复指定，显式复用已下载文件；不隐式依赖相邻项目。已有文件不匹配会停止，不覆盖它们。

`convert` 对固定 ONNX 执行 batch 1、`[1,4,2048,256]`、不量化转换，输出 `.cache/rknn/<chip>/{manifest.json,uvr.rknn}`。已有转换文件必须通过相同来源、工具链、芯片及摘要检查。也可显式复用已验证的转换目录，在 macOS 上直接打包：

```sh
python3.12 scripts/models.py bundle --tag v1.0.0 --output dist/v1.0.0 \
  --rknn-dir /absolute/path/to/converted-models
```

打包在临时目录完成后才公开输出目录，拒绝覆盖已有输出。相同输入的 ZIP 使用固定时间、文件顺序和权限，不受源文件修改时间影响；RKNN 工具的重新转换可能生成不同字节，转换来源与实际摘要记录在每次发布清单中。

维护转换依赖时，在 Linux x86_64 / Python 3.12 环境修改 `requirements-rknn.in`，用 `uv==0.9.17` 执行 `uv pip compile requirements-rknn.in --python-version 3.12 --generate-hashes --output-file requirements-rknn.lock`，然后实际转换并检查导入兼容性。

## 发布工作流

[model-release.yml](.github/workflows/model-release.yml) 与现有 SingVerse 项目一致，只响应正式 Release 的 `published` 事件，不响应普通 push、PR、草稿或预发布。仅推送 tag 不会构建模型。

该流程需要 Release 在发布后仍允许添加附件；若启用了 GitHub 不可变 Release，预检会明确停止，须改用发布前上传附件的流程。

1. 将审查后的源码提交并推送到本仓，创建带中文变更说明的 `vMAJOR.MINOR.PATCH` 注释标签和 Release 草稿，再在 GitHub 发布。[中文标签与发布说明](https://github.com/mynora-dot/singverse-go-backend/blob/main/docs/multi-repository.md#中文标签与发布说明)
2. `build` 检出准确 tag 的提交，核对正式 Release，下载并验证 5 个上游文件，安装隔离的转换依赖，生成三芯片 RKNN 文件及全部附件。
3. 将完整发布目录保存为 30 天的 Actions artifact；`publish` 下载同一份字节、检查完整校验和，再上传到该 tag 的 Release，为所有附件设置中文显示名，并生成置顶下载指南。

仅 `publish` job 有 `contents: write`，使用内置 `github.token`，不需要额外密钥。上传前检查所有同名资产；相同摘要跳过文件上传并按需补齐中文标签，不同内容拒绝覆盖。下载指南列出用途、设备、后台导入项与直达下载链接，使用 `<!-- singverse-model-downloads:start -->` / `<!-- singverse-model-downloads:end -->` 标记管理，只替换自己的区块，保留手写发布说明；重试不会重复插入。上传文件、补齐标签和更新指南成功后，最后上传 `models.json`，作为完整模型发布的标记。消费者应等工作流成功后再接入。

上传失败时使用 GitHub Actions 的 **Re-run failed jobs**，保留成功的 build 产物。重新转换会改变已发布内容时必须使用新 tag；不使用 `--clobber` 替换旧模型。

## compute 接入

包含新命名的 Release 完整可用后，再将 compute 的固定下载源切到该 tag，避免节点提前访问不存在的地址。模型 ID、安装文件名、版本、字节数和原始摘要沿用固定清单；下载地址读取本次 Release 的 `files[].url`，其附件名与 `files[].name` 不再相同。

需要一起更新的位置：

| compute 文件 | 接入方式 |
| --- | --- |
| `singverse_compute/application/audio_catalog.py` | 把每个原始文件的 `url` 改为同一模型 tag 的 `files[].url`；保留 `name`、大小和摘要 |
| `singverse_compute/application/audio_models.py` | 基准 HTDemucs 还有独立的 `URL` 常量，应改为读取上述清单，避免仍从 Meta 下载 |
| `scripts/setup-uvr-model.py` | UVR 安装脚本还有独立来源，应改为读取清单 |
| `scripts/setup-audio-model.py` / `scripts/setup-fast-audio-model.py` | 已读取清单，跟随清单切换 |
| RKNN 后台在线安装 | 使用该 tag 的通用 ZIP 地址及完整包 SHA-256，沿用已有显式下载接口 |

所有处理任务继续只读取本地已安装权重。模型安装后依然需要环境检测与真实试跑，不在用户播放或后台歌曲处理期间隐式联网取模型。

第三方来源、署名和使用条件见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)；本轮工作与验证记录见 [WORKLOG.md](WORKLOG.md)。
