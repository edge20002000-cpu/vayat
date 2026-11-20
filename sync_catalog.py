"""
ڤايات طحينة — مزامنة كتالوج واتساب/الميتا مع الموقع
====================================================
 btch كل ما تضيف أو تعدّل منتج في الكتالوج، شغّل الملف ده:
     python sync_catalog.py

هيقرأ products.js الجديد ويستخدمه الموقع تلقائياً.

الإعداد: افتح config.json واكتب فيه:
  catalog_id   = رقم الكتالوج من Meta Commerce Manager
  access_token = System User Token بصلاحية catalogs_read
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE, "config.json")
OUTPUT_JS = os.path.join(BASE, "products.js")
OUTPUT_JSON = os.path.join(BASE, "catalog.json")
DATA_JSON = os.path.join(BASE, "data.json")
IMAGES_DIR = os.path.join(BASE, "images")

ARABIC_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def to_arabic_num(text):
    return str(text).translate(ARABIC_DIGITS)


def format_price(product, currency):
    """Meta بترجع السعر كـ [{'amount': '4500', 'currency': 'EGP'}] بالـ minor units."""
    prices = product.get("price") or []
    if not prices:
        return "السعر عند الطلب"
    p = prices[0]
    try:
        amount = float(p.get("amount", 0)) / 100.0
    except (TypeError, ValueError):
        return "السعر عند الطلب"
    cur = p.get("currency") or currency or ""
    label = "ج.م" if cur.upper() in ("EGP", "") else cur
    if amount == int(amount):
        value = str(int(amount))
    else:
        value = f"{amount:.2f}".rstrip("0").rstrip(".")
    return f"{to_arabic_num(value)} {label}"


def fetch_catalog(cfg):
    version = cfg.get("api_version", "v21.0").strip("/")
    cid = str(cfg.get("catalog_id", "")).strip()
    token = str(cfg.get("access_token", "")).strip()

    if not cid or "ضع_" in cid:
        raise ValueError("لازم تكتب catalog_id في config.json")
    if not token or "ضع_" in token:
        raise ValueError("لازم تكتب access_token في config.json")

    fields = "id,name,description,price,image_url,availability,retailer_id,brand,currency"
    url = (
        f"https://graph.facebook.com/{version}/{urllib.parse.quote(cid)}/products"
        f"?fields={urllib.parse.quote(fields)}"
        f"&limit=500&access_token={urllib.parse.quote(token)}"
    )

    items = []
    while url:
        req = urllib.request.Request(url, headers={"User-Agent": "VayatCatalogSync/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            raise RuntimeError(f"خطأ من Meta ({e.code}): {body[:600]}") from e
        except Exception as e:
            raise RuntimeError(f"تعذر الاتصال بـ Meta: {e}") from e

        items.extend(payload.get("data", []))
        url = (payload.get("paging") or {}).get("next")
    return items


def download_image(url, filename):
    """ينزّل صورة المنتج محلياً عشان الرابط ما ينتهيش بعد كده."""
    if not url:
        return ""
    try:
        os.makedirs(IMAGES_DIR, exist_ok=True)
        path = os.path.join(IMAGES_DIR, filename)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 VayatCatalogSync"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        if len(data) < 100:
            return ""
        with open(path, "wb") as f:
            f.write(data)
        return "images/" + filename
    except Exception:
        return url  # يفضّل الرابط الأصلي لو النزّل فشل


def build_products(items, cfg):
    products = []
    for i, raw in enumerate(items):
        name = (raw.get("name") or "منتج بدون اسم").strip()
        available = raw.get("availability") == "available"
        tag = "متوفر الآن ✅" if available else "غير متوفر مؤقتاً"
        pid = str(raw.get("id") or f"product-{i + 1}")
        safe = "".join(c for c in pid if c.isalnum() or c in "-_")[:60]
        local_image = download_image(raw.get("image_url"), safe + ".jpg")
        products.append({
            "name": name,
            "price": format_price(raw, cfg.get("currency")),
            "desc": (raw.get("description") or "منتج طبيعي من ڤايات.").strip(),
            "tag": tag,
            "c1": cfg.get("default_c1", "#f0d09a"),
            "c2": cfg.get("default_c2", "#c98f4f"),
            "label": name[:22],
            "sub": f"كتالوج واتساب • {to_arabic_num(i + 1)}",
            "image": local_image,
            "images": [local_image] if local_image else [],
            "catalog_id": raw.get("id", ""),
        })
    return products


def write_outputs(products, cfg):
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    whatsapp = str(cfg.get("whatsapp", "201286008717")).strip()

    js = (
        "/* ملف منتجات ڤايات — مولّد تلقائياً من كتالوج الميتا بواسطة sync_catalog.py */\n"
        f"/* آخر مزامنة: {stamp} */\n"
        f"window.VAYAT_SYNCED_AT = {json.dumps(stamp)};\n\n"
        f"window.VAYAT_PRODUCTS = {json.dumps(products, ensure_ascii=False, indent=2)};\n\n"
        f'window.VAYAT_WHATSAPP = "{whatsapp}";\n'
    )
    with open(OUTPUT_JS, "w", encoding="utf-8") as f:
        f.write(js)

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"synced_at": stamp, "products": products}, f, ensure_ascii=False, indent=2)

    # data.json هو الملف اللي الموقع المنشور بيقرأه مباشرة (GitHub Pages)
    current = {}
    if os.path.exists(DATA_JSON):
        try:
            with open(DATA_JSON, encoding="utf-8") as f:
                current = json.load(f)
        except Exception:
            current = {}
    current["products"] = products
    current["syncedAt"] = stamp
    current.setdefault("texts", {})
    current.setdefault("settings", {"whatsapp": whatsapp})
    with open(DATA_JSON, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=2)

    return stamp


def main():
    print("جارٍ قراءة الإعدادات...")
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        print(f"تعذر قراءة config.json: {e}")
        sys.exit(1)

    try:
        items = fetch_catalog(cfg)
    except Exception as e:
        print(f"\n❌ {e}")
        sys.exit(1)

    if not items:
        print("⚠️ الكتالوج فاضي أو مفيش منتجات متاحة للقراءة.")
        sys.exit(0)

    products = build_products(items, cfg)
    stamp = write_outputs(products, cfg)

    print(f"✅ تمت مزامنة {len(products)} منتج بنجاح.")
    print(f"   آخر مزامنة: {stamp}")
    print("   الملفات المحدّثة: products.js , catalog.json , data.json")
    print("   افتح index.html هتلاقي المنتجات من الكتالوج ظاهرة تلقائياً.")


if __name__ == "__main__":
    main()
