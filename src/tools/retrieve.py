from abc import ABC, abstractmethod
from typing import Any, Dict, List
import logging
import json
import re
import unicodedata
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import requests
from urllib.parse import urlparse
from langchain_core.tools import tool
from dotenv import load_dotenv
import os
from langchain_core.prompts import PromptTemplate
from itertools import cycle
import whois
import urllib.parse
from datetime import datetime
import google.generativeai as genai
load_dotenv()

SERPER_API_KEY = os.getenv("SERPER_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Load media bias data 
_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_TOOLS_DIR, "media_bias_data.json"), "r", encoding="utf-8") as file:
    MEDIA_DATA = json.load(file)

# Create a dictionary for efficient URL lookup
MEDIA_BIAS_DICT = {entry.get("url"): entry for entry in MEDIA_DATA}
DATASET_DATE_LIMITS = {
        "feverous": "10/12/2021",
        "hover": "11/16/2020", 
        "scifact": "10/3/2020"
    }
genai.configure(api_key=GOOGLE_API_KEY)
GEMINI_MODEL = genai.GenerativeModel("gemini-1.5-flash", generation_config=genai.GenerationConfig(temperature=0.1))


class SearchEngineRetriever:
    def __init__(self, dataset: str, headless: bool = True):
        self.skip_query_token = None
        self.server_address = "https://google.serper.dev/search"
        self.dataset = dataset
        # Initialize Selenium WebDriver
        options = webdriver.ChromeOptions()
        if headless:
            options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 10)

    def create_content_dict(self, content: list, **kwargs) -> Dict:
        resp_content = {"content": content}
        resp_content.update(**kwargs)
        return resp_content


    def _query_search_server(self, query_term):
        payload = json.dumps({"q": query_term, "num": 10, "tbs": f"cdr:1,cd_min:,cd_max:{DATASET_DATE_LIMITS[self.dataset]}"})
        headers = {
            'X-API-KEY': SERPER_API_KEY,
            'Content-Type': 'application/json'
        }

        response = requests.post(self.server_address, headers=headers, data=payload)
        resp_status = response.status_code
        if resp_status == 200:
            try:
                res = response.json()
                return res.get('organic', [])  # Return empty list if 'organic' key is missing
            except json.JSONDecodeError:
                logging.error('Failed to parse JSON response from search server.')
           
        logging.error('All API keys exhausted. No results retrieved.')
        return [] # Return empty list if all keys are exhausted

    def _get_original_url(self, url):
        parsed_url = urlparse(url)
        return f"{parsed_url.netloc}/"

    def _check_valid_url(self, url):
        """
        Checks if a URL is legitimate based on:
        1. Media bias and factuality (using existing dictionary)
        2. Domain suffix analysis (.edu, .gov, .org)
        3. Publication history (domain age)
        4. Citation patterns (for scientific sources)

        Returns: 
            bool: True if the URL is considered legitimate, False otherwise
        """
        # Normalize URL for consistency
        parsed_url = urllib.parse.urlparse(url)
        domain = parsed_url.netloc.lower()
        if domain.startswith('www.'):
            domain = domain[4:]

        # 1. Check against media bias dictionary
        entry = MEDIA_BIAS_DICT.get(domain)
        if entry:
            valid_factuality = {"very high", "high", "mostly factual"}
            valid_bias = {"least biased", "left-center", "right-center", "pro-science"}
            factual = entry.get("factual", "").lower()
            bias = entry.get("bias", "").lower()

            if factual in valid_factuality and bias in valid_bias:
                return True

        # 2. Domain suffix analysis
        if domain.endswith(".edu") or domain.endswith(".gov") or domain.endswith(".org"):
            return True

        # 3. Publication history (domain age)
        try:
            domain_info = whois.whois(domain)
            if domain_info.creation_date:
                # Handle both single date and list of dates
                if isinstance(domain_info.creation_date, list):
                    creation_date = domain_info.creation_date[0]
                else:
                    creation_date = domain_info.creation_date

                domain_age_years = (datetime.now() - creation_date).days / 365

                # Consider domains older than 5 years as legitimate
                if domain_age_years > 5:
                    return True
        except Exception:
            # If WHOIS lookup fails, continue to other checks
            pass

        # 4. Citation patterns (for scientific claims)
        # Check if URL is from a recognized scientific source
        scientific_domains = [
            'nature.com', 'science.org', 'nih.gov', 'pubmed.ncbi.nlm.nih.gov', 
            'sciencedirect.com', 'springer.com', 'wiley.com', 'oxford', 'cambridge.org', 
            'cell.com', 'nejm.org', 'thelancet.com', 'bmj.com', 'pnas.org'
        ]

        if any(sci_domain in domain for sci_domain in scientific_domains):
            return True

        # If none of the criteria are met, return False
        return False

    def _retrieve_single(self, search_query: str):
        if search_query == self.skip_query_token:
            return None

        retrieved_doc = ""
        search_server_resp = self._query_search_server(search_query)
        if not search_server_resp:
            logging.warning(
                f'Server search did not produce any results for "{search_query}" query.'
                ' returning an empty set of results for this query.'
            )
            return retrieved_doc

        for i, rd in enumerate(search_server_resp):
            link_choosen = -1
            original_url = self._get_original_url(rd.get("link", ""))
            if self._check_valid_url(original_url):
                if link_choosen == -1:
                    link_choosen = i
                url = rd.get('link', '')
                title = rd.get('title', '')
                content = self.get_details(url)
                snippet = rd.get("snippet", " ")
                if len(content) > 1:
                    article_content = f"Article Title: {title} \nGoogle Snippet: {snippet}\nArticle Content: \n{content}"
                    retrieved_doc = self._process_content(search_query, article_content)
                if retrieved_doc:
                    break
            if link_choosen != -1:
                article_content = f"Article Title: {search_server_resp[link_choosen].get('title', '')} \nGoogle Snippet: {search_server_resp[link_choosen].get('snippet', ' ')}"
                retrieved_doc = self._process_content(search_query, article_content)
                 
        return retrieved_doc

    def get_details(self, url):
        """Extract content from webpage using Selenium"""
        try:
            self.driver.get(url)
            # Wait for paragraphs to load
            self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "p")))

            # Extract all paragraph texts
            paragraphs = self.driver.find_elements(By.TAG_NAME, "p")
            raw_para = ""

            for para in paragraphs:
                text = para.text.strip()
                if text:  # Only add non-empty paragraphs
                    text = " ".join(text.split())  # Normalize whitespace
                    text = unicodedata.normalize("NFKD", text)
                    text = re.sub(r'\n', '', text)
                    text = re.sub(r'\t', '', text)
                    raw_para += ' ' + text

            if not raw_para.strip() or len(raw_para) < 50:  # Arbitrary threshold
                logging.warning(f"Possible bot detection on {url} - No content found")
                return []

            # Detect bot-detection messages
            bot_detection_patterns = [
                r"please enable javascript",
                r"access denied",
                r"are you a robot",
                r"verify you are human",
                r"captcha"
            ]

            for pattern in bot_detection_patterns:
                if re.search(pattern, raw_para, re.IGNORECASE):
                    logging.warning(f"Bot detection triggered on {url}")
                    return []
                # Split into sentences
            sentences = self._split_into_sentences(raw_para)
            return sentences

        except TimeoutException:
            logging.warning(f"Timeout while accessing {url}")
            return []
        except Exception as e:
            logging.error(f"Error accessing {url}: {str(e)}")
            return []

    def _split_into_sentences(self, text):
        """Split text into sentences using regex patterns"""
        abbreviations = {
            'dr.': 'doctor', 'mr.': 'mister', 'bro.': 'brother', 'mrs.': 'mistress',
            'ms.': 'miss', 'jr.': 'junior', 'sr.': 'senior', 'i.e.': 'for example',
            'e.g.': 'for example', 'vs.': 'versus'
        }

        # Replace abbreviations to avoid false sentence breaks
        for abbr, full in abbreviations.items():
            text = text.replace(abbr, full)

        # Split into sentences using regex
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
        return [s.strip() for s in sentences if s.strip()]

    def _process_content(self, query: str, content: str):
        # Prompt evidence: evidence_fs_prompt (in prompt file)
        ## if not enough info, add evidence
        """
        Processes retrieved content using Gemini to extract information relevant to the query.

        Args:
            query: The original search query.
            content: The retrieved text content from a webpage.

        Returns:
            A string containing only the information from the content that is relevant to the query.
            Returns an empty string if no relevant information is found.
        """

        prompt_template = PromptTemplate.from_template(
            """
            You are a helpful assistant who extracts information from text.
            Given the following query and text content, extract only the sentences or phrases that directly
            relate to the query. Do not include any information that is not relevant.
            If the content contains no relevant information, return None.
            Query: {query}
            Content:
            {content}
            Relevant Information:
            """
        )
        prompt = prompt_template.format(query=query, content=content)
        response = GEMINI_MODEL.generate_content(prompt)
        return response.text.strip() if response.text else ""

    def retrieve(self, queries: List[str]) -> List[Dict[str, Any]]:
        return [self._retrieve_single(q) for q in queries]

    def __del__(self):
        """Clean up browser instance"""
        if hasattr(self, 'driver'):
            self.driver.quit()


@tool
def search_retrieve_news(query: str, dataset: str):
    """
    Searches for news articles related to the given query.

    Args:
        query: The search query string.
        dataset: The dataset to use for date limits in the search.
    Returns:
        A list of dictionaries, where each dictionary represents a search result
        and contains keys like 'url', 'title', 'content', and 'snippet'.
        Returns an empty list if no results are found or if all API keys are exhausted.
    """
    try:
        search_result = SearchEngineRetriever(dataset).retrieve(queries=[query])
        return search_result[0]
    except:
        return ""