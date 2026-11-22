# -*- coding: utf-8 -*-
"""
جامع مزادات عُمان — يقرأ كل منصات المزادات الإلكترونية ويصنفها ويرتبها.
يشتغل على GitHub Actions كل ساعة، ويكتب docs/data.json للصفحة.
"""
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

MUSCAT = timezone(timedelta(hours=4))
NOW = datetime.now(MUSCAT)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
HDR = {"User-Agent": UA, "Accept-Language": "ar,en;q=0.8"}
OUT = "docs/data.json"
DEBUG = "docs/debug.json"

# المنصات اللي تحتاج متصفح (جافاسكربت)
JS_SITES = [
    {"key": "mzadcom", "name": "مزادكم", "desc": "مركبات حكومية وشركات، معدات، خردة، أرقام مميزة",
     "pages": ["https://www.mzadcom.om/auctions?sec=main&type=active",
               "https://www.mzadcom.om/auctions?sec=main&type=upcoming",
               "https://www.mzadcom.om/?type=auctions"],
     "detail": "https://www.mzadcom.om/auction-details/{id}"},
    {"key": "rop", "name": "مزادات شرطة عُمان", "desc": "مركبات محجوزة ومنقولات الشرطة",
     "pages": ["https://rop.mzadcom.om/auctions", "https://rop.mzadcom.om/"],
     "detail": "https://rop.mzadcom.om/auction-details/{id}"},
    {"key": "safqa", "name": "صفقة للمزادات", "desc": "عقارات ومركبات ومنقولات حكومية",
     "pages": ["https://safqaauctions.om/", "https://safqaauctions.om/auctions"]},
    {"key": "mazadoman", "name": "مزاد عُمان", "desc": "منقولات ومركبات جهات حكومية",
     "pages": ["https://mazad.om/auctions", "https://mazad.om/"],
     "extra": ["https://mazad.om/auctions?cat=Real%20Estate&view=1", "https://mazad.om/auctions?cat=Cars&view=1",
               "https://mazad.om/auctions?cat=Various%20Items&view=1", "https://mazad.om/auctions?cat=Animals&view=1"]},
    {"key": "bidproc", "name": "bidproc", "desc": "معدات وخردة ومركبات شركات",
     "pages": ["https://bidproc.com/", "https://bidproc.com/events"]},
    {"key": "mctbids", "name": "MCTBids", "desc": "سيارات مستعملة ومتضررة",
     "pages": ["https://www.mctbids.com/", "https://www.mctbids.com/auctions"]},
    {"key": "muscatauction", "name": "Muscat Auction", "desc": "سيارات فاخرة وعقارات وسلع",
     "pages": ["https://www.muscatauction.com/"]},
]

# ---------------------------------------------------------------- أدوات
AR_MONTHS = {"يناير": 1, "فبراير": 2, "مارس": 3, "أبريل": 4, "ابريل": 4, "مايو": 5, "يونيو": 6,
             "يوليو": 7, "أغسطس": 8, "اغسطس": 8, "سبتمبر": 9, "أكتوبر": 10, "اكتوبر": 10,
             "نوفمبر": 11, "ديسمبر": 12}
EN_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")

GOVS = {
    "مسقط": ["مسقط", "مطرح", "بوشر", "السيب", "العامرات", "قريات", "المعبيلة", "الخوض", "روي", "الغبرة",
             "الموالح", "الحيل", "الخوير", "الوطية", "القرم", "الأنصب", "الجفنين", "حلبان", "سندان",
             "muscat", "seeb", "bausher", "mutrah", "amerat", "ruwi", "ghubrah", "mabela", "rusayl"],
    "شمال الباطنة": ["صحار", "صحم", "شناص", "لوى", "الخابورة", "السويق", "sohar", "saham", "shinas", "liwa", "suwaiq"],
    "جنوب الباطنة": ["الرستاق", "بركاء", "المصنعة", "نخل", "وادي المعاول", "العوابي", "barka", "rustaq", "musannah", "nakhal"],
    "الداخلية": ["نزوى", "بهلاء", "أدم", "الحمراء", "منح", "إزكي", "سمائل", "بدبد", "nizwa", "bahla", "izki", "samail", "sumail"],
    "شمال الشرقية": ["إبراء", "المضيبي", "بدية", "القابل", "وادي بني خالد", "دماء والطائيين", "ibra", "mudhaibi"],
    "جنوب الشرقية": ["صور", "جعلان", "مصيرة", "الكامل", "sur", "jalan", "masirah"],
    "الظاهرة": ["عبري", "ينقل", "ضنك", "ibri"],
    "البريمي": ["البريمي", "محضة", "السنينة", "buraimi"],
    "ظفار": ["صلالة", "طاقة", "مرباط", "ثمريت", "رخيوت", "ضلكوت", "المزيونة", "سدح", "عوقد", "salalah", "dhofar", "thumrait"],
    "الوسطى": ["الدقم", "هيماء", "محوت", "الجازر", "duqm", "haima"],
    "مسندم": ["خصب", "دبا", "بخا", "مدحاء", "khasab", "musandam"],
}

