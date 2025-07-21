import os
import json
import threading
import time
import requests
from flask import Flask, render_template, request, jsonify
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime
from collections import defaultdict
import html
from email.utils import parsedate_to_datetime

app = Flask(__name__)

FETCH_INTERVAL = 300  # 5 phút
RSS_SOURCE_FILE = "rss_sources.json"
lock = threading.Lock()

def load_sources():
    with open(RSS_SOURCE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def fetch_and_cache_rss(source_key, source_url):
    while True:
        try:
            print(f"⏳ Fetching from {source_key}...")
            feed = feedparser.parse(source_url)
            new_articles = defaultdict(list)

            for entry in feed.entries:
                soup = BeautifulSoup(entry.description, "html.parser")
                image_tag = soup.find("img")
                image_url = image_tag["src"] if image_tag else None

                for tag in soup(["a", "img"]):
                    tag.extract()

                clean_description = html.unescape(soup.get_text().strip())
                clean_title = html.unescape(entry.title).replace("&#39;", "'")
                clean_description = clean_description.replace("&#39;", "'")

                try:
                    pub_dt = parsedate_to_datetime(entry.published)
                except Exception:
                    continue  # bỏ qua nếu lỗi ngày giờ

                pub_str = pub_dt.strftime("%Y-%m-%d %H:%M:%S")

                article = {
                    "title": clean_title,
                    "link": entry.link,
                    "published": entry.published,
                    "pubDate": pub_str,
                    "description": clean_description,
                    "image": image_url
                }

                pub_date = pub_str.split(" ")[0]
                new_articles[pub_date].append(article)

            cache_file = f"rss_cache_{source_key}.json"
            with lock:
                if os.path.exists(cache_file):
                    with open(cache_file, "r", encoding="utf-8") as f:
                        existing_data = json.load(f)
                else:
                    existing_data = {"articles": {}, "sorted_dates": []}

            existing_articles = existing_data.get("articles", {})
            for date, items in new_articles.items():
                if date not in existing_articles:
                    existing_articles[date] = items
                else:
                    existing_titles = {a["title"] for a in existing_articles[date]}
                    for item in items:
                        if item["title"] not in existing_titles:
                            existing_articles[date].append(item)
                    existing_articles[date].sort(key=lambda x: x["pubDate"], reverse=True)

            sorted_dates = sorted(existing_articles.keys(), reverse=True)
            updated_data = {
                "articles": existing_articles,
                "sorted_dates": sorted_dates
            }

            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(updated_data, f, ensure_ascii=False, indent=2)

            print(f"✅ Updated {source_key}")
        except Exception as e:
            print(f"❌ Error with {source_key}: {e}")

        time.sleep(FETCH_INTERVAL)

@app.route("/", methods=["GET"])
def index():
    source_key = request.args.get("source", "vnexpress_home")
    sources = load_sources()

    if source_key not in sources:
        return f"Invalid source: {source_key}", 400

    cache_file = f"rss_cache_{source_key}.json"
    if not os.path.exists(cache_file):
        return f"No cache found for {source_key}", 404

    with lock:
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)

    return render_template("index.html",
                           articles=data["articles"],
                           sorted_dates=data["sorted_dates"],
                           source_key=source_key,
                           sources=sources)

if __name__ == "__main__":
    sources = load_sources()
    for key, source in sources.items():
        threading.Thread(target=fetch_and_cache_rss, args=(key, source["url"]), daemon=True).start()
    app.run(debug=True)
