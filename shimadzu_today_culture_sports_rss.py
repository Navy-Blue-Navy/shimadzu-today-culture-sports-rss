import os
import sys
import hashlib
import html
import requests
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime, parsedate_to_datetime
from urllib.parse import urljoin


BASE_URL = "https://www.shimadzu.co.jp"
LIST_URL = "https://www.shimadzu.co.jp/today/index.html?category=259"
JSON_URL = "https://www.shimadzu.co.jp/today/list.json"

OUTPUT_FILE = "shimadzu_today_culture_sports.xml"

FEED_TITLE = "SHIMADZU TODAY Culture&Sports"
FEED_LINK = LIST_URL
FEED_DESCRIPTION = "SHIMADZU TODAY Culture&Sports 新着記事RSS"

CATEGORY_ID = "259"

REQUEST_TIMEOUT = 30

JST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/155.0.0.0 Safari/537.36"
    )
}


def rss_date(dt):
    return format_datetime(dt)


def parse_date(text):
    text = text.strip()

    for fmt in ("%Y.%m.%d", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=JST)
        except ValueError:
            pass

    raise ValueError(f"日付を解析できません: {text}")


def clean_title(text):
    if not text:
        return ""

    soup = BeautifulSoup(text, "html.parser")
    title = soup.get_text(" ", strip=True)
    title = html.unescape(title)

    return " ".join(title.split())


def make_guid(article):
    nid = str(article.get("nid", "")).strip()

    if nid:
        return f"shimadzu-today-{nid}"

    return hashlib.sha256(
        article["url"].encode("utf-8")
    ).hexdigest()


def fetch_articles():
    print(f"GET {JSON_URL}")

    response = requests.get(
        JSON_URL,
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
    )

    print(
        f"HTTP: {response.status_code} / "
        f"{len(response.content)} bytes"
    )

    response.raise_for_status()

    data = response.json()

    if "page_list" not in data:
        raise RuntimeError(
            "JSONに page_list がありません"
        )

    page_list = data["page_list"]

    print(f"JSON全記事数: {len(page_list)}")

    articles = {}

    for item in page_list:
        categories = [
            str(x)
            for x in item.get("category", [])
        ]

        if CATEGORY_ID not in categories:
            continue

        title = clean_title(
            item.get("title", "")
        )

        alias = str(
            item.get("alias", "")
        ).strip()

        date_text = str(
            item.get("date", "")
        ).strip()

        nid = str(
            item.get("nid", "")
        ).strip()

        image = str(
            item.get("image", "")
        ).strip()

        if not title or not alias or not date_text:
            continue

        try:
            published = parse_date(date_text)
        except Exception as e:
            print(f"日付解析失敗: {title}")
            print(f"  {date_text}")
            print(f"  {e}")
            continue

        article_url = urljoin(
            BASE_URL,
            alias,
        )

        image_url = (
            urljoin(BASE_URL, image)
            if image
            else ""
        )

        article = {
            "nid": nid,
            "title": title,
            "url": article_url,
            "published": published,
            "image": image_url,
        }

        articles[article_url] = article

    if len(articles) == 0:
        raise RuntimeError(
            "Culture&Sportsの記事を1件も取得できませんでした"
        )

    print(
        "Culture&Sports取得件数: "
        f"{len(articles)}"
    )

    return articles


def load_existing_feed():
    articles = {}

    if not os.path.exists(OUTPUT_FILE):
        print("既存RSSなし：新規作成します")
        return articles

    try:
        tree = ET.parse(OUTPUT_FILE)
        root = tree.getroot()

        for item in root.findall("./channel/item"):
            title = item.findtext(
                "title",
                default="",
            ).strip()

            link = item.findtext(
                "link",
                default="",
            ).strip()

            pub_date = item.findtext(
                "pubDate",
                default="",
            ).strip()

            guid = item.findtext(
                "guid",
                default="",
            ).strip()

            description = item.findtext(
                "description",
                default="",
            ).strip()

            if not link:
                continue

            try:
                published = parsedate_to_datetime(
                    pub_date
                )
            except Exception:
                continue

            if published.tzinfo is None:
                published = published.replace(
                    tzinfo=JST
                )

            nid = ""

            if guid.startswith(
                "shimadzu-today-"
            ):
                nid = guid.replace(
                    "shimadzu-today-",
                    "",
                    1,
                )

            articles[link] = {
                "nid": nid,
                "title": title,
                "url": link,
                "published": published,
                "image": "",
                "old_description": description,
            }

        print(
            f"既存RSS読込件数: "
            f"{len(articles)}"
        )

    except Exception as e:
        print(
            f"既存RSSの読込に失敗しました: {e}"
        )
        print(
            "安全のため処理を中止します。"
        )
        sys.exit(1)

    return articles


