from abc import ABC, abstractmethod
from typing import Any, Dict, List
import logging
import json
import re
import unicodedata
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from langchain_core.tools import tool
from dotenv import load_dotenv
import os
import whois
import urllib.parse
from datetime import datetime
load_dotenv()

SERPER_API_KEY = os.getenv("SERPER_API_KEY")

# Load media bias data
_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_TOOLS_DIR, "media_bias_data.json"), "r", encoding="utf-8") as file:
    MEDIA_DATA = json.load(file)

MEDIA_BIAS_DICT = {entry.get("url"): entry for entry in MEDIA_DATA}
DATASET_DATE_LIMITS = {
    "feverous": "10/12/2021",
    "hover": "11/16/2020",
    "scifact": "10/3/2020"
}

# Stop-words to skip when building keyword sets
_STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
    "for", "of", "with", "by", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did",
    "will", "would", "could", "should", "may", "might", "that",
    "this", "it", "its", "from", "as", "not", "which", "who",
}

_SCRAPE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
_SCRAPE_TIMEOUT = 8  # seconds per HTTP request


class SearchEngineRetriever:
    def __init__(self, dataset: str, headless: bool = True):
        self.skip_query_token = None
        self.server_address = "https://google.serper.dev/search"
        self.dataset = dataset

    def create_content_dict(self, content: list, **kwargs) -> Dict:
        resp_content = {"content": content}
        resp_content.update(**kwargs)
        return resp_content

    def _query_search_server(self, query_term):
        payload = json.dumps({
            "q": query_term,
            "num": 10,
            "tbs": f"cdr:1,cd_min:,cd_max:{DATASET_DATE_LIMITS[self.dataset]}"
        })
        headers = {
            'X-API-KEY': SERPER_API_KEY,
            'Content-Type': 'application/json'
        }
        response = requests.post(self.server_address, headers=headers, data=payload)
        if response.status_code == 200:
            try:
                res = response.json()
                return res.get('organic', [])
            except json.JSONDecodeError:
                logging.error('Failed to parse JSON response from search server.')
        logging.error('Search server error. No results retrieved.')
        return []

    def _get_original_url(self, url):
        parsed_url = urlparse(url)
        return f"{parsed_url.netloc}/"

    def _check_valid_url(self, url):
        parsed_url = urllib.parse.urlparse(url)
        domain = parsed_url.netloc.lower()
        if domain.startswith('www.'):
            domain = domain[4:]

        entry = MEDIA_BIAS_DICT.get(domain)
        if entry:
            valid_factuality = {"very high", "high", "mostly factual"}
            valid_bias = {"least biased", "left-center", "right-center", "pro-science"}
            if (entry.get("factual", "").lower() in valid_factuality and
                    entry.get("bias", "").lower() in valid_bias):
                return True

        if domain.endswith(".edu") or domain.endswith(".gov") or domain.endswith(".org"):
            return True

        try:
            domain_info = whois.whois(domain)
            if domain_info.creation_date:
                creation_date = (domain_info.creation_date[0]
                                 if isinstance(domain_info.creation_date, list)
                                 else domain_info.creation_date)
                if (datetime.now() - creation_date).days / 365 > 5:
                    return True
        except Exception:
            pass

        scientific_domains = [
            'nature.com', 'science.org', 'nih.gov', 'pubmed.ncbi.nlm.nih.gov',
            'sciencedirect.com', 'springer.com', 'wiley.com', 'oxford',
            'cambridge.org', 'cell.com', 'nejm.org', 'thelancet.com',
            'bmj.com', 'pnas.org'
        ]
        if any(sd in domain for sd in scientific_domains):
            return True

        return False

    def _extract_relevant_sentences(self, query: str, sentences: list) -> str:
        """
        Deterministic relevance filter — no Gemini call needed.

        Scores each sentence by how many non-trivial query tokens it contains,
        then returns the top-scoring sentences (up to 6), preserving their
        original order.  Falls back to the first 4 sentences when no sentence
        shares any keyword with the query.
        """
        keywords = {
            w.lower().rstrip("s")          # crude stemming (plurals)
            for w in re.split(r'\W+', query)
            if len(w) > 3 and w.lower() not in _STOP_WORDS
        }
        if not keywords:
            return " ".join(sentences[:4])

        scored = []
        for s in sentences:
            s_lower = s.lower()
            hits = sum(1 for k in keywords if k in s_lower)
            if hits > 0:
                scored.append((hits, s))

        if not scored:
            return " ".join(sentences[:4])

        # Sort descending by score, keep original order for ties
        scored.sort(key=lambda x: -x[0])
        top = [s for _, s in scored[:6]]
        return " ".join(top)

    def _retrieve_single(self, search_query: str):
        if search_query == self.skip_query_token:
            return None

        retrieved_doc = ""
        search_server_resp = self._query_search_server(search_query)
        if not search_server_resp:
            logging.warning(
                f'Server search produced no results for "{search_query}".'
            )
            return retrieved_doc

        for i, rd in enumerate(search_server_resp):
            link_chosen = -1
            original_url = self._get_original_url(rd.get("link", ""))
            if self._check_valid_url(original_url):
                if link_chosen == -1:
                    link_chosen = i
                url = rd.get('link', '')
                title = rd.get('title', '')
                sentences = self.get_details(url)
                snippet = rd.get("snippet", " ")
                if len(sentences) > 1:
                    relevant = self._extract_relevant_sentences(
                        search_query, sentences
                    )
                    if relevant:
                        parsed_domain = urllib.parse.urlparse(url).netloc.lower()
                        if parsed_domain.startswith('www.'):
                            parsed_domain = parsed_domain[4:]
                        entry = MEDIA_BIAS_DICT.get(parsed_domain)
                        
                        retrieved_doc = json.dumps({
                            "url": url,
                            "title": title,
                            "excerpt": relevant,
                            "credibility_score": entry.get("factual", "Unknown") if entry else "Unknown",
                            "bias_label": entry.get("bias", "Unknown") if entry else "Unknown"
                        })
                if retrieved_doc:
                    break

            if not retrieved_doc and link_chosen != -1:
                r = search_server_resp[link_chosen]
                fallback_url = r.get('link', '')
                parsed_domain = urllib.parse.urlparse(fallback_url).netloc.lower()
                if parsed_domain.startswith('www.'):
                    parsed_domain = parsed_domain[4:]
                entry = MEDIA_BIAS_DICT.get(parsed_domain)

                retrieved_doc = json.dumps({
                    "url": fallback_url,
                    "title": r.get('title', ''),
                    "excerpt": r.get('snippet', ' '),
                    "credibility_score": entry.get("factual", "Unknown") if entry else "Unknown",
                    "bias_label": entry.get("bias", "Unknown") if entry else "Unknown"
                })

        return retrieved_doc

    def get_details(self, url):
        """Extract content from webpage using requests + BeautifulSoup."""
        try:
            resp = requests.get(url, headers=_SCRAPE_HEADERS, timeout=_SCRAPE_TIMEOUT)
            if resp.status_code != 200:
                logging.warning(f"HTTP {resp.status_code} for {url}")
                return []

            soup = BeautifulSoup(resp.text, "html.parser")
            raw_para = ""
            for para in soup.find_all("p"):
                text = para.get_text(separator=" ").strip()
                if text:
                    text = " ".join(text.split())
                    text = unicodedata.normalize("NFKD", text)
                    text = re.sub(r'[\n\t]', '', text)
                    raw_para += ' ' + text

            if not raw_para.strip() or len(raw_para) < 50:
                logging.warning(f"Possible bot detection on {url} — no content found")
                return []

            bot_patterns = [
                r"please enable javascript", r"access denied",
                r"are you a robot", r"verify you are human", r"captcha"
            ]
            for pattern in bot_patterns:
                if re.search(pattern, raw_para, re.IGNORECASE):
                    logging.warning(f"Bot detection triggered on {url}")
                    return []

            return self._split_into_sentences(raw_para)

        except requests.exceptions.Timeout:
            logging.warning(f"Timeout while accessing {url}")
            return []
        except Exception as e:
            logging.error(f"Error accessing {url}: {str(e)}")
            return []

    def _split_into_sentences(self, text):
        abbreviations = {
            'dr.': 'doctor', 'mr.': 'mister', 'bro.': 'brother',
            'mrs.': 'mistress', 'ms.': 'miss', 'jr.': 'junior',
            'sr.': 'senior', 'i.e.': 'for example', 'e.g.': 'for example',
            'vs.': 'versus'
        }
        for abbr, full in abbreviations.items():
            text = text.replace(abbr, full)
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
        return [s.strip() for s in sentences if s.strip()]

    def retrieve(self, queries: List[str]) -> List[Dict[str, Any]]:
        return [self._retrieve_single(q) for q in queries]


@tool
def search_retrieve_news(query: str, dataset: str):
    """
    Search for news/web articles relevant to the query and return extracted evidence.

    Args:
        query:   The search query string.
        dataset: Dataset name used to apply publication date limits
                 (feverous | hover | scifact).

    Returns:
        A string with the article title, snippet, and relevant extracted
        sentences, or an empty string when nothing is found.
    """
    try:
        result = SearchEngineRetriever(dataset).retrieve(queries=[query])
        return result[0] or ""
    except Exception:
        return ""