CAT_WORDS = [
    ("num", r"أرقام|ارقام|رقم مميز|أرقام مميزة|لوحة|لوحات|ماسي|ذهبي|diamond|gold number|plate|vip number|special number|mobile number"),
    ("car", r"سيار|مركب|شاحن|باص|حافل|دراج|بيك ?أب|بيكب|تويوتا|نيسان|لكزس|هوندا|هيونداي|كيا|ميتسوبيشي|فورد|شفروليه|"
            r"جيب|مرسيدس|بي ام|لاندكروزر|هايلكس|كامري|كورولا|باترول|رافعة شوكية|"
            r"vehicle|car\b|cars\b|truck|bus\b|pickup|pick-up|toyota|nissan|lexus|honda|hyundai|kia|ford|"
            r"mitsubishi|chevrolet|mercedes|bmw|land cruiser|hilux|corolla|camry|patrol|prado|suv|sedan|motorcycle"),
    ("land", r"أرض|ارض|أراضي|عقار|سكني|تجاري|زراعي|صناعي|سياحي|شقة|فيلا|منزل|بناية|مبنى|قطعة|"
             r"land|plot|villa|apartment|property|real estate|building"),
]
CAT_ORDER = ["num", "car", "land"]


def clean(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def num(s):
    s = str(s).translate(AR_DIGITS)
    m = re.search(r"\d[\d,]*(?:\.\d+)?", s)
    if not m:
        return None
    try:
        v = float(m.group(0).replace(",", ""))
        return int(v) if v == int(v) else v
    except ValueError:
        return None


def guess_cat(text):
    t = (text or "").lower()
    for k, rx in CAT_WORDS:
        if re.search(rx, t):
            return k
    return "proj"


def guess_gov(text):
    t = (text or "").lower()
    for gov, words in GOVS.items():
        for w in words:
            if w.lower() in t:
                place = w if not w.isascii() else w.title()
                return gov, place
    return None, None


def parse_time(s):
    m = re.search(r"(\d{1,2}):(\d{2})\s*(AM|PM|ص|م|صباحا|مساء)?", s, re.I)
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2)), (m.group(3) or "").lower()
    if ap in ("pm", "م", "مساء") and h < 12:
        h += 12
    if ap in ("am", "ص", "صباحا") and h == 12:
        h = 0
    return h, mi


