from sec_loader import load_sec_filings
from snowflake_loader import load_chunks

if __name__ == "__main__":
    print("=== Step 1: Fetching SEC filings ===")
    chunks = load_sec_filings()
    print(f"Total chunks ready: {len(chunks)}\n")

    print("=== Step 2: Loading into Snowflake ===")
    load_chunks(chunks)

    print("\nIngestion complete.")
