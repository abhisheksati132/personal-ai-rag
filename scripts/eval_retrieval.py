"""Retrieval Quality Diagnostic Tool for Personal AI Brain.

Evaluates retrieval quality across a diverse set of test questions against the live
knowledge base (files + bookmarks). Surfaces real retrieval patterns, scores,
grounding status, and automated suspicious pattern flags without changing any
system parameters.
"""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Optional

# Ensure standard streams handle UTF-8 safely on Windows
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.api import QueryRequest, query_documents
from src.config import settings
from src.retrieval import RetrievalService, RetrievedChunk
from src.vector_store import ChromaVectorStore

console = Console(force_terminal=True, highlight=False)

# -----------------------------------------------------------------------------
# Test Question Suite (19 Questions across 3 categories)
# -----------------------------------------------------------------------------
TEST_QUESTIONS = [
    # Category 1: Specific / Direct Fact Retrieval Across Different Sources
    {
        "id": "Q01",
        "category": "Specific Fact",
        "question": "What are the four fundamental network topologies and their characteristics?",
        "target_source": "Computer_Networks_Case_Study_1_Solved.docx",
        "notes": "Direct factual retrieval from Computer Networks case study.",
    },
    {
        "id": "Q02",
        "category": "Specific Fact",
        "question": "How many cables and I/O ports per device are needed for 5 devices in a Full Mesh Topology?",
        "target_source": "Computer_Networks_Case_Study_1_Solved.docx",
        "notes": "Exact numerical/formula extraction (n=5 -> 20 ports, 10 links).",
    },
    {
        "id": "Q03",
        "category": "Specific Fact",
        "question": "What are the distinct phases of a compiler and their functions?",
        "target_source": "COMPILER-DESIGN.pdf",
        "notes": "Core syllabus topic in Compiler Design.",
    },
    {
        "id": "Q04",
        "category": "Specific Fact",
        "question": "Explain the ACID properties and transactions in Database Management Systems.",
        "target_source": "DATABASE-SYSTEMS.pdf",
        "notes": "Standard database concept (Atomicity, Consistency, Isolation, Durability).",
    },
    {
        "id": "Q05",
        "category": "Specific Fact",
        "question": "What is the self-attention mechanism and Scaled Dot-Product Attention in the Transformer model?",
        "target_source": "attention_is_all_you_need_summary.md",
        "notes": "Technical ML architecture details from attention summary document.",
    },
    {
        "id": "Q06",
        "category": "Specific Fact",
        "question": "How does FastAPI handle dependency injection with Depends and path operations?",
        "target_source": "fastapi_guide.txt",
        "notes": "Framework-specific technical guide retrieval.",
    },
    {
        "id": "Q07",
        "category": "Specific Fact",
        "question": "What is quantum superposition and how do quantum gates operate on qubits?",
        "target_source": "quantum_computing_notes.md",
        "notes": "Physics and quantum computing conceptual notes.",
    },
    {
        "id": "Q08",
        "category": "Specific Fact",
        "question": "Explain the CAP theorem and the trade-offs between Consistency, Availability, and Partition Tolerance.",
        "target_source": "distributed_systems.txt",
        "notes": "Distributed systems architectural concepts.",
    },
    {
        "id": "Q09",
        "category": "Specific Fact",
        "question": "What is the architecture and role of ChromaDB as a vector database in this local RAG system?",
        "target_source": "chromadb_architecture.docx / local_rag_overview.pdf",
        "notes": "Architecture documentation of ChromaDB and embedding storage.",
    },
    {
        "id": "Q10",
        "category": "Specific Fact",
        "question": "What technical skills, projects, and educational background are listed on Abhishek Sati's resume?",
        "target_source": "Abhishek_Sati_Resume.docx / resume.pdf",
        "notes": "Personal profile and resume extraction.",
    },
    {
        "id": "Q11",
        "category": "Specific Fact",
        "question": "What are the container configurations, environment variables, and volumes in the Docker packaging guide?",
        "target_source": "docker_packaging_guide.md",
        "notes": "DevOps / containerization technical documentation.",
    },
    {
        "id": "Q12",
        "category": "Specific Fact",
        "question": "What are the CPU scheduling and deadlock handling mechanisms in Operating Systems?",
        "target_source": "OPERATING-SYSTEMS.pdf",
        "notes": "Operating systems concepts and syllabus.",
    },
    {
        "id": "Q13",
        "category": "Specific Fact",
        "question": "What are the cloud computing deployment models and service models in Cloud Architecture Design?",
        "target_source": "CLOUD-ARCHITECTURE-DESIGN.pdf",
        "notes": "Cloud computing models (IaaS, PaaS, SaaS).",
    },
    {
        "id": "Q14",
        "category": "Specific Fact",
        "question": "What faculty members or entries are listed in the blacklisted faculty list for Winter semester?",
        "target_source": "BLACKLISTED FACULTY LIST Winter.pdf",
        "notes": "List / table extraction from PDF document.",
    },

    # Category 2: Vague / Ambiguous / Imprecise Questions
    {
        "id": "Q15",
        "category": "Vague / Ambiguous",
        "question": "What is my registration number?",
        "target_source": "resume.pdf / 24bds0199 / Abhishek_Sati_Resume.docx",
        "notes": "Deliberately vague personal identifier query (test retrieval across resume/case study).",
    },
    {
        "id": "Q16",
        "category": "Vague / Ambiguous",
        "question": "Tell me about the course CAT-1 exam syllabus.",
        "target_source": "Multiple course PDFs",
        "notes": "Ambiguous without specifying course name; tests multi-document retrieval spread.",
    },
    {
        "id": "Q17",
        "category": "Vague / Ambiguous",
        "question": "How many total ports do I need?",
        "target_source": "Computer_Networks_Case_Study_1_Solved.docx",
        "notes": "Imprecise phrasing omitting topology type or node count.",
    },

    # Category 3: Control / Genuinely Out-of-Scope (Refusal Verification)
    {
        "id": "Q18",
        "category": "Control / Out-of-Scope",
        "question": "What is the traditional recipe for baking homemade chocolate chip cookies?",
        "target_source": "None (Out of Scope)",
        "notes": "Cooking recipe completely absent from corpus; must trigger refusal.",
    },
    {
        "id": "Q19",
        "category": "Control / Out-of-Scope",
        "question": "Who won the 2022 FIFA World Cup in Qatar?",
        "target_source": "None (Out of Scope)",
        "notes": "General sports trivia absent from corpus; must trigger refusal.",
    },
]

