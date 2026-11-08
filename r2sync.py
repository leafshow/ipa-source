#!/usr/bin/env python3
"""ipas/*.ipa 转存 Cloudflare R2，并自动维护 urls.json 映射（纯标准库，SigV4 手写签名）。

环境变量（前 4 个缺失则自动跳过转存）：
  R2_ACCOUNT_ID / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_BUCKET
  R2_PUBLIC_BASE  公开访问基址（自定义域名或 pub-xxx.r2.dev，不含尾斜杠）
用法：python3 r2sync.py [ipas目录] [urls.json路径]
"""
import hashlib, hmac, json, os, sys, urllib.request
from datetime import datetime, timezone
from urllib.parse import quote

ENV_KEYS = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID",
            "R2_SECRET_ACCESS_KEY", "R2_BUCKET", "R2_PUBLIC_BASE")


def signing_key(secret, date):
    k = hmac.new(("AWS4" + secret).encode(), date.encode(), hashlib.sha256).digest()
    k = hmac.new(k, b"auto", hashlib.sha256).digest()
    k = hmac.new(k, b"s3", hashlib.sha256).digest()
    return hmac.new(k, b"aws4_request", hashlib.sha256).digest()


def r2_put(cfg, key, data):
    host = cfg["R2_ACCOUNT_ID"] + ".r2.cloudflarestorage.com"
    path = "/" + cfg["R2_BUCKET"] + "/" + quote(key)
    now = datetime.now(timezone.utc)
    amzdate = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    ph = hashlib.sha256(data).hexdigest()
    signed_headers = "host;x-amz-content-sha256;x-amz-date"
    canonical = "\n".join([
        "PUT", path, "",
        "host:" + host,
        "x-amz-content-sha256:" + ph,
        "x-amz-date:" + amzdate, "",
        signed_headers, ph])
    scope = datestamp + "/auto/s3/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amzdate, scope,
                         hashlib.sha256(canonical.encode()).hexdigest()])
    sig = hmac.new(signing_key(cfg["R2_SECRET_ACCESS_KEY"], datestamp),
                   to_sign.encode(), hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        "https://" + host + path, data=data, method="PUT",
        headers={"Host": host, "x-amz-date": amzdate,
                 "x-amz-content-sha256": ph,
                 "Authorization": "AWS4-HMAC-SHA256 Credential=%s/%s, SignedHeaders=%s, Signature=%s" % (
                     cfg["R2_ACCESS_KEY_ID"], scope, signed_headers, sig)})
    with urllib.request.urlopen(req, timeout=600) as f:
        return f.status

def remote_size(base, key):
    """返回远端对象大小；不存在/未配置公开访问返回 -1"""
    if not base:
        return -1
    try:
        req = urllib.request.Request(base.rstrip("/") + "/" + quote(key), method="HEAD")
        with urllib.request.urlopen(req, timeout=20) as f:
            return int(f.headers.get("Content-Length") or -1)
    except Exception:
        return -1


def main():
    cfg = {k: os.environ.get(k, "") for k in ENV_KEYS}
    missing = [k for k in ENV_KEYS[:4] if not cfg[k]]
    if missing:
        print("[R2] 未配置(%s)，跳过转存" % ",".join(missing))
        return
    ipas_dir = sys.argv[1] if len(sys.argv) > 1 else "ipas"
    urls_file = sys.argv[2] if len(sys.argv) > 2 else "urls.json"
    files = sorted(f for f in os.listdir(ipas_dir) if f.lower().endswith(".ipa"))
    if not files:
        print("[R2] 没有可转存的 IPA")
        return
    base = cfg["R2_PUBLIC_BASE"].rstrip("/")
    try:
        url_map = json.load(open(urls_file, encoding="utf-8"))
    except Exception:
        url_map = {}
    for fn in files:
        size = os.path.getsize(os.path.join(ipas_dir, fn))
        if remote_size(base, fn) == size:
            print("[R2] 已存在，跳过:", fn)
        else:
            data = open(os.path.join(ipas_dir, fn), "rb").read()
            st = r2_put(cfg, fn, data)
            if st != 200:
                print("[R2] ❌ 上传失败(HTTP %s): %s" % (st, fn))
                continue
            print("[R2] ✅ 已上传: %s (%.1f MB)" % (fn, size / 1048576))
        if base:
            url_map[fn] = base + "/" + quote(fn)
    if base:
        json.dump(url_map, open(urls_file, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print("[R2] urls.json 已更新，共 %d 条映射" % len(url_map))


if __name__ == "__main__":
    main()
