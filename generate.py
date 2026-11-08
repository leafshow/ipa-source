#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IPA 软件源生成器
扫描 ipas/ 目录下的 .ipa 文件，提取应用信息与图标，生成：
  - apps.json    AltStore v2 格式（易签 ESign / 轻松签 / 全能签 / Feather / LiveContainer 兼容）
  - scarlet.json Scarlet 格式
  - index.html   网页浏览页
  - icons/       从 IPA 中提取的应用图标
  - *.ipa        复制到输出目录，保证下载链接可用

用法:
  python3 generate.py --base http://127.0.0.1:8899/ --out out
  python3 generate.py --base https://USER.github.io/ipa-source/ --out out
"""
import argparse, os, shutil, sys, zipfile, plistlib
from datetime import datetime, timezone
from urllib.parse import quote
import json
import html

def ustr(x, fallback):
    return x if isinstance(x, str) and x else fallback

def find_plist_and_icon(zf):
    """定位 Payload/xxx.app/ 的 Info.plist 与最大图标"""
    names = zf.namelist()
    app_dir = None
    for n in names:
        if n.startswith("Payload/") and n.count("/") == 1 and n.endswith(".app/"):
            app_dir = n
            break
    if not app_dir:
        # 兼容无尾斜杠的条目
        for n in names:
            if n.startswith("Payload/") and ".app/" in n:
                app_dir = n.split(".app/")[0] + ".app/"
                break
    if not app_dir:
        return None, None
    plist_name = app_dir + "Info.plist"
    if plist_name not in names:
        return None, None
    # 找图标：优先 AppIcon 相关，其次任意 png，取体积最大的
    icon = None; icon_size = -1
    for n in names:
        if n.startswith(app_dir) and n.lower().endswith(".png"):
            base = os.path.basename(n).lower()
            score = 0
            if "appicon" in base or base.startswith("icon"): score = 1
            sz = zf.getinfo(n).file_size
            if sz > icon_size or (score == 1 and icon_size < sz * 4):
                if sz > icon_size or (score == 1 and icon_size >= 0 and sz >= icon_size / 4):
                    icon, icon_size = n, sz
    return plist_name, icon

def parse_ipa(path, icons_dir):
    try:
        zf = zipfile.ZipFile(path)
    except Exception as e:
        print("  [跳过] 无法读取 zip: %s (%s)" % (path, e))
        return None
    plist_name, icon_entry = find_plist_and_icon(zf)
    if not plist_name:
        print("  [跳过] 找不到 Payload/*/Info.plist: %s" % path)
        return None
    try:
        info = plistlib.loads(zf.read(plist_name))
    except Exception as e:
        print("  [跳过] Info.plist 解析失败: %s (%s)" % (path, e))
        return None
    stem = os.path.splitext(os.path.basename(path))[0]
    bid = ustr(info.get("CFBundleIdentifier"), "")
    name = ustr(info.get("CFBundleDisplayName"), ustr(info.get("CFBundleName"), stem))
    ver = ustr(info.get("CFBundleShortVersionString"), ustr(info.get("CFBundleVersion"), "1.0"))
    minos = info.get("MinimumOSVersion", "12.0")
    icon_url = ""
    if icon_entry:
        try:
            os.makedirs(icons_dir, exist_ok=True)
            icon_file = os.path.join(icons_dir, "%s.png" % quote(bid or stem, safe=""))
            with open(icon_file, "wb") as f:
                f.write(zf.read(icon_entry))
            icon_url = "icons/" + os.path.basename(icon_file)
        except Exception as e:
            print("  [提示] 图标提取失败: %s" % e)
    mtime = os.path.getmtime(path)
    return {
        "name": name, "bid": bid or stem, "version": ver,
        "minos": str(minos), "icon_url": icon_url,
        "date": datetime.fromtimestamp(mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mtime": mtime, "size": os.path.getsize(path), "file": os.path.basename(path),
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ipas", default="ipas", help="IPA 文件夹 (默认 ipas/)")
    ap.add_argument("--out", default="out", help="输出目录 (默认 out/)")
    ap.add_argument("--base", required=True, help="最终访问的基础 URL，需以 / 结尾")
    ap.add_argument("--name", default="我的 IPA 源", help="源名称")
    ap.add_argument("--dev", default="SelfHosted", help="开发者署名")
    ap.add_argument("--tint", default="0e7afe", help="主题色 HEX (不带 #)")
    ap.add_argument("--website", default="", help="主页 URL")
    args = ap.parse_args()
    base = args.base if args.base.endswith("/") else args.base + "/"

    ipas = sorted(f for f in os.listdir(args.ipas) if f.lower().endswith(".ipa")) if os.path.isdir(args.ipas) else []
    if not ipas:
        print("在 %s 中没有找到 .ipa 文件" % args.ipas); sys.exit(1)

    os.makedirs(args.out, exist_ok=True)
    icons_dir = os.path.join(args.out, "icons")
    metas = []
    print("解析 %d 个 IPA..." % len(ipas))
    for fn in ipas:
        m = parse_ipa(os.path.join(args.ipas, fn), icons_dir)
        if m:
            metas.append(m)
            # 复制 IPA 到输出目录（同目录则跳过）
            src = os.path.join(args.ipas, fn); dst = os.path.join(args.out, fn)
            if os.path.abspath(src) != os.path.abspath(dst):
                shutil.copy2(src, dst)
            print("  [OK] %s  %s %s (%.1f MB)" % (m["name"], m["bid"], m["version"], m["size"] / 1048576))
    if not metas:
        print("没有可用的 IPA"); sys.exit(1)

    # 可选 urls.json：文件名 → 外部直链（GitHub Releases 大文件、蓝奏云等）
    url_map = {}
    for cand in ("urls.json", os.path.join(args.out, "urls.json")):
        if os.path.isfile(cand):
            with open(cand, encoding="utf-8") as f:
                url_map.update(json.load(f))

    def dl_url(fn): return url_map.get(fn) or (base + quote(fn))
    def icon_abs(rel): return base + quote(rel) if rel else ""
    if url_map:
        print("  [外链] %d 个文件使用外部直链" % len(url_map))

    # ---- AltStore v2 (apps.json)：同一 bundleIdentifier 合并为多版本 ----
    apps_map = {}
    for m in metas:
        a = apps_map.setdefault(m["bid"], {
            "name": m["name"], "bundleIdentifier": m["bid"],
            "developerName": args.dev, "localizedDescription": m["name"] + "（自建源）",
            "iconURL": icon_abs(m["icon_url"]), "tintColor": args.tint,
            "permissions": [], "versions": [],
            # v1 兼容字段
            "version": m["version"], "date": m["date"],
            "downloadURL": dl_url(m["file"]), "size": m["size"],
        })
        a["versions"].append({
            "version": m["version"], "date": m["date"],
            "localizedDescription": m["file"], "downloadURL": dl_url(m["file"]),
            "size": m["size"], "minOSVersion": m["minos"], "_mtime": m["mtime"],
        })
    # 版本从新到旧（同日期按文件修改时间）
    for a in apps_map.values():
        a["versions"].sort(key=lambda v: v["_mtime"], reverse=True)
        for v in a["versions"]:
            del v["_mtime"]
        a["version"] = a["versions"][0]["version"]; a["date"] = a["versions"][0]["date"]
        a["downloadURL"] = a["versions"][0]["downloadURL"]; a["size"] = a["versions"][0]["size"]
    apps = sorted(apps_map.values(), key=lambda a: a["name"])
    altstore = {
        "name": args.name,
        "iconURL": apps[0]["iconURL"] or "",
        "website": args.website or base,
        "tintColor": args.tint, "apps": apps,
    }
    with open(os.path.join(args.out, "apps.json"), "w", encoding="utf-8") as f:
        json.dump(altstore, f, ensure_ascii=False, indent=1)

    # ---- Scarlet (scarlet.json)：每个 IPA 一条 ----
    scarlet = {
        "name": args.name, "iconURL": altstore["iconURL"],
        "apps": [{
            "name": m["name"], "bundleIdentifier": m["bid"], "developerName": args.dev,
            "version": m["version"], "versionDate": m["date"],
            "versionDescription": m["file"], "downloadURL": dl_url(m["file"]),
            "size": m["size"], "iconURL": icon_abs(m["icon_url"]),
        } for m in metas],
    }
    with open(os.path.join(args.out, "scarlet.json"), "w", encoding="utf-8") as f:
        json.dump(scarlet, f, ensure_ascii=False, indent=1)

    # ---- 全能签原生格式 (appstore)：每个 IPA 一条，type/lock/isLanZouCloud ----
    qnq = {
        "name": args.name, "message": "自建 IPA 源",
        "identifier": args.name, "sourceURL": base + "appstore",
        "sourceicon": altstore["iconURL"], "payURL": "", "unlockURL": "",
        "apps": [{
            "name": m["name"], "type": 0,
            "version": m["version"], "versionDate": m["date"],
            "versionDescription": m["file"], "lock": "0",
            "downloadURL": dl_url(m["file"]), "isLanZouCloud": False,
            "iconURL": icon_abs(m["icon_url"]), "tintColor": args.tint,
            "size": m["size"],
        } for m in metas],
    }
    native = json.dumps(qnq, ensure_ascii=False, indent=1)
    for fn in ("appstore", "appstore.json"):
        with open(os.path.join(args.out, fn), "w", encoding="utf-8") as f:
            f.write(native)

    # ---- index.html ----
    rows = "".join(
        "<tr><td>%s</td><td>%s</td><td>%s</td><td>%.1f MB</td>"
        "<td><a href='%s'>下载</a></td></tr>" % (
            html.escape(m["name"]), html.escape(m["version"]),
            html.escape(m["bid"]), m["size"] / 1048576, dl_url(m["file"]))
        for m in metas)
    page = ("<!doctype html><meta charset=utf-8><title>%s</title>"
            "<body style='font-family:-apple-system;background:#111;color:#eee;max-width:640px;margin:2em auto;padding:0 1em'>"
            "<h2>📦 %s</h2><p>签名软件添加源：</p>"
            "<p>全能签（原生格式）：<b>%sappstore</b></p>"
            "<p>易签/轻松签/Feather（AltStore 格式）：<b>%sapps.json</b></p>"
            "<p>Scarlet：<b>%sscarlet.json</b></p>"
            "<table border=0 cellpadding=6 style='border-collapse:collapse;width:100%%'>"
            "<tr style='color:#888'><th align=left>应用</th><th>版本</th><th>BundleID</th><th>大小</th><th></th></tr>%s</table></body>"
            % (args.name, args.name, html.escape(base), html.escape(base),
               html.escape(base), rows))
    with open(os.path.join(args.out, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)

    print("\n✅ 生成完成 → %s" % os.path.abspath(args.out))
    print("   全能签源(原生):        %sappstore" % base)
    print("   易签/轻松签/Feather:   %sapps.json" % base)
    print("   Scarlet 源:            %sscarlet.json" % base)

if __name__ == "__main__":
    main()