def find_dates(text):
    """كل التواريخ في النص مع الساعة إن وجدت: [(datetime, label_before)]"""
    t = text.translate(AR_DIGITS)
    out = []
    pats = [
        (r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", lambda m: (int(m[3]), int(m[2]), int(m[1]))),
        (r"(\d{4})-(\d{1,2})-(\d{1,2})", lambda m: (int(m[1]), int(m[2]), int(m[3]))),
        (r"(\d{1,2})\s+(" + "|".join(AR_MONTHS) + r"),?\s+(\d{4})", lambda m: (int(m[3]), AR_MONTHS[m[2]], int(m[1]))),
        (r"(\d{1,2})\s+([A-Za-z]{3})[a-z]*\.?,?\s+(\d{4})",
         lambda m: (int(m[3]), EN_MONTHS.get(m[2].lower()[:3], 0), int(m[1]))),
    ]
    for rx, f in pats:
        for m in re.finditer(rx, t):
            try:
                y, mo, d = f(m)
                if not (2024 <= y <= 2030 and 1 <= mo <= 12 and 1 <= d <= 31):
                    continue
                after = t[m.end():m.end() + 25]
                hm = parse_time(after) or (9, 0)
                dt = datetime(y, mo, d, hm[0], hm[1], tzinfo=MUSCAT)
                label = t[max(0, m.start() - 30):m.start()]
                out.append((dt, label))
            except (ValueError, KeyError):
                pass
    return out


def countdown(text):
    """'يبدأ بعد 2 يوم 5 ساعة 46 دقيقة' أو '6 days, 14 hours, 17 minutes' → (timedelta, kind)"""
    t = text.translate(AR_DIGITS)
    rx = (r"(\d+)\s*(?:يوم|أيام|ايام|days?|d)\W*\s*(\d+)\s*(?:ساعة|ساعات|hours?|h)\W*\s*(\d+)\s*(?:دقيقة|دقائق|minutes?|m)")
    m = re.search(rx, t, re.I)
    if not m:
        return None, None
    td = timedelta(days=int(m[1]), hours=int(m[2]), minutes=int(m[3]))
    before = t[max(0, m.start() - 25):m.start()]
    kind = "start" if re.search(r"يبدأ|starts?|begins?", before, re.I) else "end"
    return td, kind


def find_price(text):
    t = text.translate(AR_DIGITS)
    for rx in [r"(?:السعر الحالي|المزايدة الحالية|current price|current bid|أعلى مزايدة)\D{0,6}(\d[\d,]*(?:\.\d+)?)",
               r"(\d[\d,]*(?:\.\d+)?)\s*(?:ر\.?\s?ع|ريال|OMR|RO)\b",
               r"(?:OMR|RO|ر\.ع)\s*(\d[\d,]*(?:\.\d+)?)",
               r"(?:سعر البداية|starting price|السعر الافتتاحي)\D{0,6}(\d[\d,]*(?:\.\d+)?)",
               r"(?:السعر|price)\W{0,6}(\d[\d,]*(?:\.\d+)?)"]:
        m = re.search(rx, t, re.I)
        if m:
            v = num(m.group(1))
            if v is not None and v > 0:
                return v
    return None


def get(url, tries=3):
    for i in range(tries):
        try:
            r = requests.get(url, headers=HDR, timeout=30)
            if r.status_code == 200:
                return r.text
        except requests.RequestException:
            pass
        time.sleep(2 * (i + 1))
    return None


def lines_of(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup, [clean(x) for x in soup.get_text("\n").split("\n") if clean(x)]


def field(lines, label):
    for i, ln in enumerate(lines):
        if ln == label or ln.startswith(label + ":") or ln.startswith(label + " "):
            rest = clean(ln[len(label):].lstrip(":："))
            if rest:
                return rest
            if i + 1 < len(lines):
                return lines[i + 1]
    return None


# ---------------------------------------------------------------- ebid.om
EBID = "https://ebid.om"


def scrape_ebid(log):
    items, lists, details = [], set(), set()
    for start in ["/", "/auction-list", "/property-list"]:
        html = get(EBID + start)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            h = urljoin(EBID + "/", a["href"])
            if "ebid.om" not in h:
                continue
            if re.search(r"/(property|vehicle)-list", h):
                lists.add(h.split("#")[0])
            elif re.search(r"/(property|vehicle)-profile/\d+", h):
                details.add(re.sub(r"[?#].*$", "", h))
    vend_date = {}
    for lst in sorted(lists):
        html = get(lst)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            h = urljoin(EBID + "/", a["href"])
            if re.search(r"/(property|vehicle)-profile/\d+", h):
                details.add(re.sub(r"[?#].*$", "", h))
    log["ebid_links"] = len(details)
    for url in sorted(details):
        html = get(url)
        if not html:
            continue
        soup, L = lines_of(html)
        h1 = soup.find("h1")
        title = clean(h1.get_text(" ")) if h1 else None
        car = "/vehicle-profile/" in url
        price = num(field(L, "السعر الحالي") or field(L, "المزايدة الحالية") or "")
        dtxt = field(L, "تاريخ المزاد") or ""
        ds = find_dates(dtxt)
        hm = parse_time(field(L, "وقت بدء المزايدة المباشرة") or "") or (9, 0)
        start = ds[0][0].replace(hour=hm[0], minute=hm[1]) if ds else None
        if car:
            place = field(L, "موقع المزاد") or "مدينة سندان"
            gov = "مسقط"
            m = re.search(r"(?:سنة الصنع|الموديل|سنة الموديل)\s*:?\s*((?:19|20)\d{2})", " ".join(L))
            if m and m.group(1) not in (title or ""):
                title = f"{title} {m.group(1)}"
            sub, cat = "مركبات المحاكم", "car"
            area = None
        else:
            gov = field(L, "المحافظة")
            if gov and gov.endswith("ه") and (gov[:-1] + "ة") in GOVS:
                gov = gov[:-1] + "ة"
            place = field(L, "الموقع") or ""
            place = re.sub(r"^\S+ه\s*-\s*", "", place) if gov and place.split(" - ")[0].rstrip("هة") == gov.rstrip("هة") else place
            if gov and place.startswith(gov):
                place = place[len(gov):].lstrip(" -–")
            sub = (title or "").split(" - ")[0] or "عقار"
            cat = "land"
            area = num(field(L, "المساحة") or "")
        status = field(L, "حالة المزاد")
        items.append({
            "id": "ebid-" + ("v" if car else "p") + url.rsplit("/", 1)[-1],
            "src": "ebid.om", "cat": cat, "sub": sub, "title": title or ("مركبة" if car else "عقار"),
            "gov": gov, "place": place, "price": price, "area": area,
            "start": start.isoformat() if start else None, "end": None, "url": url,
            "note": " • ".join(x for x in ["محكمة التنفيذ", status] if x),
        })
        time.sleep(0.3)
    return items


# ---------------------------------------------------------------- المواقع اللي تحتاج متصفح
CARD_JS = r"""() => {
  const out = [], seen = new Set();
  const bad = /login|register|signin|signup|contact|about|faq|terms|privacy|policy|whatsapp|facebook|twitter|instagram|x\.com|youtube|linkedin|play\.google|apps\.apple|mailto:|tel:|#$/i;
  document.querySelectorAll('a[href]').forEach(a => {
    const h = a.href;
    if (!h || bad.test(h) || seen.has(h)) return;
    let el = a, txt = '';
    for (let i = 0; i < 7 && el; i++) {
      txt = (el.innerText || '').trim();
      if (txt.length > 60) break;
      el = el.parentElement;
    }
    if (txt.length < 15 || txt.length > 1500) return;
    seen.add(h);
    out.push({href: h, text: txt});
  });
  // كروت بدون روابط (أزرار)
  document.querySelectorAll('[class*=card],[class*=Card],[class*=auction],[class*=lot],[class*=item]').forEach(c => {
    const t = (c.innerText || '').trim();
    if (t.length < 30 || t.length > 1200) return;
    if (c.querySelector('a[href]')) return;
    out.push({href: '', text: t});
  });
  return out;
}"""


def walk_json(obj, out, depth=0):
    """يلقط أي قائمة عناصر شكلها إعلانات مزاد (عنوان + تاريخ أو سعر)."""
    if depth > 10:
        return
    if isinstance(obj, list):
        for x in obj:
            if isinstance(x, dict) and looks_like_auction(x):
                out.append(x)
            walk_json(x, out, depth + 1)
    elif isinstance(obj, dict):
        for v in obj.values():
            walk_json(v, out, depth + 1)


DATE_KEYS_S = ("start_date", "start_time", "starts_at", "start_at", "auction_start", "start_datetime", "startDate", "start")
DATE_KEYS_E = ("end_date", "end_time", "ends_at", "end_at", "auction_end", "end_datetime", "endDate", "end", "closing_date")
PRICE_KEYS = ("current_price", "current_amount", "current_bid", "highest_bid", "last_bid", "max_bid", "currentPrice",
              "start_amount", "starting_amount", "starting_price", "start_price", "opening_price", "min_price", "price", "amount")


def ar(v):
    if isinstance(v, dict):
        return v.get("ar") or v.get("en") or next((x for x in v.values() if isinstance(x, str)), None)
    return v


def looks_like_auction(d):
    has_title = any(d.get(k) for k in ("title", "title_ar", "name", "name_ar", "auction_name", "lot_name"))
    has_when = any(d.get(k) for k in DATE_KEYS_S + DATE_KEYS_E)
    has_id = "id" in d or "code" in d or "auction_number" in d
    return has_title and has_when and has_id


def parse_any_date(v):
    if v in (None, "", "None"):
        return None
    if isinstance(v, (int, float)) and v > 1e9:
        return datetime.fromtimestamp(v / 1000 if v > 1e11 else v, MUSCAT)
    s = str(v).strip()
    try:                                       # ISO
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=MUSCAT)
    except ValueError:
        pass
    try:                                       # Mon, 23 Nov 2026 06:00:00 GMT
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(s)
        if dt:
            return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(MUSCAT)
    except Exception:
        pass
    ds = find_dates(s)
    return ds[0][0] if ds else None


def first(d, keys):
    for k in keys:
        v = d.get(k)
        if v not in (None, "", "None", [], {}):
            return v
    return None


def item_from_json(site, d, href_for):
    title = ar(first(d, ("title_ar", "title", "name_ar", "name", "auction_name", "lot_name")))
    if not isinstance(title, str) or not title.strip():
        return None
    title = clean(title)
    start = parse_any_date(first(d, DATE_KEYS_S))
    end = parse_any_date(first(d, DATE_KEYS_E))
    price = None
    for k in PRICE_KEYS:
        if d.get(k) not in (None, "", "None"):
            price = num(d[k])
            if price:
                break
    catd = d.get("categoryDetails") or d.get("category_details") or d.get("category") or {}
    cat_txt = ar(catd.get("category_name_ar") or catd.get("category_name") or catd.get("name")) if isinstance(catd, dict) else str(catd or "")
    orgd = d.get("organizationDetails") or d.get("organization_details") or {}
    org = (ar(orgd.get("organization_name_ar") or orgd.get("organization_name")) if isinstance(orgd, dict) else None) or ar(d.get("owner_title"))
    loc = ar(first(d, ("location_ar", "location", "city", "wilayat", "wilayat_ar", "address", "region", "governorate")))
    if isinstance(loc, dict):
        loc = ar(loc.get("name_ar") or loc.get("name"))
    blob = " ".join(str(x) for x in [title, cat_txt, loc, d.get("description_ar") or "", d.get("description") or ""] if x)
    cat = guess_cat(f"{cat_txt} {title}")
    gov, place = guess_gov(f"{loc or ''} {title}")
    if loc and not place:
        place = str(loc)
    iid = str(d.get("id") or d.get("code") or d.get("auction_number"))
    sub = (cat_txt or {"num": "أرقام مميزة", "car": "مركبات", "land": "عقار", "proj": "معدات ومنقولات"}[cat])[:30]
    code = d.get("auction_number") or d.get("code")
    note = " • ".join(x for x in [str(code) if code else None, org] if x)
    return {
        "id": f"{site['key']}-{iid}", "src": site["name"], "cat": cat, "sub": sub, "title": title[:160],
        "gov": gov, "place": place, "price": price, "area": None,
        "start": start.isoformat() if start else None, "end": end.isoformat() if end else None,
        "url": href_for(d), "note": note,
    }


NAV_WORDS = ["الصفحة الرئيسية", "تسجيل الدخول", "التواصل معنا", "تواصل معنا", "من نحن", "الأسئلة الشائعة", "عن مزاد",
             "Home", "Login", "Contact", "About"]


def url_maker(site, anchors):
    tmpl = site.get("detail")

    def href_for(d):
        for key in ("id", "code", "auction_number"):
            v = d.get(key)
            if v in (None, ""):
                continue
            v = str(v)
            for h in anchors:
                if re.search(r"(?<![\w-])" + re.escape(v) + r"(?![\w-])", h):
                    return h
        if tmpl and d.get("id") not in (None, ""):
            return tmpl.format(id=d["id"])
        return site["pages"][0]
    return href_for


def scrape_js_sites(log):
    from playwright.sync_api import sync_playwright
    items = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(locale="ar-OM", user_agent=UA, viewport={"width": 1366, "height": 900})
        for site in JS_SITES:
            slog = {"pages": [], "apis": [], "raw_cards": [], "json_full": [], "items": 0}
            log[site["key"]] = slog
            json_items = []
            page = ctx.new_page()

            def on_resp(r, bucket=json_items, slog=slog):
                try:
                    if "json" in (r.headers.get("content-type") or "") and r.status == 200:
                        before = len(bucket)
                        walk_json(r.json(), bucket)
                        if len(slog["apis"]) < 40:
                            slog["apis"].append({"url": r.url[:200], "items": len(bucket) - before})
                except Exception:
                    pass

            page.on("response", on_resp)
            cards, anchors = [], set()
            for url in site["pages"] + site.get("extra", []):
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=20000)
                    except Exception:
                        pass
                    for _ in range(8):
                        page.mouse.wheel(0, 3000)
                        page.wait_for_timeout(1200)
                    cs = page.evaluate(CARD_JS)
                    anchors.update(page.evaluate("() => [...document.querySelectorAll('a[href]')].map(a => a.href)"))
                    slog["pages"].append({"url": url, "cards": len(cs)})
                    cards += cs
                    for c in cs[:6]:
                        if len(slog["raw_cards"]) < 15:
                            slog["raw_cards"].append({"href": c["href"], "text": c["text"][:350]})
                except Exception as e:
                    slog["pages"].append({"url": url, "error": str(e)[:200]})
            page.close()
            slog["anchors_sample"] = sorted(anchors)[:60]
            got = {}
            # 1) البيانات المنظمة (API) — الأدق
            href_for = url_maker(site, anchors)
            for d in json_items:
                if len(slog["json_full"]) < 2:
                    slog["json_full"].append({k: str(v)[:300] for k, v in d.items()})
                it = item_from_json(site, d, href_for)
                if it and it["id"] not in got:
                    got[it["id"]] = it
            card_by_href = {c["href"]: c["text"] for c in cards if c["href"]}
            for it in got.values():
                txt = card_by_href.get(it["url"])
                if txt:
                    if not it["gov"]:
                        it["gov"], it["place"] = guess_gov(txt)
                    if it["price"] is None:
                        it["price"] = find_price(txt)
            slog["json_items"] = len(got)
            # 2) الكروت من الصفحة — بس إذا ما فيه API
            if not got:
                for c in cards:
                    if sum(w in c["text"] for w in NAV_WORDS) >= 2:
                        continue
                    it = item_from_text(site, c["href"], c["text"], site["pages"][0])
                    if not it or not (it["start"] or it["end"]) or not (it["price"] or it["note"]):
                        continue
                    k = it["url"] + "|" + it["title"]
                    if k not in got:
                        got[k] = it
            slog["items"] = len(got)
            items.extend(got.values())
        browser.close()
    return items