def build_rss(articles):
    rss = ET.Element(
        "rss",
        {
            "version": "2.0",
        },
    )

    channel = ET.SubElement(
        rss,
        "channel",
    )

    ET.SubElement(
        channel,
        "title",
    ).text = FEED_TITLE

    ET.SubElement(
        channel,
        "link",
    ).text = FEED_LINK

    ET.SubElement(
        channel,
        "description",
    ).text = FEED_DESCRIPTION

    ET.SubElement(
        channel,
        "language",
    ).text = "ja"

    now = datetime.now(JST)

    ET.SubElement(
        channel,
        "lastBuildDate",
    ).text = rss_date(now)

    sorted_articles = sorted(
        articles.values(),
        key=lambda x: x["published"],
        reverse=True,
    )

    for article in sorted_articles:
        item = ET.SubElement(
            channel,
            "item",
        )

        ET.SubElement(
            item,
            "title",
        ).text = article["title"]

        ET.SubElement(
            item,
            "link",
        ).text = article["url"]

        guid = ET.SubElement(
            item,
            "guid",
            {
                "isPermaLink": "false"
            },
        )

        guid.text = make_guid(article)

        ET.SubElement(
            item,
            "pubDate",
        ).text = rss_date(
            article["published"]
        )

        ET.SubElement(
            item,
            "category",
        ).text = "Culture&Sports"

        description_parts = [
            "カテゴリ: Culture&Sports",
            (
                "掲載日: "
                + article["published"]
                .astimezone(JST)
                .strftime("%Y.%m.%d")
            ),
        ]

        if article.get("image"):
            description_parts.append(
                f'<img src="{article["image"]}" '
                f'alt="">'
            )

        ET.SubElement(
            item,
            "description",
        ).text = " / ".join(
            description_parts
        )

    tree = ET.ElementTree(rss)

    ET.indent(
        tree,
        space="  ",
    )

    tree.write(
        OUTPUT_FILE,
        encoding="utf-8",
        xml_declaration=True,
    )

    print()
    print(
        f"保存完了: {OUTPUT_FILE} "
        f"({len(sorted_articles)}件)"
    )


def main():
    print(
        "SHIMADZU TODAY "
        "Culture&Sports RSS生成"
    )
    print("=" * 50)

    existing_articles = load_existing_feed()

    try:
        current_articles = fetch_articles()

    except Exception as e:
        print()
        print(
            "JSONの取得・解析に失敗しました。"
        )
        print(f"エラー: {e}")
        print()
        print(
            "既存RSSは変更せず、"
            "そのまま残します。"
        )
        sys.exit(1)

    new_urls = [
        url
        for url in current_articles
        if url not in existing_articles
    ]

    combined_articles = dict(
        existing_articles
    )

    for url, article in current_articles.items():
        combined_articles[url] = article

    print()
    print(
        f"今回取得した記事: "
        f"{len(current_articles)}"
    )

    print(
        f"今回初めて確認した記事: "
        f"{len(new_urls)}"
    )

    print(
        f"累積RSS件数: "
        f"{len(combined_articles)}"
    )

    sorted_current = sorted(
        current_articles.values(),
        key=lambda x: x["published"],
        reverse=True,
    )

    print()
    print(
        "今回取得した記事（先頭20件）"
    )
    print("-" * 50)

    for article in sorted_current[:20]:
        date_text = (
            article["published"]
            .astimezone(JST)
            .strftime("%Y-%m-%d")
        )

        print(
            f"{date_text} / "
            f"{article['title']}"
        )

        print(
            f"  {article['url']}"
        )

    build_rss(
        combined_articles
    )


if __name__ == "__main__":
    main()