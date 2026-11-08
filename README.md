# 自建 iOS 签名软件源（IPA 源）

把一个装满 `.ipa` 的文件夹变成签名软件可以加载的「软件源」。
生成的 `apps.json` 兼容 **AltStore v2 格式**——这是易签 / 轻松签 / 全能签 / Feather / LiveContainer 等签名工具的事实标准；同时生成 Scarlet 专用格式。

## 项目结构

```
ipa-source/
├── generate.py      # 生成器：扫描 ipas/ → 提取元数据 → 生成源文件
├── server.sh        # 一键启动本地源服务 (端口 8899)
├── ipas/            # ← 把你的 .ipa 文件放这里
└── out/             # ← 生成的可部署网站（apps.json / scarlet.json / index.html / icons/ / *.ipa）
```

## 使用

### 1. 放入 IPA
把 `.ipa` 文件放进 `ipas/`，然后：

```sh
python3 generate.py --ipas ipas --out out \
  --base http://127.0.0.1:8899/ \
  --name "我的 IPA 源"
```

- `--base`：下载链接前缀。本地模式用 `http://127.0.0.1:8899/`，GitHub Pages 用 `https://用户名.github.io/仓库名/`
- `--name`：源名称；`--dev` 开发者名；`--tint` 主题色（可选）
- 同一 bundleIdentifier 的多个版本会自动合并成一个应用的多版本列表（新的在前）

### 2A. 本地模式（手机离线用，iSH）

```sh
sh server.sh        # 或: cd out && python3 -m http.server 8899
```

然后在签名软件「软件源 / 源」里添加：

| 软件 | 添加的地址 | 格式 |
|---|---|---|
| **全能签** | `http://127.0.0.1:8899/appstore` | 全能签原生格式（`type`/`lock`/`isLanZouCloud`，无 bundleIdentifier） |
| 易签 / 轻松签 / Feather / LiveContainer | `http://127.0.0.1:8899/apps.json` | AltStore v2 |
| Scarlet | `http://127.0.0.1:8899/scarlet.json` | Scarlet JSON |

注意：
- **后缀无所谓**：全能签官方源 `https://qnq.nuosike.cn/appstore` 没有 .json，Content-Type 还是 text/html —— 它只解析 JSON 内容。`appstore` 和 `appstore.json` 等价，都已生成
- iSH 退到后台会被系统冻结、服务即停。操作顺序：iSH 起服务 → 立刻切签名软件 → 粘贴地址 → 确认，一气呵成；之后只有点「下载」那一刻需要服务在线
- 验证服务是否活着：Safari 打开 `http://127.0.0.1:8899/appstore`，能看到 JSON 就说明服务正常，问题在签名软件端
- 签名软件和 iSH 在同一台手机上，`127.0.0.1` 直达，**完全离线可用**

### 2B. GitHub Pages 模式（公开分享）

1. 新建 GitHub 仓库（如 `my-ipa-source`）
2. 把 `out/` 目录的全部内容（appstore、apps.json、icons/、所有 .ipa）推上去
3. Settings → Pages → Branch 选 `main` / `(root)` → Save
4. 源地址（按签名软件选）：
   - 全能签：`https://你的用户名.github.io/my-ipa-source/appstore`
   - 易签/轻松签/Feather：`https://你的用户名.github.io/my-ipa-source/apps.json`
   - Scarlet：`https://你的用户名.github.io/my-ipa-source/scarlet.json`

### 使用流程（部署完成后）

1. 签名软件 → 软件源 → 添加上面的地址 → 刷新，列表出现应用和图标
2. 点应用 → 下载 IPA（走源里的 downloadURL）
3. 下载完成 → 选择证书 → 签名安装（签名由证书决定，跟源无关）
4. **更新应用**：新 IPA 放进 `ipas/` → 重新跑 generate.py → push 到 GitHub → 签名软件里下拉刷新源即可看到新版本

## GitHub 单文件 100MB 限制怎么办？

GitHub 仓库单文件超 100MB 直接拒收（>50MB 警告）。解决优先级：

**① GitHub Releases（推荐，免费且不限流量）**
- Release 资产单文件上限 **2GB**，不占仓库体积，直链稳定
- 操作：仓库 → Releases → Draft a new release → 上传大 IPA → Publish → 复制资产直链，形如
  `https://github.com/用户名/仓库/releases/download/v1.0/应用-1.0.ipa`
- 在项目根目录建 `urls.json` 做映射，生成器会自动用外链替换下载地址：

  ```json
  {
    "大应用-2.0.ipa": "https://github.com/用户名/仓库/releases/download/v2.0/大应用-2.0.ipa",
    "更大的应用-1.0.ipa": "https://github.com/用户名/仓库/releases/download/v1.0/更大的应用-1.0.ipa"
  }
  ```

- 小 IPA（<50MB）继续放仓库直出，大 IPA 放 Releases，互不影响

**② 蓝奏云（国内免费，全能签原生支持）**
- 全能签 app 字段有 `isLanZouCloud` 标记，蓝奏云分享直链可以直接填进 urls.json
- 免费单文件 ≤100MB；下载链接需为直链格式

**③ Git LFS（不推荐）**
- 免费额度仅 1GB 存储 + 1GB/月 流量，IPA 源很容易超

**④ 其他对象存储**：Cloudflare R2（10GB 免费）、腾讯 COS / 阿里 OSS（便宜稳定），直链填 urls.json 即可

国内下载 GitHub 直链慢的话，可在 urls.json 里给链接加加速前缀（如 gh-proxy 类镜像），直链变成 `https://镜像域名/https://github.com/...`。

仓库整体建议 <1GB，纯 JSON/icons 仓库几乎不占空间（IPA 都在 Releases）。

## 兼容性说明

- 易签 / 轻松签 / 全能签 / Feather：不校验源签名，直接可用 ✅
- AltStore / SideStore 官方客户端要求源带 Ed25519 签名，未签名 JSON 可能提示不受信任 ⚠️
- 这是 IPA 下载源（签名软件用），不是 Cydia/Sileo 的 apt 源；要 apt 源参考 DCRM / repo.me

## 参考项目

- [tomoya06/esign-tmy-sources](https://github.com/tomoya06/esign-tmy-sources) — GitHub Actions 全自动同步的自建源范例
- [victordedomenico/awesome-altstore](https://github.com/victordedomenico/awesome-altstore) — AltStore 源合集
- [ParadoxEpoch/altstore-repo-transformer](https://github.com/ParadoxEpoch/altstore-repo-transformer) — AltStore 源转易签格式