# ---------------------------------------------------------------- التشغيل
def main():
    log = {"run": NOW.isoformat()}
    old = {}
    if os.path.exists(OUT):
        try:
            with open(OUT, encoding="utf-8") as f:
                for it in json.load(f).get("items", []):
                    old[it["id"]] = it
        except Exception:
            pass

    items = []
    try:
        e = scrape_ebid(log)
        log["ebid_items"] = len(e)
        items += e
    except Exception as ex:
        log["ebid_error"] = str(ex)[:300]
    try:
        items += scrape_js_sites(log)
    except Exception as ex:
        log["js_error"] = str(ex)[:300]

    # دمج وتنظيف
    final, seen = [], set()
    cutoff = NOW - timedelta(hours=2)
    for it in items:
        if it["id"] in seen:
            continue
        seen.add(it["id"])
        last = it.get("end") or it.get("start")
        if last and datetime.fromisoformat(last) < cutoff:
            continue                                    # انتهى
        it["first_seen"] = old.get(it["id"], {}).get("first_seen") or NOW.isoformat()
        final.append(it)

    # لو فشلت منصة بالكامل هالمرة، نخلي إعلاناتها القديمة اللي ما انتهت
    srcs_now = {it["src"] for it in final}
    for it in old.values():
        if it["src"] not in srcs_now and it["id"] not in seen:
            last = it.get("end") or it.get("start")
            if last and datetime.fromisoformat(last) >= cutoff:
                it["stale"] = True
                final.append(it)

    final.sort(key=lambda x: (x.get("start") or x.get("end") or "9999"))
    counts = {}
    for it in final:
        counts[it["src"]] = counts.get(it["src"], 0) + 1
    sources = [{"name": "ebid.om", "desc": "عقارات ومركبات محاكم التنفيذ", "url": EBID, "count": counts.get("ebid.om", 0)}]
    for s in JS_SITES:
        sources.append({"name": s["name"], "desc": s["desc"], "url": s["pages"][0], "count": counts.get(s["name"], 0)})

    os.makedirs("docs", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"updated": NOW.isoformat(), "items": final, "sources": sources}, f, ensure_ascii=False)
    with open(DEBUG, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=1)
    print(json.dumps({"total": len(final), "by_source": counts}, ensure_ascii=False))


if __name__ == "__main__":
    main()
