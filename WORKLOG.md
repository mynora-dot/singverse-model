# 工作记录

## 2026-11-20：集中模型下载与 tag 发布

目标：盘点当前 SingVerse 需要下载的模型，在 `mynora-dot/singverse-model` 的 Git tag / GitHub Release 中统一提供原始权重、离线导入包和校验清单。

盘点依据为 `singverse-compute@eac462b633bc666020f23bd749f43d4a8c88b2d2`。覆盖当前固定模型清单、原生安装脚本、管理端导入规则和已有 RKNN 转换产物；其他项目调用 compute 或外部 AI 服务，没有另行固定下载的推理权重。

| 项目 | 数量 / 处理结果 |
| --- | --- |
| 模型类别 | 5：PANNs Cnn6、HTDemucs、HTDemucs OpenVINO、UVR MDXNet ONNX、UVR MDXNet RKNN |
| 硬件版本 | 7：前四类各 1 个，RKNN 分 RK3566 / RK3568 / RK3588 三个版本 |
| 上游文件 | 5 个，合计 243,575,315 B，保持 compute 固定大小与 SHA-256 |
| 派生权重 | 3 个芯片专用 `uvr.rknn`，各配 `manifest.json` |
| 模型下载附件 | 5 个原始文件 + 4 个严格格式的离线 ZIP |
| 版本约定 | 独立 `vMAJOR.MINOR.PATCH`，首个计划版本 `v1.0.0` |

已完成：

- 新建项目说明、固定模型清单和第三方署名说明。
- 实现固定来源下载、本地缓存复用、完整 SHA-256 与文件大小检查。
- 实现 RKNN-Toolkit2 2.3.2 的三芯片转换、转换产物校验和严格 ZIP 打包。
- 实现 Release 元数据、版本化下载地址、完整校验和与 RKNN 包摘要生成。
- 编写正式 Release 发布后构建、保留构建产物、再上传的两阶段 Actions 工作流；同名不同内容不覆盖。
- 在 README 中列明 compute 的后续接入点，包含清单外的两个硬编码下载入口。

本轮验证：

- 5 个上游文件已全部集中到本项目 `.cache/upstream/`，逐一通过固定大小与 SHA-256 校验。OpenVINO BIN 初次传输被截断；核对 Hugging Face 固定 revision 的 LFS 元数据后确认原清单正确，补齐传输后摘要一致。下载器增加有界重试及 HTTPS 字节范围续传，最终仍执行完整摘要检查。
- RK3566 / RK3568 / RK3588 的已有真实转换文件经源摘要、工具链、芯片、大小和文件摘要核对后，复制到本项目 `.cache/rknn/`；未修改 compute 原始文件。
- 通过隔离 Linux amd64 / Python 3.12 环境解析 26 个转换依赖，生成带完整 SHA-256 的 `requirements-rknn.lock`。本轮未重新安装完整转换环境或重新运行 RKNN 转换。
- 本地单元测试 13 项通过：覆盖缓存与损坏文件、截断续传、严格 ZIP 布局、稳定打包字节、版本与来源检查、不可变 Release、上传前冲突检查及失败重试。
- 工作流 YAML 可解析，核对正式 Release 触发、准确源码检出与上传 job 的权限范围；不在 Actions 中增加独立测试或 lint job。
- 已生成本地候选发布目录 `dist/v1.0.0/`，共 13 个附件，完整校验和全部通过。这只是本地候选包，不表示远端已有该版本。
- 使用当前 `singverse-compute` 的真实安装代码，对 4 个普通模型和模拟 RK3566 / RK3568 / RK3588 设备树的 3 个 RKNN 目标，执行真实文件导入；7 组均成功，原始权重和转换模型摘要保持一致，均未自动获得推理资格。机器记录保存于 `.cache/compute-import-verification.json`。

本地通用 RKNN ZIP 的 SHA-256：

```text
7ef78b3676096de79917847e1607ba6190843e3f78034d6c20b4d428134e74ae
```

本轮 ZIP 使用固定文件顺序与时间戳，摘要与 compute 先前生成的 ZIP 不同；内部模型字节及三个芯片各自的 manifest 摘要均保持一致。后续由 Actions 重新转换的包必须使用该次 Release 自带的摘要，不能沿用这个本地候选包摘要。

未执行远端 GitHub Actions、NPU 初始化或真实板端推理、速度与音质验收。7 组导入验证覆盖包格式与安装行为，不能代替板端模型试跑。

远端状态：本轮只读核对时 `mynora-dot/singverse-model` 为公开空仓库，没有 Release。尚未推送源码、创建 tag 或发布 Release；`v1.0.0` 是计划版本。首个 Release 可下载后再切换 compute 下载地址，本轮没有将运行节点指向不存在的附件。