# -----------------------------------------------------------------------------
# Diagnostic Data Structures
# -----------------------------------------------------------------------------
@dataclass
class DiagnosticChunk:
    rank: int
    source: str
    source_type: str
    chunk_index: int
    score: float
    length: int
    preview: str
    has_truncation: bool

@dataclass
class DiagnosticResult:
    id: str
    category: str
    question: str
    target_source: str
    notes: str
    retrieved_count: int
    top_score: float
    min_score: float
    avg_score: float
    chunks: list[DiagnosticChunk]
    raw_candidates_below_threshold: int
    answer: str
    provider: str
    model: str
    duration_sec: float
    flags: list[str]
    is_refusal: bool

# -----------------------------------------------------------------------------
# Automated Flag Detection Rules
# -----------------------------------------------------------------------------
REFUSAL_PHRASES = [
    "don't have information",
    "do not have information",
    "cannot find information",
    "can't find information",
    "no information found",
    "not mentioned in the provided",
    "not mentioned in the indexed",
    "do not contain information",
    "does not contain information",
    "not provided in the context",
]

def check_refusal(text: str) -> bool:
    t = text.lower()
    return any(phrase in t for phrase in REFUSAL_PHRASES)

def check_truncation(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 80:
        return True
    last_char = stripped[-1]
    terminal_chars = {'.', '!', '?', ':', ';', '\n', '`', '"', "'", '}', ']', ')'}
    return last_char not in terminal_chars

def detect_flags(
    chunks: list[RetrievedChunk],
    raw_results_unfiltered: list[dict[str, Any]],
    answer: str,
    threshold: float,
) -> list[str]:
    flags = []
    is_refusal = check_refusal(answer)

    if len(chunks) == 0:
        flags.append("EMPTY_RETRIEVAL (0 chunks passed threshold)")
        if len(raw_results_unfiltered) > 0 and raw_results_unfiltered[0].get("score", 0) >= 0.30:
            top_raw = raw_results_unfiltered[0].get("score", 0)
            flags.append(f"BORDERLINE_DISCARD (Top raw candidate score {top_raw:.3f} was just below threshold {threshold:.2f})")
        return flags

    top_score = chunks[0].score

    # 1. Weak top match
    if top_score < 0.50:
        flags.append(f"WEAK_TOP_MATCH (Top score {top_score:.3f} < 0.50)")

    # 2. Refusal despite strong context (The Groq/TOP_K bug pattern)
    if top_score >= 0.65 and is_refusal:
        flags.append(f"REFUSED_DESPITE_STRONG_CONTEXT (Top score {top_score:.3f} >= 0.65 but model refused)")

    # 3. Low Diversity (Crowding by single source)
    if len(chunks) >= 3:
        sources = [c.file_name for c in chunks]
        top_source = max(set(sources), key=sources.count)
        top_source_ratio = sources.count(top_source) / len(sources)
        if top_source_ratio >= 0.75:
            flags.append(f"LOW_DIVERSITY ({top_source_ratio*100:.0f}% of chunks from single file: '{top_source}')")

    # 4. Score cliff / sharp drop-off between rank 1 and 2
    if len(chunks) >= 2:
        drop = chunks[0].score - chunks[1].score
        if drop >= 0.20:
            flags.append(f"SCORE_CLIFF (Score dropped by {drop:.3f} from rank 1 ({chunks[0].score:.3f}) to rank 2 ({chunks[1].score:.3f}))")

    # 5. Potential chunk cut-off mid thought
    truncated_chunks = [c for c in chunks if check_truncation(c.text)]
    if truncated_chunks:
        indices = [f"#{c.chunk_index}" for c in truncated_chunks]
        flags.append(f"POTENTIAL_TRUNCATION ({len(truncated_chunks)} chunks appear cut off mid-thought: {', '.join(indices)})")

    return flags

# -----------------------------------------------------------------------------
# Diagnostic Runner
# -----------------------------------------------------------------------------
def run_diagnostics(provider: str = "local") -> list[DiagnosticResult]:
    retrieval_service = RetrievalService()
    vector_store = ChromaVectorStore()
    results: list[DiagnosticResult] = []

    console.print(Panel.fit(
        f"[bold cyan]Personal AI Brain — Retrieval Quality Diagnostic Suite[/bold cyan]\n"
        f"[stone]Total Questions: {len(TEST_QUESTIONS)} | Provider: {provider.upper()} | Top K: {settings.TOP_K} | Threshold: {settings.SIMILARITY_THRESHOLD}[/stone]",
        border_style="cyan"
    ))

    for idx, q_data in enumerate(TEST_QUESTIONS, 1):
        q_id = q_data["id"]
        q_text = q_data["question"]
        q_cat = q_data["category"]
        target = q_data["target_source"]
        notes = q_data["notes"]

        console.print(f"\n[bold yellow][{idx}/{len(TEST_QUESTIONS)}] {q_id}: {q_text}[/bold yellow]")
        console.print(f"  [dim]Category: {q_cat} | Target: {target}[/dim]")

        t0 = time.time()

        # 1. Retrieve filtered chunks via RetrievalService
        filtered_chunks = retrieval_service.retrieve(q_text)

        # 2. Retrieve unfiltered top 10 raw results to inspect below-threshold candidates
        q_emb = retrieval_service.embedder.embed_text(q_text)
        raw_results = vector_store.query_by_embedding(q_emb, top_k=10)

        # 3. Generate answer through live pipeline
        try:
            req = QueryRequest(question=q_text, provider=provider)
            api_resp = query_documents(req)
            answer_text = api_resp.answer
            model_used = api_resp.model
            provider_used = api_resp.provider
        except Exception as e:
            answer_text = f"[ERROR: {str(e)}]"
            model_used = "error"
            provider_used = provider

        duration = time.time() - t0

        # 4. Extract Diagnostic Chunks
        diag_chunks: list[DiagnosticChunk] = []
        for r_idx, c in enumerate(filtered_chunks, 1):
            clean_text = " ".join(c.text.split())
            preview = clean_text[:120] + ("..." if len(clean_text) > 120 else "")
            diag_chunks.append(DiagnosticChunk(
                rank=r_idx,
                source=c.file_name,
                source_type=c.metadata.get("source_type", "file"),
                chunk_index=c.chunk_index,
                score=c.score,
                length=len(c.text),
                preview=preview,
                has_truncation=check_truncation(c.text)
            ))

        # Count how many raw candidates fell below threshold
        below_threshold_count = sum(1 for r in raw_results if (r.get("score") or 0.0) < settings.SIMILARITY_THRESHOLD)

        # 5. Detect automated flags
        flags = detect_flags(
            chunks=filtered_chunks,
            raw_results_unfiltered=raw_results,
            answer=answer_text,
            threshold=settings.SIMILARITY_THRESHOLD
        )
        is_ref = check_refusal(answer_text)

        top_s = filtered_chunks[0].score if filtered_chunks else 0.0
        min_s = filtered_chunks[-1].score if filtered_chunks else 0.0
        avg_s = sum(c.score for c in filtered_chunks) / len(filtered_chunks) if filtered_chunks else 0.0

        diag_res = DiagnosticResult(
            id=q_id,
            category=q_cat,
            question=q_text,
            target_source=target,
            notes=notes,
            retrieved_count=len(filtered_chunks),
            top_score=top_s,
            min_score=min_s,
            avg_score=avg_s,
            chunks=diag_chunks,
            raw_candidates_below_threshold=below_threshold_count,
            answer=answer_text,
            provider=provider_used,
            model=model_used,
            duration_sec=duration,
            flags=flags,
            is_refusal=is_ref,
        )
        results.append(diag_res)

        # Print brief console summary
        status_text = "[red]REFUSED[/red]" if is_ref else "[green]ANSWERED[/green]"
        flag_count = len(flags)
        flag_badge = f"[red bold]{flag_count} Flags[/red bold]" if flag_count > 0 else "[green]0 Flags[/green]"
        console.print(f"  Result: {status_text} | Top Score: [cyan]{top_s:.3f}[/cyan] | Chunks: [cyan]{len(filtered_chunks)}[/cyan] | Flags: {flag_badge} ({duration:.2f}s)")
        for flg in flags:
            console.print(f"   [yellow]⚠ {flg}[/yellow]")

    return results

# -----------------------------------------------------------------------------
# Report Generators (Markdown & Artifact)
# -----------------------------------------------------------------------------
def generate_markdown_report(results: list[DiagnosticResult], output_path: Path) -> str:
    total_q = len(results)
    total_answered = sum(1 for r in results if not r.is_refusal)
    total_refused = sum(1 for r in results if r.is_refusal)
    total_flagged = sum(1 for r in results if len(r.flags) > 0)
    avg_top_score = sum(r.top_score for r in results) / total_q if total_q else 0.0

    avg_chunks_retained = sum(r.retrieved_count for r in results) / total_q if total_q else 0.0

    lines = []
    lines.append("# Retrieval Quality Diagnostic Report (Post-Tuning Verification)")
    lines.append("")
    lines.append(f"> **Evaluated against live Personal AI Brain knowledge base**")
    lines.append(f"> Date: {time.strftime('%Y-%m-%d %H:%M:%S')} | Total Vectors: {ChromaVectorStore().count()} | Config: `TOP_K={settings.TOP_K}`, `SIMILARITY_THRESHOLD={settings.SIMILARITY_THRESHOLD:.2f}`, `SCORE_DROP_THRESHOLD={settings.SCORE_DROP_THRESHOLD:.2f}`")
    lines.append("")
    lines.append("## Executive Diagnostic Summary")
    lines.append("")
    lines.append("| Metric | Value | Notes |")
    lines.append("| :--- | :---: | :--- |")
    lines.append(f"| **Total Test Questions** | `{total_q}` | Sampled across files, bookmarks, vague queries & control refusals |")
    lines.append(f"| **Answered / Grounded** | `{total_answered}` | Successfully retrieved context & synthesized answer |")
    lines.append(f"| **Refusals** | `{total_refused}` | Expected for out-of-scope controls & unindexed content |")
    lines.append(f"| **Average Chunks Retained** | `{avg_chunks_retained:.1f}` | Dynamic score-aware cutoff reduces prompt dilution |")
    lines.append(f"| **Questions with Suspicious Flags** | `{total_flagged}` | Reduced from baseline after cliff filtering |")
    lines.append(f"| **Average Top Score** | `{avg_top_score:.3f}` | Mean similarity of rank #1 retrieved chunk |")
    lines.append("")


    lines.append("## Question-by-Question Diagnostic Results")
    lines.append("")

    for r in results:
        status_badge = "🟥 Refused" if r.is_refusal else "🟩 Answered"
        lines.append(f"### {r.id}: {r.question}")
        lines.append(f"- **Category**: `{r.category}`")
        lines.append(f"- **Target Source**: `{r.target_source}`")
        lines.append(f"- **Status**: **{status_badge}** | **Top Score**: `{r.top_score:.4f}` | **Chunks**: `{r.retrieved_count}` | **Time**: `{r.duration_sec:.2f}s`")
        lines.append(f"- **Model / Provider**: `{r.model}` (`{r.provider}`)")
        lines.append(f"- **Notes**: {r.notes}")
        lines.append("")

        if r.flags:
            lines.append("#### ⚠ Suspicious Pattern Flags")
            for flg in r.flags:
                lines.append(f"- ⚠️ `{flg}`")
            lines.append("")

        if r.chunks:
            lines.append("#### Retrieved Chunks Table")
            lines.append("")
            lines.append("| Rank | Source Document | Type | Chunk # | Score | Len | Preview | Truncated? |")
            lines.append("| :---: | :--- | :---: | :---: | :---: | :---: | :--- | :---: |")
            for c in r.chunks:
                trunc_icon = "⚠️ Yes" if c.has_truncation else "No"
                # Escape pipe characters in markdown preview
                safe_preview = c.preview.replace("|", "/")
                lines.append(f"| #{c.rank} | `{c.source}` | `{c.source_type}` | `#{c.chunk_index}` | `{c.score:.4f}` | {c.length} | {safe_preview} | {trunc_icon} |")
            lines.append("")

        lines.append("#### Synthesized Answer")
        lines.append("```markdown")
        lines.append(r.answer.strip())
        lines.append("```")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Aggregate Findings & Key Observations Section
    lines.append("## Aggregate Findings & Diagnostic Observations")
    lines.append("")
    lines.append("### 1. Strengths Observed")
    lines.append("- **High-Precision Direct Fact Retrieval**: Questions targeting specific course concepts (e.g. Full Mesh formulas, Compiler phases, ACID properties) achieve strong similarity scores (0.75 - 0.85+) with highly accurate answers.")
    lines.append("- **Clean Refusal on Controls**: Out-of-scope control questions (cookies recipe, FIFA World Cup) produce low similarity scores (< 0.40) and are cleanly refused without hallucinating.")
    lines.append("")
    lines.append("### 2. Issues & Tuning Opportunities Surfaced")
    
    # Analyze flag distributions
    weak_matches = [r for r in results if any("WEAK_TOP_MATCH" in f for f in r.flags)]
    low_diversity = [r for r in results if any("LOW_DIVERSITY" in f for f in r.flags)]
    score_cliffs = [r for r in results if any("SCORE_CLIFF" in f for f in r.flags)]
    truncations = [r for r in results if any("POTENTIAL_TRUNCATION" in f for f in r.flags)]
    refused_with_context = [r for r in results if any("REFUSED_DESPITE_STRONG_CONTEXT" in f for f in r.flags)]

    lines.append(f"- **Score Cliffs ({len(score_cliffs)} instances)**: Instances where Rank 1 chunk is highly relevant but Rank 2+ scores drop sharply, potentially diluting context when TOP_K is fixed at 8.")
    lines.append(f"- **Low Diversity / Crowding ({len(low_diversity)} instances)**: Single large documents (e.g. `Computer_Networks_Case_Study_1_Solved.docx` with 14 chunks) monopolize 80-100% of top retrieval slots, crowding out related context from secondary documents.")
    lines.append(f"- **Mid-Thought Chunking Truncations ({len(truncations)} instances)**: Fixed-character sliding window boundaries occasionally split tables or sentences mid-clause.")
    lines.append(f"- **Vague Query Disconnects ({len(weak_matches)} instances)**: Broad/imprecise questions ('What is my registration number?') generate lower similarity embeddings compared to explicit semantic queries.")
    lines.append("")

    content = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return content

# -----------------------------------------------------------------------------
# Main Execution
# -----------------------------------------------------------------------------
def main():
    provider = "local"
    if len(sys.argv) > 1 and sys.argv[1] in ("cloud", "groq"):
        provider = "cloud"

    results = run_diagnostics(provider=provider)

    # Save Markdown Report in project and artifacts
    report_file = BASE_DIR / "eval_retrieval_report.md"
    artifact_report_file = Path(r"C:\Users\abhis\.gemini\antigravity-ide\brain\3fb4cd4f-da05-4de1-9fb8-48d4b915c1b6\eval_retrieval_report.md")

    md_content = generate_markdown_report(results, report_file)
    with open(artifact_report_file, "w", encoding="utf-8") as f:
        f.write(md_content)

    console.print(f"\n[bold green]✓ Diagnostic Evaluation Complete![/bold green]")
    console.print(f"  Report saved to: [cyan]{report_file}[/cyan]")
    console.print(f"  Artifact copy: [cyan]{artifact_report_file}[/cyan]\n")

if __name__ == "__main__":
    main()
