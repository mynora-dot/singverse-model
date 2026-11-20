# 第三方模型来源与署名

这些权重来自各自上游，版权和使用条件归原作者所有。`models.lock.json` 记录原始下载地址、固定 revision、字节数和 SHA-256；每个 Release 的 `models.json` 记录本次实际分发文件及转换文件的摘要。本仓库不重新授权第三方权重。

## PANNs Cnn6

- 作品：PANNs: Large-Scale Pretrained Audio Neural Networks for Audio Pattern Recognition (Pretrained Models)。
- 作者：Qiuqiang Kong、Yin Cao、Turab Iqbal、Yuxuan Wang、Wenwu Wang、Mark D. Plumbley。
- 来源：<https://zenodo.org/records/3987831>，DOI `10.5281/zenodo.3987831`。
- 文件：`Cnn6_mAP=0.343.pth`，原样镜像；ZIP 仅改变容器格式。
- 许可：Creative Commons Attribution 4.0 International (CC BY 4.0)，<https://creativecommons.org/licenses/by/4.0/>；许可全文 <https://creativecommons.org/licenses/by/4.0/legalcode>。
- 作者未为 SingVerse 背书。模型权重与 PANNs 推理代码的许可分别适用。

## HTDemucs 与 OpenVINO 转换

- 原作者：Meta Platforms, Inc. and affiliates；Demucs / Alexandre Défossez 等贡献者。
- 源项目：<https://github.com/facebookresearch/demucs>。
- HTDemucs 权重 `955717e8-8726e21a.th` 原样镜像。
- OpenVINO IR 由 Intel 提供，原样镜像固定 revision `efb3d2bc54f93899b13b72b12c57001e19f09ae2` 的 `htdemucs_v4/htdemucs_fwd.xml`、`htdemucs_fwd.bin`。
- 模型卡及来源：<https://huggingface.co/Intel/demucs-openvino/tree/efb3d2bc54f93899b13b72b12c57001e19f09ae2>，模型卡声明 MIT。

MIT License

Copyright (c) Meta Platforms, Inc. and affiliates.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## UVR MDXNet 9482 与 RKNN 派生文件

- UVR / Ultimate Vocal Remover：Anjok07、aufr33 及项目贡献者；MDX-Net 原始架构来自 KUIELAB / Woosung Choi。
- 上游项目和模型说明：<https://github.com/Anjok07/ultimatevocalremovergui>。
- 固定 ONNX 的实际来源：<https://github.com/k2-fsa/sherpa-onnx/releases/tag/source-separation-models>，文件 `UVR_MDXNET_9482.onnx` 原样镜像。
- RK3566、RK3568、RK3588 的 `uvr.rknn` 由同一固定 ONNX 经 `rknn-toolkit2==2.3.2` 转换，固定 batch 1，不量化。转换不改变原权重的使用条件；转换工具和板端运行库不在模型包中分发。
- 保留当前 SingVerse compute 清单的使用范围：个人使用，模型、训练数据及商业使用条件仍须按上游说明独立确认。UVR README 对第三方应用使用其模型要求保留 UVR 和开发者署名；不将其 GUI 代码的 MIT 说明替代每份模型的使用条件。

离线导入 ZIP 必须恰好包含 compute 约定的模型文件，不能在其中增加本说明；本说明随 Release 作为独立附件提供。
