import re
import requests
from bs4 import BeautifulSoup
from typing import List, Dict

HEADERS = {"User-Agent": "FinSight research@finsight.com"}

TICKERS = ["AAPL", "MSFT", "GOOGL", "JPM", "GS"]

CHUNK_SIZE = 400   # words (proxy for tokens)
CHUNK_OVERLAP = 50


def get_cik(ticker: str) -> str:
    """Resolve ticker to zero-padded 10-digit CIK via SEC company_tickers.json."""
    url = "https://www.sec.gov/files/company_tickers.json"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    for entry in resp.json().values():
        if entry["ticker"].upper() == ticker.upper():
            return str(entry["cik_str"]).zfill(10)
    raise ValueError(f"CIK not found for ticker: {ticker}")


def get_latest_10k(cik: str) -> Dict:
    """Return metadata for the most recent 10-K in the submissions feed."""
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    recent = resp.json()["filings"]["recent"]

    for i, form in enumerate(recent["form"]):
        if form == "10-K":
            return {
                "accession": recent["accessionNumber"][i].replace("-", ""),
                "filing_date": recent["filingDate"][i],
                "primary_doc": recent["primaryDocument"][i],
            }
    raise ValueError(f"No 10-K found for CIK: {cik}")


def fetch_filing_text(cik: str, filing: Dict) -> str:
    """Download the primary 10-K document and return clean plain text."""
    cik_int = int(cik)
    accession = filing["accession"]
    doc = filing["primary_doc"]
    url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession}/{doc}"

    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.content, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()

    text = soup.get_text(separator=" ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def chunk_text(text: str) -> List[str]:
    """Split text into overlapping word-based chunks."""
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        chunk = " ".join(words[start : start + CHUNK_SIZE])
        chunks.append(chunk)
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def load_sec_filings() -> List[Dict]:
    """
    Fetch the latest 10-K for each ticker, chunk it, and return records of:
      { company, filing_date, chunk_text, chunk_index }
    """
    records = []
    for ticker in TICKERS:
        print(f"[{ticker}] Resolving CIK...")
        try:
            cik = get_cik(ticker)
            filing = get_latest_10k(cik)
            print(f"[{ticker}] Fetching 10-K filed {filing['filing_date']}...")
            text = fetch_filing_text(cik, filing)
            chunks = chunk_text(text)
            for idx, chunk in enumerate(chunks):
                records.append(
                    {
                        "company": ticker,
                        "filing_date": filing["filing_date"],
                        "chunk_text": chunk,
                        "chunk_index": idx,
                    }
                )
            print(f"[{ticker}] -> {len(chunks)} chunks")
        except Exception as e:
            print(f"[{ticker}] ERROR: {e}")

    return records


if __name__ == "__main__":
    docs = load_sec_filings()
    print(f"\nTotal chunks: {len(docs)}")
    if docs:
        sample = docs[0]
        print(f"Sample — company={sample['company']}, date={sample['filing_date']}, "
              f"chunk_index={sample['chunk_index']}")
        print(f"Text preview: {sample['chunk_text'][:200]}")
