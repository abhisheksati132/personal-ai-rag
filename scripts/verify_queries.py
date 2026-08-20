import sys
from pathlib import Path

# Ensure standard streams handle UTF-8 safely on Windows
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import time
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.api import QueryRequest, query_documents

console = Console(force_terminal=True, highlight=False)

TEST_QUESTIONS = [
    {
        "id": 1,
        "question": "Explain how a modern compiler processes the statement through all compilation phases in CAT-1.",
        "expected_topic": "Compiler phases (Lexical, Syntax, Semantic, Intermediate Code, Optimization, Code Generation)",
        "expected_file": "BCSE307L-CAT-1-A2-2025-2026.pdf",
    },
    {
        "id": 2,
        "question": "What tokens are identified during lexical analysis of the C-like statement in CAT-1?",
        "expected_topic": "Tokens identified (total, =, (, price, *, quantity, etc.)",
        "expected_file": "BCSE307L-CAT-1-A2-2025-2026.pdf",
    },
    {
        "id": 3,
        "question": "How many ports at end devices and total cables are needed for 5 devices in a Full Mesh Topology?",
        "expected_topic": "20 ports and 10 links/cables",
        "expected_file": "24bds0199.pdf",
    },
    {
        "id": 4,
        "question": "What is the single-link failure impact and fault tolerance for 5 devices in a Star Topology?",
        "expected_topic": "Only the device on the failed link is disconnected; moderate/low fault tolerance",
        "expected_file": "24bds0199.pdf",
    },
    {
        "id": 5,
        "question": "Why is a bus topology single backbone cable considered a major single point of failure?",
        "expected_topic": "If the shared communication backbone breaks, all devices lose network communication",
        "expected_file": "24bds0199.pdf",
    },
    {
        "id": 6,
        "question": "What are the columns and data types in the ORDERS table schema in DBMS Lab Manual 3?",
        "expected_topic": "order_id, customer_name, product_name, category, quantity, unit_price, order_date, payment_mode, status, total_amount",
        "expected_file": "Lab_Manual_3_Purchase_Database.pdf",
    },
    {
        "id": 7,
        "question": "Explain the difference between UNIQUE and NOT NULL constraints in DBMS Lab Manual 3.",
        "expected_topic": "UNIQUE ensures distinct values; NOT NULL disallows empty values",
        "expected_file": "Lab_Manual_3_Purchase_Database.pdf",
    },
    {
        "id": 8,
        "question": "What are the core design principles and index type used in ChromaDB architecture?",
        "expected_topic": "Simplicity, HNSW indexing for ANN search, SQLite persistent store",
        "expected_file": "chromadb_architecture.docx",
    },
    {
        "id": 9,
        "question": "What is the formula for Scaled Dot-Product Attention in the Transformer architecture?",
        "expected_topic": "Attention(Q, K, V) = softmax(QK^T / sqrt(d_k))V",
        "expected_file": "attention_is_all_you_need_summary.md",
    },
    {
        "id": 10,
        "question": "Why does FastAPI support asynchronous request handling with async def?",
        "expected_topic": "Handles I/O-bound tasks concurrently without thread pool exhaustion using Starlette and Uvicorn",
        "expected_file": "fastapi_guide.txt",
    },
    {
        "id": 11,
        "question": "What is the secret recipe for baking homemade chocolate chip cookies?",
        "expected_topic": "Negative test case (Out of scope - must return zero info found fallback)",
        "expected_file": "None (Fallback expected)",
    },
]


def run_verification():
    console.print(Panel.fit("[bold cyan]Personal AI Brain - Phase 2 Live Verification Suite[/bold cyan]"))
    results_summary = []

    for item in TEST_QUESTIONS:
        q_id = item["id"]
        question = item["question"]
        expected = item["expected_topic"]

        console.print(f"\n[bold yellow]Query {q_id}:[/bold yellow] {question}")
        console.print(f"[dim]Expected focus: {expected}[/dim]")

        start = time.time()
        try:
            req = QueryRequest(question=question)
            res = query_documents(req)
            elapsed = time.time() - start

            sources_str = ", ".join([f"{s.file} (chunk #{s.chunk_index}, score={s.score:.3f})" for s in res.sources]) or "None"

            console.print(f"[bold green]Answer ({elapsed:.2f}s):[/bold green]")
            console.print(Panel(res.answer, title=f"Grounded Response ({sources_str})", border_style="green"))

            results_summary.append({
                "id": q_id,
                "question": question[:45] + "...",
                "sources": sources_str[:35] + ("..." if len(sources_str) > 35 else ""),
                "status": "PASS" if res.answer else "FAIL",
                "time": f"{elapsed:.2f}s",
            })

        except Exception as e:
            elapsed = time.time() - start
            console.print(f"[bold red]Failed with error ({elapsed:.2f}s):[/bold red] {e}")
            results_summary.append({
                "id": q_id,
                "question": question[:45] + "...",
                "sources": "ERROR",
                "status": f"ERR: {e}",
                "time": f"{elapsed:.2f}s",
            })

    # Print summary table
    table = Table(title="Live Verification Summary", header_style="bold magenta")
    table.add_column("#", style="bold")
    table.add_column("Question", style="cyan")
    table.add_column("Cited Sources", style="green")
    table.add_column("Status", style="bold white")
    table.add_column("Latency", style="dim")

    for r in results_summary:
        table.add_row(str(r["id"]), r["question"], r["sources"], r["status"], r["time"])

    console.print("\n")
    console.print(table)


if __name__ == "__main__":
    run_verification()
